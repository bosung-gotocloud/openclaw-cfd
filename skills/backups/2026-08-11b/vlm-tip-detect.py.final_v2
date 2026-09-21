#!/usr/bin/env python3
"""
STEP Tip Detection — CAD-edge projection + VLM BBox snap
===
2026-08-06: 초기화 완료
- PNG: CAD 축 방향 그대로, mesh bbox center가 이미지 중앙
- tip: VLM이 2D bbox 반환 → CAD snap으로 정확한 3D 좌표
- 필요시 VLM 없이 CAD snap만 사용 (bbox manual)

Dependencies:
    pip install cadquery numpy Pillow opencv-python
"""

import argparse, json, os, sys, numpy as np, cv2
import cadquery as cq

# ─── STEP load ───

def load_step(step_file):
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
    if diag > 100:
        all_verts /= 1000; vmin /= 1000; vmax /= 1000; size /= 1000
    return {
        'edges': edges_3d, 'verts': all_verts,
        'bbox': {'xmin':float(vmin[0]),'xmax':float(vmax[0]),'ymin':float(vmin[1]),
                 'ymax':float(vmax[1]),'zmin':float(vmin[2]),'zmax':float(vmax[2]),
                 'xl':float(size[0]),'yl':float(size[1]),'zl':float(size[2]),
                 'center':(vmin+vmax)/2},
        'size_m': size
    }

# ─── View mapping ───
VIEW = {
    'XZ': {'ax1': 0, 'n1': 'X', 'ax2': 2, 'n2': 'Z'},
    'YZ': {'ax1': 1, 'n1': 'Y', 'ax2': 2, 'n2': 'Z'},
    'XY': {'ax1': 0, 'n1': 'X', 'ax2': 1, 'n2': 'Y'},
}

# ─── Render ortho PNG ───

def render_ortho(edges, view, bbox, img_size=1000):
    ax1 = VIEW[view]['ax1']; ax2 = VIEW[view]['ax2']
    n1 = VIEW[view]['n1']; n2 = VIEW[view]['n2']
    h_min = bbox[f'{n1.lower()}min']; h_max = bbox[f'{n1.lower()}max']
    v_min = bbox[f'{n2.lower()}min']; v_max = bbox[f'{n2.lower()}max']
    h_span = h_max - h_min or 1; v_span = v_max - v_min or 1
    margin = 0.05
    fit_scale = min((img_size*(1-2*margin))/h_span, (img_size*(1-2*margin))/v_span)
    ch = (h_min + h_max) / 2; cv = (v_min + v_max) / 2
    off_x = int(img_size//2 - ch*fit_scale); off_y = int(img_size//2 - cv*fit_scale)
    
    def to_px(h, v):
        return int(round(h*fit_scale + off_x)), int(round(img_size - (v*fit_scale + off_y)))
    
    img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)
    # Draw edges as bold black lines for clear silhouette
    for edge in edges:
        pts, _ = edge.sample(30); arr = np.array([[p.x,p.y,p.z] for p in pts])
        for i in range(len(arr)-1):
            x1,y1 = to_px(arr[i,ax1],arr[i,ax2]); x2,y2 = to_px(arr[i+1,ax1],arr[i+1,ax2])
            if (-50<=x1<=img_size+50 and -50<=y1<=img_size+50 and -50<=x2<=img_size+50 and -50<=y2<=img_size+50):
                cv2.line(img, (x1,y1), (x2,y2), (0,0,0), 2)
    
    # Center crosshair
    cx, cy = to_px(ch, cv); cv2.circle(img, (cx,cy), 5, (0,200,0), -1)
    # Axis labels
    cv2.putText(img, f'{n1} →', (10, img_size-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)
    cv2.putText(img, f'{n2} ↑', (img_size-80, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)
    
    di = {'fit_scale':fit_scale,'offset_x':off_x,'offset_y':off_y,
          'h_min':h_min,'h_max':h_max,'v_min':v_min,'v_max':v_max,
          'h_span':h_span,'v_span':v_span,
          'to_px':to_px}
    return img, di

# ─── CAD snap ───

def snap_to_edges(edges, view, cad_h, cad_v, bbox, tol=0.05):
    ax1 = VIEW[view]['ax1']; ax2 = VIEW[view]['ax2']
    tol_m = max(bbox['xl'], bbox['yl'], bbox['zl']) * tol
    best_score = -1; best_pt = None
    for edge in edges:
        pts, _ = edge.sample(200); arr = np.array([[p.x,p.y,p.z] for p in pts])
        for i in range(len(arr)-1):
            h1,v1 = arr[i,ax1], arr[i,ax2]
            h2,v2 = arr[i+1,ax1], arr[i+1,ax2]
            seg = np.array([h2-h1, v2-v1]); sl = np.linalg.norm(seg)
            if sl < 1e-15: continue
            t = max(0,min(1,((cad_h-h1)*(h2-h1)+(cad_v-v1)*(v2-v1))/sl**2))
            ph = h1+t*(h2-h1); pv = v1+t*(v2-v1)
            dist = abs(ph-cad_h)+abs(pv-cad_v)
            if dist < tol_m:
                score = 1/(dist+0.001)
                # Bonus for sharp corners
                if i > 0 and i < len(arr)-2:
                    pv2 = arr[i]-arr[max(0,i-1)]; nv2 = arr[min(len(arr)-1,i+1)]-arr[i]
                    nl2 = np.linalg.norm(pv2)*np.linalg.norm(nv2)
                    if nl2 > 0:
                        ca = np.dot(pv2,nv2)/nl2; ca = np.clip(ca,-1,1)
                        if ca < 0.7: score *= 2
                if score > best_score:
                    best_score = score; best_pt = arr[i]
    return best_pt

# ─── VLM (optional) ───

try:
    import ollama; HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

VL_PROMPT = ("Aircraft silhouette on white background. Find wing tips (far left/right of body) and tail tips (far up/down). Exclude the nose (the frontmost pointed part). "
             "Return JSON ONLY: {tips:[{tip_id:N,bbox:[x1,y1,x2,y2]}]} "
             "x1,y1,x2,y2 are pixel coordinates 0-1000. "
             "Put each box tightly around the tip with ~20px margin. "
             "tip_id: start from 1, increment. "
             "Include ALL wing tips and tail tips you can see.")

def get_vlm(image_path):
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        r = ollama.chat(model='qwen3.6:35b',
                        messages=[{"role":"user","content":VL_PROMPT,"images":[image_path]}],
                        stream=False)
        return r['message']['content']
    except: return None

def parse_vlm(raw):
    if not raw: return []
    t = raw.strip()
    for s in ['```json','```']:
        if s in t: t = t.split(s)[1].split(s)[0].strip()
    try: d = json.loads(t)
    except: return []
    tips = d.get('tips',[])
    res = []
    for tp in tips:
        tid = tp.get('tip_id', tp.get('id'))
        bb = tp.get('bbox', tp.get('bbox_2d'))
        if tid is not None and bb and len(bb)==4:
            res.append({'tip_id':int(tid),'bbox':[float(x) for x in bb]})
    return res

# ─── Iso view ───

def render_iso(edges, tips, bbox, sz=800):
    img = np.full((sz,sz,3), 255, dtype=np.uint8)
    c = bbox['center']; me = max(bbox['xl'],bbox['yl'],bbox['zl']) or 1
    sc = sz*0.7/me; c35,s35 = np.cos(np.radians(35.264)),np.sin(np.radians(35.264))
    c45,s45 = np.cos(np.radians(45)),np.sin(np.radians(45))
    def _p(p):
        tx,ty,tz = p[0]-c[0],p[1]-c[1],p[2]-c[2]
        rx=tx*c45+tz*s45; ry=ty; rz=-tx*s45+tz*c45
        return rx*sc+sz//2, -(ry*c35-rz*s35)*sc+sz//2
    for edge in edges:
        pts,_ = edge.sample(30); arr = np.array([[p.x,p.y,p.z] for p in pts])
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

def triangulate(tips_by_view, all_verts):
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
            # Fill missing from nearest vertex
            for j in range(3):
                if j==0 and x is None:
                    d2 = np.linalg.norm(all_verts[:,:1]-np.array([[y or 0],[z or 0]]),axis=1) if all_verts.size>0 else []
                elif j==1 and y is None:
                    d2 = np.linalg.norm(all_verts[:,:1]-np.array([[x or 0],[z or 0]]),axis=1) if all_verts.size>0 else []
                else:
                    d2 = [0]*len(all_verts) if all_verts.size>0 else []
            best_j = np.argmin(d2) if d2 and all_verts.size>0 else 0
            val = all_verts[best_j,j] if all_verts.size>0 else 0
            if j==0: x=val
            elif j==1: y=val
            else: z=val
            result.append(np.array([x or 0, y or 0, z or 0]))
    
    final = []
    for t in result:
        if all(np.linalg.norm(t-f)>=0.05 for f in final): final.append(t)
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
    edges = data['edges']; bbox = data['bbox']; verts = data['verts']
    print(f"BBox(m): X[{bbox['xmin']:.3f}..{bbox['xmax']:.3f}] Y[{bbox['ymin']:.3f}..{bbox['ymax']:.3f}] Z[{bbox['zmin']:.3f}..{bbox['zmax']:.3f}]\n")
    
    tips_by_view = {}
    img_paths = {}
    
    for vn in ['XZ','YZ','XY']:
        img, di = render_ortho(edges, vn, bbox)
        op = os.path.join(sd, f'{sn}_{vn}.png')
        cv2.imwrite(op, img); img_paths[vn] = op
        ch = (di['h_min']+di['h_max'])/2; cv = (di['v_min']+di['v_max'])/2
        cx, cy = di['to_px'](ch, cv)
        print(f"[{vn}] {op} center=({cx},{cy})")
        
        if args.no_vlm:
            # No VLM — skip
            tips_by_view[vn] = []
            continue
        
        raw = get_vlm(op)
        if raw:
            bbs = parse_vlm(raw)
            print(f"  VLM: {len(bbs)} tip(s)")
        else:
            bbs = []; print(f"  VLM: none")
        
        tips = []
        for bb in bbs:
            tid, x1, y1, x2, y2 = bb['tip_id'], *bb['bbox']
            cx_px = (x1+x2)/2; cy_px = (y1+y2)/2
            # pixel → CAD
            CAD_h = (cx_px - di['offset_x']) / di['fit_scale'] + di['h_min']
            CAD_v = (1000 - cy_px - di['offset_y']) / di['fit_scale'] + di['v_min']
            snapped = snap_to_edges(edges, vn, CAD_h, CAD_v, bbox, tol=0.05)
            if snapped is not None:
                tips.append(snapped)
                print(f"  tip#{tid}: CAD({CAD_h:.3f},{CAD_v:.3f})→snap({snapped[0]*1000:.1f},{snapped[1]*1000:.1f},{snapped[2]*1000:.1f})mm")
        tips_by_view[vn] = tips
        print(f"  [{vn}] {len(tips)} snapped tip(s)\n")
    
    if not any(tips_by_view.values()):
        print("No tips detected. Try: --no-vlm to skip VLM, or check VLM output.")
        sys.exit(1)
    
    # Triangulate
    tips_3d = triangulate(tips_by_view, verts)
    print(f"\n{len(tips_3d)} 3D tip(s):")
    for i, t in enumerate(tips_3d):
        print(f"  Tip {i+1}: ({t[0]*1000:.1f}, {t[1]*1000:.1f}, {t[2]*1000:.1f}) mm")
    
    if tips_3d:
        csv_p = os.path.join(sd, f'{sn}_tip_points.csv')
        with open(csv_p,'w') as f:
            for t in tips_3d: f.write(f'{t[0]:.6f},{t[1]:.6f},{t[2]:.6f}\n')
        print(f"\nCSV: {csv_p}")
        
        iso = render_iso(edges, tips_3d, bbox)
        png_p = os.path.join(sd, f'{sn}_tip.png')
        cv2.imwrite(png_p, iso)
        print(f"PNG: {png_p}")
    
    print(f"\n{'='*60}\nDone!\n{'='*60}")

if __name__ == '__main__':
    main()
