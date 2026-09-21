#!/usr/bin/env python3
"""
STL Tip Detection — STL mesh projection + VLM pixel snap
===
2026-09-07: STL 기반 버전
- STL 내부는 m로 저장 (단위 미지정 시 m 가정)
- render_ortho: STL face-filled projection (외곽선만 visible, 내부 face gray fill)
- pixel → CAD(m): 직결 변환 (scale + offset 만으로 역산)
- VLM 프롬프트: "윙팁 또는 부착물 등 뾰족한 돌출부"

Dependencies:
    pip install numpy Pillow opencv-python trimesh ollama
"""

import argparse, json, os, sys, numpy as np, cv2
import trimesh
from PIL import Image, ImageDraw, ImageFont

# ─── STL load (m 기준) ───

def load_stl(stl_file):
    """STL 파일을 로드하여 m 기준으로 저장.
    
    STL 파일은 단위 메타데이터가 없으므로 m으로 가정.
    """
    try:
        mesh = trimesh.load(stl_file)
        # Scene (multi-body STEP) → single Mesh
        if hasattr(mesh, "geometry") and not hasattr(mesh, "vertices"):
            mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
        if mesh is None or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            return None
    except Exception as e:
        print(f"  [load error] {type(e).__name__}: {e}")
        return None

    
    verts = mesh.vertices  # (N, 3) in m
    faces = mesh.faces  # (M, 3) indices
    edges_unique = mesh.edges_unique  # (E, 2) edge indices
    
    vmin = verts.min(axis=0); vmax = verts.max(axis=0)
    size = vmax - vmin
    
    return {
        'mesh': mesh,
        'verts': verts,  # (N, 3) in m
        'faces': faces,  # (M, 3) indices
        'edges_unique': edges_unique,  # (E, 2) edge indices
        'bbox': {
            'xmin': float(vmin[0]), 'xmax': float(vmax[0]),
            'ymin': float(vmin[1]), 'ymax': float(vmax[1]),
            'zmin': float(vmin[2]), 'zmax': float(vmax[2]),
            'xl': float(size[0]), 'yl': float(size[1]), 'zl': float(size[2]),
            'center': (vmin + vmax) / 2
        },
        'size': size
    }

# ─── View mapping ───
VIEW = {
    'XZ': {'ax1': 0, 'n1': 'X', 'ax2': 2, 'n2': 'Z'},
    'YZ': {'ax1': 1, 'n1': 'Y', 'ax2': 2, 'n2': 'Z'},
    'XY': {'ax1': 0, 'n1': 'X', 'ax2': 1, 'n2': 'Y'},
}

# ─── STL-based ortho rendering (face-filled, outer silhouette only) ───

def render_ortho_stl(data, view, img_size=1100):
    """STL face-filled orthographic view.
    
    trimesh mesh를 직접 사용 → orthographic projection → face filled (gray) + edges (gray).
    외곽선은 gray line, 내부는 gray face fill로 덮어서 내부 선이 보이지 않음.
    """
    ax1 = VIEW[view]['ax1']; ax2 = VIEW[view]['ax2']
    n1 = VIEW[view]['n1']; n2 = VIEW[view]['n2']
    bbox = data['bbox']
    h_min = bbox[f'{n1.lower()}min']; h_max = bbox[f'{n1.lower()}max']
    v_min = bbox[f'{n2.lower()}min']; v_max = bbox[f'{n2.lower()}max']
    h_span = h_max - h_min or 1; v_span = v_max - v_min or 1
    margin = 0.10  # 10% padding
    fit_scale = min((img_size*(1-2*margin))/h_span, (img_size*(1-2*margin))/v_span)
    ch = (h_min + h_max) / 2; cv = (v_min + v_max) / 2
    off_x = int(img_size//2 - ch*fit_scale); off_y = int(img_size//2 - cv*fit_scale)

    def to_px(h, v):
        return int(round(h*fit_scale + off_x)), int(round(img_size - (v*fit_scale + off_y)))

    # trimesh mesh直接使用
    mesh = data['mesh']
    verts = data['verts']  # (N, 3) in m
    faces = data['faces']  # (M, 3) indices
    n_verts, n_faces = len(verts), len(faces)
    
    if n_faces == 0 or n_verts == 0:
        # Fallback: empty image
        img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)
        di = {'fit_scale':fit_scale, 'offset_x':off_x, 'offset_y':off_y,
              'h_min':h_min, 'h_max':h_max, 'v_min':v_min, 'v_max':v_max,
              'h_span':h_span, 'v_span':v_span,
              'to_px':to_px, 'ax1':ax1, 'ax2':ax2,
              'n1':n1, 'n2':n2}
        return img, di

    # Get face normals from trimesh
    fnorms = mesh.face_normals  # (M, 3)
    
    # Determine view normal (direction we're looking FROM)
    # XZ view: looking from +Y → front faces have normal.y > 0
    # YZ view: looking from +X → front faces have normal.x > 0
    # XY view: looking from +Z → front faces have normal.z > 0
    view_normals = {'XZ': np.array([0, 1, 0]), 'YZ': np.array([1, 0, 0]), 'XY': np.array([0, 0, 1])}
    view_n = view_normals[view]

    # Back-face culling: front faces have normal dot view_n > 0
    # Draw filled faces (gray) + edges (gray) on white background
    img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)
    
    # Project front-facing faces to 2D
    poly_2d = []
    for i, f in enumerate(faces):
        # Back-face culling
        if np.dot(fnorms[i], view_n) <= 0:
            continue
        
        v0, v1, v2 = verts[f[0]], verts[f[1]], verts[f[2]]
        p0 = to_px(v0[ax1], v0[ax2])
        p1 = to_px(v1[ax1], v1[ax2])
        p2 = to_px(v2[ax1], v2[ax2])
        
        # Cull faces outside image bounds
        min_x = min(p0[0], p1[0], p2[0])
        max_x = max(p0[0], p1[0], p2[0])
        min_y = min(p0[1], p1[1], p2[1])
        max_y = max(p0[1], p1[1], p2[1])
        if max_x < -50 or min_x > img_size+50 or max_y < -50 or min_y > img_size+50:
            continue
        
        poly_2d.append(np.array([p0, p1, p2], dtype=np.int32))
    
    # Fill front-facing faces and silhouette edges with the SAME color
    # (no visible line — filled body, clean silhouette)
    fill_color = (200, 200, 200)  # gray
    if poly_2d:
        cv2.fillPoly(img, np.array(poly_2d), color=fill_color)
    
    # Draw silhouette edges in the same color (invisible — just for clean edge definition)
    boundary = data['edges_unique']
    for e0, e1 in boundary:
        x1_v, y1_v = to_px(verts[e0, ax1], verts[e0, ax2])
        x2_v, y2_v = to_px(verts[e1, ax1], verts[e1, ax2])
        if -50<=x1_v<=img_size+50 and -50<=y1_v<=img_size+50 and -50<=x2_v<=img_size+50 and -50<=y2_v<=img_size+50:
            cv2.line(img, (x1_v,y1_v), (x2_v,y2_v), fill_color, 2)
    
    cv2.putText(img, f'{n1} →', (10, img_size-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)
    cv2.putText(img, f'{n2} ↑', (img_size-80, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,200), 1)

    di = {'fit_scale':fit_scale, 'offset_x':off_x, 'offset_y':off_y,
          'h_min':h_min, 'h_max':h_max, 'v_min':v_min, 'v_max':v_max,
          'h_span':h_span, 'v_span':v_span,
          'to_px':to_px, 'ax1':ax1, 'ax2':ax2,
          'n1':n1, 'n2':n2,
          'img_w':img.shape[1], 'img_h':img.shape[0]}   # 실제 저장된 이미지 크기
    return img, di

# ─── VLM (optional) ───

try:
    import ollama; HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

VL_PROMPT = ("Find ALL sharp convex extremities of the geometry. "
             "These are the pointed protruding ends: wing tips, fin tips, blade tips, canard tips, "
             "and in general the outermost/innermost sharp points along the longest span (top & bottom, "
             "left & right, front & back edges) where thin blade/fin/wing structures terminate. "
             "Do NOT mark smooth curves, rounded bodies, or flat surfaces. "
             "Return ONLY JSON with double quotes: {\"tips\": [{\"tip_id\": N, \"x\": pixelX, \"y\": pixelY}, ...], \"image_width\": W, \"image_height\": H}")

def get_vlm(image_path, timeout_sec=60):
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        r = ollama.chat(model='orcarouter/qwen3.8-27b-uncensored:latest',
                        messages=[{"role":"user","content":VL_PROMPT,"images":[img_bytes]}],
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

def parse_vlm(raw, img_size=1100):
    """Parse VLM response: returns (tips, real_w, real_h).
    Accepts: {image_size:[w,h],tips:[...]}, [tips:...], {tip_id,x,y} etc."""
    if not raw:
        return [], img_size, img_size
    t = raw.strip()
    # Remove markdown code block wrapper (```json or ```)
    if t.startswith('```json'):
        t = t[7:].strip()
    elif t.startswith('```'):
        t = t[3:].strip()
    if t.endswith('```'):
        t = t[:-3].strip()
    # Also try splitting by ``` and picking the JSON part
    if '```' in t:
        parts = t.split('```')
        json_part = None
        for p in parts:
            p = p.strip()
            if ('{' in p and '}' in p) or ('[' in p and ']' in p):
                json_part = p
                break
        if json_part:
            t = json_part
    bracket_start = t.find('[')
    brace_start = t.find('{')
    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):
        start, end = bracket_start, t.rfind(']')
    elif brace_start >= 0:
        start, end = brace_start, t.rfind('}')
    else:
        return [], img_size, img_size
    if start >= end:
        return [], img_size, img_size
    t = t[start:end+1]
    d = None
    try:
        d = json.loads(t)
    except:
        pass
    if d is None:
        try:
            import ast
            d = ast.literal_eval(t)
        except:
            pass
    if d is None:
        # Fallback: extract tips from plain text/JSON with regex
        import re
        tip_pattern = r'\{\s*"?tip_id"?\s*[:=]\s*(\d+)\s*,\s*"?x"?\s*[:=]\s*(\d+)\s*,\s*"?y"?\s*[:=]\s*(\d+)'
        tips_raw = re.findall(tip_pattern, t)
        if tips_raw:
            d = {'tips': [{'tip_id': int(t[0]), 'x': float(t[1]), 'y': float(t[2])} for t in tips_raw], 'image_width': img_size, 'image_height': img_size}
    if d is None:
        return [], img_size, img_size

    real_w, real_h = img_size, img_size
    items = None

    def extract_tips(obj):
        if not isinstance(obj, dict):
            return None, None
        # Try various image size keys
        imsz_w = obj.get('image_width', obj.get('imageWidth', None))
        imsz_h = obj.get('image_height', obj.get('imageHeight', None))
        if imsz_w is None:
            imsz = obj.get('image_size', obj.get('imageSize', obj.get('img_size', None)))
            if imsz is not None:
                if isinstance(imsz, (list, tuple)) and len(imsz) == 2:
                    real_w_h = int(imsz[0]), int(imsz[1])
                elif isinstance(imsz, dict):
                    real_w_h = int(imsz.get('w', imsz.get('width', img_size))), int(imsz.get('h', imsz.get('height', img_size)))
                else:
                    real_w_h = None
            else:
                real_w_h = None
        else:
            real_w_h = int(imsz_w), int(imsz_h)
        
        # Check for 'tips' array key first
        tips = obj.get('tips', None)
        if tips is not None:
            return tips, real_w_h
        
        # Fall back: single tip object with x,y
        if 'x' in obj and 'y' in obj:
            return [obj], None
        return None, None

    if isinstance(d, dict):
        tips, imsz = extract_tips(d)
        if tips is not None:
            items = tips
            if imsz:
                real_w, real_h = imsz
        elif 'bbox_2d' in d:
            items = [d]
        else:
            items = [d]
    elif isinstance(d, list):
        for item in d:
            tips, imsz = extract_tips(item)
            if tips is not None:
                items = tips
                if imsz:
                    real_w, real_h = imsz
                break
        if items is None:
            items = d

    if not isinstance(items, list):
        return [], real_w, real_h

    res = []
    for tp in items:
        tid = tp.get('tip_id', tp.get('id', len(res) + 1))
        x = tp.get('x')
        y = tp.get('y')
        if x is not None and y is not None:
            tid = int(tid) if tid is not None else len(res) + 1
            res.append({'tip_id': tid, 'x': float(x), 'y': float(y)})
            continue
        x1 = tp.get('x1')
        y1 = tp.get('y1')
        x2 = tp.get('x2')
        y2 = tp.get('y2')
        bb2d = tp.get('bbox_2d', tp.get('box_2d'))
        if bb2d and len(bb2d) == 4 and x1 is None:
            x1, y1, x2, y2 = bb2d[0], bb2d[1], bb2d[2], bb2d[3]
        if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
            try:
                tid = int(tid) if tid is not None else len(res) + 1
                res.append({'tip_id': tid, 'x': float(x1), 'y': float(y1)})
            except:
                pass
    return res, real_w, real_h

def render_iso(data, tips, sz=800):
    """Isometric view: filled silhouette (no wireframe) + orange tip markers (like annotated views).

    Camera: looking FROM (-1,-1,1) direction (left, behind, above) toward origin.
    data: load_stl() 결과 dict
    tips: 3D tip 좌표 리스트 (m)
    """
    # 모든 값 m 통일
    img = np.full((sz, sz, 3), 255, dtype=np.uint8)
    bbox = data['bbox']
    c = bbox['center']; me = max(bbox['xl'], bbox['yl'], bbox['zl']) or 1
    sc = sz * 0.7 / me
    # 等角投影: 3 axis가 모두 30° — 모든 축이 동등하게 보임
    a = np.sqrt(3.0) / 3.0; b = 1.0 / 3.0
    def _p(p):
        tx, ty, tz = p[0] - c[0], p[1] - c[1], p[2] - c[2]
        # Camera looks from (-1,-1,1) → screen x = X-Y, screen y = (X+Y+2Z)/√6
        return ((tx - ty) * sc * a + sz // 2,
                (tx + ty + 2.0 * tz) * sc * b + sz // 2)

    verts = data['verts']
    faces = data['faces']
    # View direction: camera at (-1,-1,1) → looking toward (1,1,-1)/√3
    view_dir = np.array([1.0, 1.0, -1.0]) / np.sqrt(3.0)

    # Painter's order: sort faces by mean depth (far first, near last)
    # depth = dot(view_dir, r) — larger = closer to camera
    depth_per_vert = verts @ view_dir
    fnorms = data['mesh'].face_normals  # (M, 3)
    face_depth = depth_per_vert[faces].mean(axis=1)
    order = np.argsort(-face_depth)  # far (small depth) → near (large depth)

    fill_color = (90, 90, 90)  # dark gray solid body (no wireframe)
    for i in order:
        if np.dot(fnorms[i], view_dir) <= 0:
            continue  # back-face cull → closed body, no internal lines
        f = faces[i]
        pts = np.array([_p(verts[f[0]]), _p(verts[f[1]]), _p(verts[f[2]])], dtype=np.int32)
        cv2.fillPoly(img, [pts], color=fill_color)

    # Draw tip markers: orange circles (same style as annotated views)
    for k, tip in enumerate(tips):
        x, y = _p(tip)
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < sz and 0 <= yi < sz):
            continue
        # NOTE: cv2.circle/putText use BGR order (orange = B0 G165 R255)
        cv2.circle(img, (xi, yi), 14, (0, 165, 255), 1)    # outer ring
        cv2.circle(img, (xi, yi), 10, (0, 165, 255), -1)   # orange fill
        cv2.putText(img, f"tip{k+1}", (xi + 18, yi - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 220), 1)
    return img

# ─── Triangulate ───

def triangulate(tips_by_view, verts, bbox):
    """3-view triangulation + dedup.
    
    tips_by_view: {view_name: [tip_2d_array, ...]} (m)
    verts: (N, 3) vertex array (m)
    bbox: bounding box dict (m)
    """
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
            if verts.size > 0:
                cols = [j for j in range(3) if mask[j]]
                dists = np.linalg.norm(verts[:, cols] - np.array(partial)[cols], axis=1)
                best_j = np.argmin(dists)
            else:
                best_j = 0
            for j in range(3):
                if mask[j]:
                    continue
                val = float(verts[best_j, j]) if verts.size > 0 else 0.0
                if j == 0: x = val
                elif j == 1: y = val
                else: z = val
            result.append(np.array([x or 0, y or 0, z or 0]))
    
    final = []
    for t in result:
        if all(np.linalg.norm(t-f)>=0.05 for f in final): final.append(t)  # 5cm threshold (m)
    
    # --- Y-Z Dedup + Max-X Filter ---
    # 조건: y, z가 tol(=bbox_max_span*0.05) 이내이면 하나로 취급 → x가 제일 큰 것만 남김
    tol = max(bbox['xl'], bbox['yl'], bbox['zl']) * 0.05
    deduped = []
    for t in result:
        placed = False
        for i, d in enumerate(deduped):
            dy = abs(float(t[1]) - float(d[1]))
            dz = abs(float(t[2]) - float(d[2]))
            dx = abs(float(t[0]) - float(d[0]))
            if dy < tol and dz < tol and dx < tol:
                # x, y, z가 모두 tol 이내 → 하나의 지점
                # x가 큰 것만 남김 (wing tip은 X max 방향)
                if float(t[0]) > float(d[0]):
                    deduped[i] = t
                placed = True
                break
        if not placed:
            deduped.append(t)
    
    return deduped

# ─── Main ───

def main():
    p = argparse.ArgumentParser()
    p.add_argument('stl_file')
    p.add_argument('--no-vlm', action='store_true', help='Skip VLM, use CAD tip detection only')
    p.add_argument('--tips', type=str, help='Manual tips as JSON string for testing')
    args = p.parse_args()
    
    if not os.path.exists(args.stl_file):
        print(f"Error: {args.stl_file} not found"); sys.exit(1)
    
    sd = os.path.dirname(os.path.abspath(args.stl_file))
    sn = os.path.splitext(os.path.basename(args.stl_file))[0]
    
    print(f"{'='*60}\nSTL Tip Detection\n{'='*60}\nSTL: {args.stl_file}")
    
    data = load_stl(args.stl_file)
    if data is None: print("Error: load failed"); sys.exit(1)
    bbox = data['bbox']; verts = data['verts']
    print(f"BBox(m): X[{bbox['xmin']:.3f}..{bbox['xmax']:.3f}] Y[{bbox['ymin']:.3f}..{bbox['ymax']:.3f}] Z[{bbox['zmin']:.3f}..{bbox['zmax']:.3f}]")
    print(f"BBox(mm): X[{bbox['xmin']*1000:.1f}..{bbox['xmax']*1000:.1f}] Y[{bbox['ymin']*1000:.1f}..{bbox['ymax']*1000:.1f}] Z[{bbox['zmin']*1000:.1f}..{bbox['zmax']*1000:.1f}]\n")
    
    tips_by_view = {}
    img_paths = {}
    img_size = 1100  # 1100x1100, 10% padding for tip bbox safety
    
    for vn in ['XZ','YZ','XY']:
        img, di = render_ortho_stl(data, vn, img_size=img_size)
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
            print(f"  [VLM RESPONSE] {raw}")
            try:
                tips_vlm, real_w, real_h = parse_vlm(raw)
                print(f"  VLM parsed: {len(tips_vlm)} tip(s)")
            except Exception as e:
                print(f"  [VLM PARSE ERROR] {type(e).__name__}: {e}")
            
            # VLM 분석 이미지 크기 기반 스케일 보정
            # VLM이 real_w x real_h 기준으로 pixel을 반환 → 실제 이미지(img_size)에 맞게 보정
            tips_vlm_scaled = []
            if real_w != img_size or real_h != img_size:
                scale_w = img_size / real_w
                scale_h = img_size / real_h
                for tp in tips_vlm:
                    tips_vlm_scaled.append({
                        'tip_id': tp['tip_id'],
                        'x': tp['x'] * scale_w,   # VLM 원본 → 이미지 상 pixel
                        'y': tp['y'] * scale_h
                    })
                    print(f"  Scale correction: {real_w}x{real_h} → {img_size}x{img_size} (sx={scale_w:.3f}, sy={scale_h:.3f})")
            else:
                tips_vlm_scaled = [{'tip_id': tp['tip_id'], 'x': tp['x'], 'y': tp['y']} for tp in tips_vlm]
            
            # Draw VLM tips on the image using SCALE-TO-IMAGE pixel coordinates
            if tips_vlm_scaled:
                annot_path = op.replace('.png', '_annotated.png')
                try:
                    img_pil = Image.open(op).convert("RGB")
                    draw = ImageDraw.Draw(img_pil)
                    width, height = img_pil.size
                    for tip in tips_vlm_scaled:
                        tx, ty = int(tip['x']), int(tip['y'])
                        # 주황색 큰 원: 외경 r=14 선 두께 1, 내경 r=10 채움
                        draw.ellipse([tx-14, ty-14, tx+14, ty+14], outline="orange", width=1)
                        draw.ellipse([tx-10, ty-10, tx+10, ty+10], fill="orange")
                        draw.text((tx+40, ty-10), f"tip{tip['tip_id']}", fill="orange")
                    img_pil.save(annot_path)
                    print(f"    annotated PNG saved: {annot_path}")
                except Exception as e:
                    print(f"  [annotate error] {e}")
        else:
            tips_vlm_scaled = []
            print(f"  [VLM] no response")
        
        # pixel → CAD(m): 직결 변환
        # tips_vlm_scaled: 이미지 상의 pixel 좌표 (1100 기준)
        # CAD 역산: 이미지를 기준으로 하므로 tips_vlm_scaled 사용
        tips = []
        for tp in tips_vlm_scaled:
            tid = tp['tip_id']
            px = tp['x']
            py = tp['y']
            CAD_h_m = (px - di['offset_x']) / di['fit_scale']
            CAD_v_m = (img_size - py - di['offset_y']) / di['fit_scale']
            tips.append(np.array([CAD_h_m, CAD_v_m, 0.0]))  # placeholder z
            print(f"  tip#{tid}: pixel({px:.0f},{py:.0f}) → CADm({CAD_h_m:.3f},{CAD_v_m:.3f})")
        tips_by_view[vn] = tips
        print(f"  [{vn}] {len(tips)} snapped tip(s)\n")
    
    if not any(tips_by_view.values()):
        print("No tips detected. Try: --no-vlm to skip VLM, or check VLM output.")
        sys.exit(1)
    
    # Triangulate (tips_by_view: m, verts: m, bbox: m)
    tips_3d = triangulate(tips_by_view, verts, bbox)
    print(f"\n{len(tips_3d)} 3D tip(s):")
    for i, t in enumerate(tips_3d):
        print(f"  Tip {i+1}: ({t[0]:.3f}, {t[1]:.3f}, {t[2]:.3f}) m")
    
    if tips_3d:
        csv_p = os.path.join(sd, f'{sn}_tip_points.csv')
        with open(csv_p,'w') as f:
            for t in tips_3d: f.write(f'{t[0]:.6f},{t[1]:.6f},{t[2]:.6f}\n')
        print(f"\nCSV: {csv_p}")
        
        iso = render_iso(data, tips_3d)
        png_p = os.path.join(sd, f'{sn}_tip.png')
        cv2.imwrite(png_p, iso)
        print(f"PNG: {png_p}")
    
    print(f"\n{'='*60}\nDone!\n{'='*60}")

if __name__ == '__main__':
    main()
