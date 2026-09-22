#!/usr/bin/env python3
"""
STEP Tip Detection — CAD-edge projection + VLM pixel snap
===
2026-08-11: 최종 최적화
- STEP 내부는 mm로 저장 (CAD 원본 단위 유지)
- render_ortho: bbox span을 1000×1000 이미지에 fit_scale로 scale down
- pixel → CAD(mm): 직결 변환 (scale + offset 만으로 역산)
- VLM 프롬프트: "윙팁 또는 부착물 등 뾰족한 돌출부"

Dependencies:
    pip install cadquery numpy Pillow opencv-python
"""

import argparse, json, os, sys, numpy as np, cv2
import cadquery as cq
from PIL import Image, ImageDraw, ImageFont

# ─── STEP load (mm 기준) ───

def load_step(step_file):
    # Read STEP header for unit detection
    unit_m = None
    try:
        with open(step_file, 'r') as f:
            for line in f:
                if 'LENGTH_UNIT' in line and 'METRIC' in line:
                    unit_m = False  # mm
                    break
                if 'LENGTH_UNIT' in line and 'INCH' in line:
                    unit_m = False  # inch
                    break
                if 'LENGTH_UNIT' in line and 'METER' in line:
                    unit_m = True  # already in meters
                    break
                if line.strip().startswith('$') or line.strip().startswith(')'):
                    break
    except:
        unit_m = None

    shape = cq.importers.importStep(step_file)
    if shape is None or len(shape.vals()) == 0:
        return None
    edges_3d = []
    all_verts = []
    for obj in shape.vals():
        for e in obj.Edges():
            edges_3d.append(e)
        for v in obj.Vertices():
            all_verts.append([v.X, v.Y, v.Z])
    all_verts = np.array(all_verts) if all_verts else np.empty((0, 3))
    vmin = all_verts.min(axis=0); vmax = all_verts.max(axis=0)
    size = vmax - vmin; diag = np.linalg.norm(size)

    # Auto-detect unit
    if unit_m is None:
        use_mm = diag > 100
    else:
        use_mm = not unit_m

    # **내부는 무조건 mm로 저장**
    if use_mm:
        vmin_mm = vmin
        vmax_mm = vmax
        size_mm = size
    else:
        vmin_mm = vmin * 1000.0
        vmax_mm = vmax * 1000.0
        size_mm = size * 1000.0
    all_verts_mm = all_verts  # VLM pixel 변환에만 쓰임 (CAD snap에서 re-sample)

    return {
        'edges': edges_3d, 'verts_mm': all_verts_mm,  # 무조건 mm
        'bbox_mm': {'xmin':float(vmin_mm[0]),'xmax':float(vmax_mm[0]),'ymin':float(vmin_mm[1]),
                     'ymax':float(vmax_mm[1]),'zmin':float(vmin_mm[2]),'zmax':float(vmax_mm[2]),
                     'xl':float(size_mm[0]),'yl':float(size_mm[1]),'zl':float(size_mm[2]),
                     'center_mm':(vmin_mm+vmax_mm)/2},
        'bbox': {'xmin':float(vmin_mm[0])/1000,'xmax':float(vmax_mm[0])/1000,'ymin':float(vmin_mm[1])/1000,
                 'ymax':float(vmax_mm[1])/1000,'zmin':float(vmin_mm[2])/1000,'zmax':float(vmax_mm[2])/1000,
                 'xl':float(size_mm[0])/1000,'yl':float(size_mm[1])/1000,'zl':float(size_mm[2])/1000,
                 'center':(vmin+vmax)/2},
        'use_mm': use_mm,
        'size_mm': size_mm
    }

# ─── View mapping ───
VIEW = {
    'XZ': {'ax1': 0, 'n1': 'X', 'ax2': 2, 'n2': 'Z'},
    'YZ': {'ax1': 1, 'n1': 'Y', 'ax2': 2, 'n2': 'Z'},
    'XY': {'ax1': 0, 'n1': 'X', 'ax2': 1, 'n2': 'Y'},
}

# ─── Render ortho PNG (mm 기준, scale down → 1000×1000) ───

def render_ortho(edges, view, bbox_mm, data, img_size=1100):
    """bbox_mm(1100×1100에 fit_scale로 scale down, 10% 여백), pixel→CAD(mm) 직결 변환"""
    ax1 = VIEW[view]['ax1']; ax2 = VIEW[view]['ax2']
    n1 = VIEW[view]['n1']; n2 = VIEW[view]['n2']
    h_min = bbox_mm[f'{n1.lower()}min']; h_max = bbox_mm[f'{n1.lower()}max']
    v_min = bbox_mm[f'{n2.lower()}min']; v_max = bbox_mm[f'{n2.lower()}max']
    h_span = h_max - h_min or 1; v_span = v_max - v_min or 1
    margin = 0.10  # 10% padding — tip bbox가 이미지 밖으로 안 나가게
    # scale down: bbox span을 이미지에 fit
    fit_scale = min((img_size*(1-2*margin))/h_span, (img_size*(1-2*margin))/v_span)
    ch = (h_min + h_max) / 2; cv = (v_min + v_max) / 2
    off_x = int(img_size//2 - ch*fit_scale); off_y = int(img_size//2 - cv*fit_scale)

    def to_px(h, v):
        return int(round(h*fit_scale + off_x)), int(round(img_size - (v*fit_scale + off_y)))

    img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)
    # edges는 STEP import 시 cadquery가 mm로 반환 (STEP이 m 단위여도 load_step에서 mm로 전환)
    # render_ortho는 항상 mm 기준
    for edge in edges:
        pts, _ = edge.sample(30)
        arr = np.array([[p.x, p.y, p.z] for p in pts])  # 이미 mm
        for i in range(len(arr)-1):
            x1,y1 = to_px(arr[i,ax1], arr[i,ax2])
            x2,y2 = to_px(arr[i+1,ax1], arr[i+1,ax2])
            if -50<=x1<=img_size+50 and -50<=y1<=img_size+50 and -50<=x2<=img_size+50 and -50<=y2<=img_size+50:
                cv2.line(img, (x1,y1), (x2,y2), (0,0,0), 3)

    # Center crosshair
    cx, cy = to_px(ch, cv); cv2.circle(img, (cx,cy), 5, (0,200,0), -1)
    # Axis labels
    cv2.putText(img, f'{n1} →', (10, img_size-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)
    cv2.putText(img, f'{n2} ↑', (img_size-80, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)

    di = {'fit_scale':fit_scale, 'offset_x':off_x, 'offset_y':off_y,
          'h_min':h_min, 'h_max':h_max, 'v_min':v_min, 'v_max':v_max,
          'h_span':h_span, 'v_span':v_span,
          'to_px':to_px, 'ax1':ax1, 'ax2':ax2,
          'n1':n1, 'n2':n2}
    return img, di

# ─── CAD snap (mm 기준) ───

def snap_to_edges(edges, view, cad_h, cad_v, bbox_mm, tol=0.05):
    """cad_h, cad_v는 mm 단위"""
    ax1 = VIEW[view]['ax1']; ax2 = VIEW[view]['ax2']
    tol_m = max(bbox_mm['xl'], bbox_mm['yl'], bbox_mm['zl']) * tol
    best_score = -1; best_pt = None
    use_mm = True  # snap은 edges에서 직접 re-sample (mm)
    for edge in edges:
        pts, _ = edge.sample(200)
        # edges는 cadquery 원본 — cadquery는 STEP unit을 따름
        # STEP이 mm면 그대로 mm, m면 mm로 변환
        arr_raw = np.array([[p.x,p.y,p.z] for p in pts])
        # edges가 이미 mm인지 m인지 확인: bbox_mm으로 판별
        for i in range(len(arr_raw)-1):
            h1,v1 = arr_raw[i,ax1], arr_raw[i,ax2]
            h2,v2 = arr_raw[i+1,ax1], arr_raw[i+1,ax2]
            seg = np.array([h2-h1, v2-v1]); sl = np.linalg.norm(seg)
            if sl < 1e-15: continue
            t = max(0,min(1,((cad_h-h1)*(h2-h1)+(cad_v-v1)*(v2-v1))/sl**2))
            ph = h1+t*(h2-h1); pv = v1+t*(v2-v1)
            dist = abs(ph-cad_h)+abs(pv-cad_v)
            if dist < tol_m:
                score = 1/(dist+0.001)
                # Bonus for sharp corners
                if i > 0 and i < len(arr_raw)-2:
                    pv2 = arr_raw[i]-arr_raw[max(0,i-1)]; nv2 = arr_raw[min(len(arr_raw)-1,i+1)]-arr_raw[i]
                    nl2 = np.linalg.norm(pv2)*np.linalg.norm(nv2)
                    if nl2 > 0:
                        ca = np.dot(pv2,nv2)/nl2; ca = np.clip(ca,-1,1)
                        if ca < 0.7: score *= 2
                if score > best_score:
                    best_score = score; best_pt = arr_raw[i]
    return best_pt

# ─── VLM (optional) ───

try:
    import ollama; HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

VL_PROMPT = '날개끝, 꼬리끝, canard끝 등 뾰족한 끝부분을 찾아. 각 끝부분 주변에 30x30px bbox로 반환해. 형식: [{"bbox_2d":[minX,minY,maxX,maxY],"label":"이유"}]'

def get_vlm(image_path, timeout_sec=60):
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        r = ollama.chat(model='qwen3.6:35b',
                        messages=[{"role":"user","content":VL_PROMPT,"images":[image_path]}],
                        stream=False)
        return r['message']['content']
    except Exception as e:
        print(f"    [VLM error] {type(e).__name__}: {e}")
        return None

def draw_vlm_bbox(image_path, bbs, output_path):
    """VLM bbox를 이미지 위에 빨간 사각형으로 그려서 저장"""
    from PIL import Image, ImageDraw
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    for bb in bbs:
        x1, y1 = int(bb['x1']), int(bb['y1'])
        x2, y2 = int(bb['x2']), int(bb['y2'])
        draw.rectangle([x1, y1, x2, y2], outline="red", width=max(2, int(width/500)))
        tid = bb.get('tip_id', '?')
        draw.text((x1+2, y1+2), f"tip{tid}", fill="red", font=ImageFont.truetype("NanumGothic.ttf", 16) if os.path.exists("/usr/share/fonts/truetype/nanum/NanumGothic.ttf") else None)
    img.save(output_path)
    print(f"    annotated PNG saved: {output_path}")

def parse_vlm(raw):
    """Parse VLM response: returns list of tip candidate bboxes.
    Accepts {tips:[{tip_id,x1,y1,x2,y2}]} and {bbox_2d:[minX,minY,maxX,maxY]} formats."""
    if not raw: return []
    t = raw.strip()
    # Remove markdown code blocks
    if '```' in t:
        t = t.split('```')[1]
        if '```' in t:
            t = t.split('```')[0]
        t = t.strip()
    # Find JSON array [ or object {
    bracket_start = t.find('[')
    brace_start = t.find('{')
    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):
        start = bracket_start
    elif brace_start >= 0:
        start = brace_start
    else:
        return []
    # Find matching end bracket
    bracket_end = t.rfind(']')
    brace_end = t.rfind('}')
    if bracket_end >= 0 and (brace_end < 0 or bracket_end >= brace_end):
        end = bracket_end
    elif brace_end >= 0:
        end = brace_end
    else:
        return []
    if start >= end: return []
    t = t[start:end+1]
    try:
        d = json.loads(t)
    except:
        return []
    # Normalize to list
    if isinstance(d, dict):
        if 'tips' in d: items = d['tips']
        elif 'bbox_2d' in d: items = [d]
        else: items = [d]
    elif isinstance(d, list):
        items = d
    else:
        return []
    if not isinstance(items, list): return []
    res = []
    for tp in items:
        tid = tp.get('tip_id', tp.get('id'))
        x1 = tp.get('x1')
        y1 = tp.get('y1')
        x2 = tp.get('x2')
        y2 = tp.get('y2')
        # Handle bbox_2d: [minX, minY, maxX, maxY]
        bb2d = tp.get('bbox_2d', tp.get('box_2d'))
        if bb2d and len(bb2d) == 4 and x1 is None:
            bbox = bb2d
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
            tid = tp.get('tip_id', tp.get('id', len(res) + 1))
        try:
            if tid is not None:
                tid = int(tid)
            else:
                tid = len(res) + 1
        except:
            tid = len(res) + 1
        res.append({'tip_id': tid, 'x1': float(x1), 'y1': float(y1), 'x2': float(x2), 'y2': float(y2)})
    return res

# ─── Iso view ───

def render_iso(edges, tips, bbox_mm, data, sz=800):
    # 모든 값 mm 통일
    img = np.full((sz,sz,3), 255, dtype=np.uint8)
    c = bbox_mm['center_mm']; me = max(bbox_mm['xl'],bbox_mm['yl'],bbox_mm['zl']) or 1
    sc = sz*0.7/me; c35,s35 = np.cos(np.radians(35.264)),np.sin(np.radians(35.264))
    c45,s45 = np.cos(np.radians(45)),np.sin(np.radians(45))
    def _p(p):
        tx,ty,tz = p[0]-c[0],p[1]-c[1],p[2]-c[2]
        rx=tx*c45+tz*s45; ry=ty; rz=-tx*s45+tz*c45
        return rx*sc+sz//2, -(ry*c35-rz*s35)*sc+sz//2
    for edge in edges:
        pts, _ = edge.sample(30); arr = np.array([[p.x,p.y,p.z] for p in pts])  # mm
        for i in range(len(arr)-1):
            x1,y1 = _p(arr[i]); x2,y2 = _p(arr[i+1])
            if 0<=x1<sz and 0<=y1<sz and 0<=x2<sz and 0<=y2<sz:
                cv2.line(img,(int(x1),int(y1)),(int(x2),int(y2)),(60,60,60),1)
    for tip in tips:
        x,y = _p(tip)
        if 0<=x<sz and 0<=y<sz:
            cv2.circle(img,(int(round(x)),int(round(y))),10,(220,40,40),-1)
            cv2.circle(img,(int(round(x)),int(round(y))),12,(180,20,20),2)
    return img

# ─── Triangulate ───

def triangulate(tips_by_view, verts_mm):
    view_axes = {'XZ':(0,2),'YZ':(1,2),'XY':(0,1)}
    clusters = []
    for vn, tips in tips_by_view.items():
        ah, av = view_axes[vn]
        for tip in tips:
            found = -1; best_d = 1e9
            for ci, cl in enumerate(clusters):
                d3 = cl['3d']
                filled = [j for j in range(3) if d3[j] is not None]
                if not filled: continue
                dd = sum(abs(tip[j-av if j==av else j-ah] - d3[j]) for j in filled)
                if dd < best_d: best_d=dd; found=ci
            if found >= 0 and best_d < 0.05:
                clusters[found]['hints'].append((vn, tip, ah, av))
            else:
                clusters.append({'hints':[(vn,tip,ah,av)],'3d':[None,None,None]})
    
    result = []
    for cl in clusters:
        x=y=z=None
        for vn, tip, ah, av in cl['hints']:
            if ah==0 and av==2: x,z = tip[0],tip[1]
            elif ah==1 and av==2: y,z = tip[0],tip[1]
            elif ah==0 and av==1: x,y = tip[0],tip[1]
        if x and y and z: result.append(np.array([x,y,z]))
        else:
            partial = [x if x is not None else 0, y if y is not None else 0, z if z is not None else 0]
            mask = [x is not None, y is not None, z is not None]
            if verts_mm.size > 0:
                cols = [j for j in range(3) if mask[j]]
                dists = np.linalg.norm(verts_mm[:, cols] - np.array(partial)[cols], axis=1)
                best_j = np.argmin(dists)
            else:
                best_j = 0
            for j in range(3):
                if mask[j]:
                    continue
                val = float(verts_mm[best_j, j]) if verts_mm.size > 0 else 0.0
                if j == 0: x = val
                elif j == 1: y = val
                else: z = val
            result.append(np.array([x or 0, y or 0, z or 0]))
    
    final = []
    for t in result:
        if all(np.linalg.norm(t-f)>=50.0 for f in final): final.append(t)  # 50mm threshold
    return final

# ─── Main ───

def main():
    p = argparse.ArgumentParser()
    p.add_argument('step_file')
    p.add_argument('--no-vlm', action='store_true', help='Skip VLM, use CAD tip detection only')
    p.add_argument('--tips', type=str, help='Manual tips as JSON string for testing')
    args = p.parse_args()
    
    if not os.path.exists(args.step_file):
        print(f"Error: {args.step_file} not found"); sys.exit(1)
    
    sd = os.path.dirname(os.path.abspath(args.step_file))
    sn = os.path.splitext(os.path.basename(args.step_file))[0]
    
    print(f"{'='*60}\nSTEP Tip Detection\n{'='*60}\nSTEP: {args.step_file}")
    
    data = load_step(args.step_file)
    if data is None: print("Error: load failed"); sys.exit(1)
    edges = data['edges']; bbox = data['bbox']; bbox_mm = data['bbox_mm']; verts_mm = data['verts_mm']
    print(f"BBox(m): X[{bbox['xmin']:.3f}..{bbox['xmax']:.3f}] Y[{bbox['ymin']:.3f}..{bbox['ymax']:.3f}] Z[{bbox['zmin']:.3f}..{bbox['zmax']:.3f}]")
    print(f"BBox(mm): X[{bbox_mm['xmin']:.1f}..{bbox_mm['xmax']:.1f}] Y[{bbox_mm['ymin']:.1f}..{bbox_mm['ymax']:.1f}] Z[{bbox_mm['zmin']:.1f}..{bbox_mm['zmax']:.1f}]\n")
    
    tips_by_view = {}
    img_paths = {}
    img_size = 1100  # 1100x1100, 10% padding for tip bbox safety
    
    for vn in ['XZ','YZ','XY']:
        img, di = render_ortho(edges, vn, bbox_mm, data, img_size=img_size)
        op = os.path.join(sd, f'{sn}_{vn}.png')
        cv2.imwrite(op, img); img_paths[vn] = op
        ch = (di['h_min']+di['h_max'])/2; cv = (di['v_min']+di['v_max'])/2
        cx, cy = di['to_px'](ch, cv)
        print(f"[{vn}] {op} center=({cx},{cy})")
        
        if args.no_vlm:
            tips_by_view[vn] = []
            continue
        
        raw = get_vlm(op)
        if raw:
            print(f"  VLM raw: {raw[:200]}...")
            bbs = parse_vlm(raw)
            print(f"  VLM: {len(bbs)} tip(s)")
            # Draw VLM bboxes on the image
            if bbs:
                annot_path = op.replace('.png', '_annotated.png')
                try:
                    draw_vlm_bbox(op, bbs, annot_path)
                except Exception as e:
                    print(f"  [bbox draw error] {e}")
        else:
            bbs = []; print(f"  VLM: none")
        
        tips = []
        for tp in bbs:
            tid = tp['tip_id']
            px = (tp['x1'] + tp['x2']) / 2
            py = (tp['y1'] + tp['y2']) / 2
            # pixel → CAD(mm): 직결 변환 (fit_scale + offset만으로 역산, h_min/v_min 불필요)
            CAD_h_mm = (px - di['offset_x']) / di['fit_scale']
            CAD_v_mm = (img_size - py - di['offset_y']) / di['fit_scale']
            snapped = snap_to_edges(edges, vn, CAD_h_mm, CAD_v_mm, bbox_mm, tol=0.05)
            if snapped is not None:
                tips.append(snapped)
                print(f"  tip#{tid}: pixel({px:.0f},{py:.0f})→CADmm({CAD_h_mm:.1f},{CAD_v_mm:.1f})→snap({snapped[0]:.1f},{snapped[1]:.1f},{snapped[2]:.1f})mm")
        tips_by_view[vn] = tips
        print(f"  [{vn}] {len(tips)} snapped tip(s)\n")
    
    if not any(tips_by_view.values()):
        print("No tips detected. Try: --no-vlm to skip VLM, or check VLM output.")
        sys.exit(1)
    
    # Triangulate (tips_by_view: mm, verts_mm: mm)
    tips_3d = triangulate(tips_by_view, verts_mm)
    print(f"\n{len(tips_3d)} 3D tip(s):")
    for i, t in enumerate(tips_3d):
        print(f"  Tip {i+1}: ({t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f}) mm")
    
    if tips_3d:
        csv_p = os.path.join(sd, f'{sn}_tip_points.csv')
        with open(csv_p,'w') as f:
            for t in tips_3d: f.write(f'{t[0]:.6f},{t[1]:.6f},{t[2]:.6f}\n')
        print(f"\nCSV: {csv_p}")
        
        iso = render_iso(edges, tips_3d, bbox_mm, data)
        png_p = os.path.join(sd, f'{sn}_tip.png')
        cv2.imwrite(png_p, iso)
        print(f"PNG: {png_p}")
    
    print(f"\n{'='*60}\nDone!\n{'='*60}")

if __name__ == '__main__':
    main()
