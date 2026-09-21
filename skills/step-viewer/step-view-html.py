#!/usr/bin/env python3
"""
step-view-html.py -- STEP 파일을 정적 HTML 뷰어로 변환 + tip 검출

Usage:
  python step-view-html.py <input.stp> [--tol <tol_m>] [--method convex|projection|radial_x]
  python step-view-html.py LC62-50H.stp
  python step-view-html.py LC62-50H.stp --tol 0.5
  python step-view-html.py LC62-50H.stp --method projection

Output:
  LC62-50H.html       -- 정적 HTML 뷰어 (STEP mesh + tip points)
  LC62-50H_tip_points.csv  -- tip points (m unit)
"""

import sys, os, numpy as np, csv, re, argparse

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery must be installed")
    sys.exit(1)

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh must be installed")
    sys.exit(1)

try:
    from scipy.spatial import ConvexHull
    HAS_CONVEXHULL = True
except ImportError:
    HAS_CONVEXHULL = False

try:
    from sklearn.cluster import DBSCAN
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False

if not HAS_SKLEARN:
    try:
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import pdist
        HAS_LINKAGE = True
    except ImportError:
        HAS_LINKAGE = False


def read_step_header_unit(path):
    with open(path, 'r') as f:
        for line in f:
            if 'SI_UNIT' in line and 'LENGTH_UNIT' in line:
                m = re.search(r'SI_UNIT\([.\$\s,]*\.(METRE|MMETER)\.', line)
                if m:
                    return 'M' if m.group(1) == 'METRE' else 'MM'
    return None


def step_to_uniform_mesh(shape_mm, target_face_area=None):
    if target_face_area is None:
        all_faces = list(shape_mm.Faces())
        face_areas = [f.Area() for f in all_faces if hasattr(f, 'Area')]
        target_face_area = np.mean(face_areas) if face_areas else 100.0
    target_size = np.sqrt(target_face_area)
    try:
        verts_list, faces_list = shape_mm.tessellate(target_size)
        if verts_list is None or len(verts_list) == 0:
            verts_list, faces_list = shape_mm.tessellate(1.0)
    except Exception:
        verts_list, faces_list = shape_mm.tessellate(1.0)
    verts = np.array([[v.x, v.y, v.z] for v in verts_list])
    faces = np.array(faces_list)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    if mesh.is_empty:
        verts_list, faces_list = shape_mm.tessellate(1.0)
        verts = np.array([[v.x, v.y, v.z] for v in verts_list])
        faces = np.array(faces_list)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    return mesh


def direction_aware_merge(candidates, tol_mm):
    tips = []
    for candidate in candidates:
        merged = False
        for i, existing in enumerate(tips):
            diffs = np.abs(candidate - existing)
            sorted_diffs = np.sort(diffs)
            if sorted_diffs[2] >= tol_mm and sorted_diffs[0] < tol_mm and sorted_diffs[1] < tol_mm:
                tips[i] = (existing + candidate) / 2.0
                merged = True
                break
        if not merged:
            tips.append(candidate.copy())
    return tips


def find_tip_convex(mesh_vertices, mesh_faces, tol_mm):
    if not HAS_CONVEXHULL:
        return []
    vertices = np.array(mesh_vertices)
    hull = ConvexHull(vertices)
    hull_simplices = hull.simplices
    hull_faces_verts = vertices[hull_simplices]
    hull_normals = np.cross(
        hull_faces_verts[:, 1] - hull_faces_verts[:, 0],
        hull_faces_verts[:, 2] - hull_faces_verts[:, 0]
    )
    norm_n = np.linalg.norm(hull_normals, axis=1, keepdims=True)
    norm_n[norm_n == 0] = 1.0
    hull_normals /= norm_n
    n_verts = len(vertices)
    distances = np.full(n_verts, np.inf)
    chunk_size = 5000
    for start in range(0, n_verts, chunk_size):
        end = min(start + chunk_size, n_verts)
        chunk = vertices[start:end, np.newaxis, :]
        face_pts = hull_faces_verts[:, 0, :]
        v_to_v = chunk - face_pts[np.newaxis, :, :]
        dist_normal = np.sum(v_to_v * hull_normals[np.newaxis, :, :], axis=2)
        proj_on_face = v_to_v - dist_normal[:, :, np.newaxis] * hull_normals[np.newaxis, :, :]
        dist_on_face = np.linalg.norm(proj_on_face, axis=2)
        closest_idx = np.argmin(dist_on_face, axis=1)
        distances[start:end] = dist_normal[np.arange(end - start), closest_idx]
    pos_mask = distances > 0
    if pos_mask.sum() == 0:
        return []
    pos_dists = distances[pos_mask]
    pos_verts = vertices[pos_mask]
    threshold = np.percentile(pos_dists, 80)
    tip_mask = pos_dists >= threshold
    tip_candidates = pos_verts[tip_mask]
    if len(tip_candidates) == 0:
        return []
    return direction_aware_merge(tip_candidates, tol_mm)


def find_tip_points_radial_x(mesh_vertices, mesh_faces, tol_mm, xl_mm=None):
    vertices = np.array(mesh_vertices)
    bb_min = vertices.min(axis=0)
    bb_max = vertices.max(axis=0)
    xl = xl_mm if xl_mm else bb_max[0] - bb_min[0]
    center_y = (bb_min[1] + bb_max[1]) / 2.0
    center_z = (bb_min[2] + bb_max[2]) / 2.0
    n_x_slices = min(20, max(5, int(xl / (xl / 20.0))))
    x_step = xl / n_x_slices
    n_angles = 360
    angles = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    cos_angles = np.cos(angles)
    sin_angles = np.sin(angles)
    vertex_slice_idx = np.clip(np.floor((vertices[:, 0] - bb_min[0]) / x_step).astype(int), 0, n_x_slices - 1)
    all_radial = [None] * n_x_slices
    for si in range(n_x_slices):
        slice_verts = vertices[vertex_slice_idx == si]
        if slice_verts.shape[0] < 10:
            continue
        dy = slice_verts[:, 1] - center_y
        dz = slice_verts[:, 2] - center_z
        radial_proj = dy[:, np.newaxis] * cos_angles[np.newaxis, :] + dz[:, np.newaxis] * sin_angles[np.newaxis, :]
        positive_mask = radial_proj > 0
        radial_at_angle = np.full(n_angles, np.nan)
        for ai in range(n_angles):
            pos_in_ai = positive_mask[:, ai]
            if pos_in_ai.sum() > 0:
                radial_at_angle[ai] = radial_proj[pos_in_ai, ai].min()
        all_radial[si] = radial_at_angle
    tip_candidates_mm = []
    for xi in range(1, n_x_slices):
        prev_r = all_radial[xi - 1]
        curr_r = all_radial[xi]
        if prev_r is None or curr_r is None:
            continue
        diff = curr_r - prev_r
        valid_mask = ~np.isnan(diff)
        if valid_mask.sum() < 10:
            continue
        prev_max = prev_r[valid_mask].max()
        sharp_decrease_idx = np.where((diff < -prev_max * 0.10) & valid_mask)[0]
        for ai in sharp_decrease_idx:
            cos_a, sin_a = cos_angles[ai], sin_angles[ai]
            slice_verts = vertices[vertex_slice_idx == (xi - 1)]
            if slice_verts.shape[0] == 0:
                continue
            dy_prev = slice_verts[:, 1] - center_y
            dz_prev = slice_verts[:, 2] - center_z
            proj_prev = dy_prev * cos_a + dz_prev * sin_a
            pos_mask_prev = proj_prev > 0
            if pos_mask_prev.sum() == 0:
                continue
            local_idx = np.where(vertex_slice_idx == (xi - 1))[0][np.argmax(proj_prev[pos_mask_prev])]
            tip_candidates_mm.append(vertices[local_idx].copy())
    if len(tip_candidates_mm) == 0:
        return []
    from collections import defaultdict
    tips_by_angle = defaultdict(list)
    for tip in tip_candidates_mm:
        angle_deg = np.degrees(np.arctan2(tip[2] - center_z, tip[1] - center_y)) % 360
        tips_by_angle[int(round(angle_deg)) % 360].append(tip)
    final_tips = []
    for angle_bin in sorted(tips_by_angle.keys()):
        angle_tips = sorted(tips_by_angle[angle_bin], key=lambda t: t[0])
        if len(angle_tips) == 1:
            final_tips.append(angle_tips[0])
            continue
        unique_tips = []
        for tip in angle_tips:
            if not unique_tips or tip[0] - unique_tips[-1][0] > x_step * 0.5:
                unique_tips.append(tip.copy())
            else:
                unique_tips[-1] = np.array([max(unique_tips[-1][0], tip[0]),
                                             (unique_tips[-1][1] + tip[1]) / 2.0,
                                             (unique_tips[-1][2] + tip[2]) / 2.0])
        radials = [np.sqrt((t[1]-center_y)**2 + (t[2]-center_z)**2) for t in unique_tips]
        for i in range(1, len(radials)):
            if radials[i] - radials[i-1] < 0:
                final_tips.append(unique_tips[i-1].copy())
                while i + 1 < len(radials) and radials[i+1] - radials[i] < 0:
                    i += 1
                while i + 1 < len(radials) and radials[i+1] - radials[i] > 0:
                    i += 1
    if len(final_tips) == 0:
        return []
    merged = []
    for tip in final_tips:
        found = False
        for i, existing in enumerate(merged):
            dx = abs(tip[0] - existing[0])
            if dx < tol_mm and np.sqrt((tip[1]-existing[1])**2 + (tip[2]-existing[2])**2) < tol_mm:
                merged[i] = (existing + tip) / 2.0
                found = True
                break
        if not found:
            merged.append(tip.copy())
    return [np.array(t) for t in merged]


def find_tip_projection(mesh_vertices, mesh_faces, tol_mm):
    mesh = trimesh.Trimesh(vertices=mesh_vertices, faces=mesh_faces, process=False)
    vertices, faces = mesh.vertices, mesh.faces
    tip_candidates = []
    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
        verts_2d = vertices[:, [axis1, axis2]]
        origin_2d = vertices[faces].mean(axis=1)[:, [axis1, axis2]].mean(axis=0)
        radial = np.linalg.norm(verts_2d - origin_2d, axis=1)
        for pct in [5, 10, 20, 50, 70, 80, 90, 95]:
            threshold = np.percentile(radial, pct)
            high_mask = radial > threshold
            if high_mask.sum() == 0:
                continue
            high_coords = verts_2d[high_mask]
            high_indices = np.where(high_mask)[0]
            high_radial = radial[high_mask]
            if len(high_indices) < 10:
                continue
            if len(high_indices) > 5000:
                rng = np.random.RandomState(42)
                idx = rng.choice(len(high_indices), 5000, replace=False)
                high_coords, high_indices, high_radial = high_coords[idx], high_indices[idx], high_radial[idx]
            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale
            eps_val = max(0.05, min(0.3 / max(scale.min(), 1e-6), 0.999))
            if HAS_SKLEARN:
                clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
            elif HAS_LINKAGE:
                dist_matrix = pdist(features)
                Z = linkage(dist_matrix, method='complete')
                clustering = type('obj', (object,), {'labels_': fcluster(Z, t=eps_val, criterion='distance')})()
            else:
                continue
            for label in set(clustering.labels_):
                if label == -1:
                    continue
                cm_mask = clustering.labels_ == label
                cluster_idx_2d = high_indices[cm_mask]
                peak_idx_3d = cluster_idx_2d[np.argmax(high_radial[cm_mask])]
                tip_candidates.append(vertices[peak_idx_3d].copy())
    tips = []
    for t in tip_candidates:
        if not any(np.linalg.norm(t - q) < tol_mm for q in tips):
            tips.append(t)
    return tips[:20]


def write_tip_csv(tip_points_m, output_path):
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        for tp in tip_points_m:
            writer.writerow(["%.6f" % tp[0], "%.6f" % tp[1], "%.6f" % tp[2]])
    print("Output: %s (%d tip points, m unit)" % (output_path, len(tip_points_m)))


def generate_html(mesh_vertices, mesh_faces, tip_points_m, tip_color="#ff3333", model_color="#4a90d9", bgcolor="#1a1a2e"):
    """Generate static HTML with Plotly 3D mesh + tip markers."""
    vx = ",".join("%.6f" % v for v in mesh_vertices[:, 0])
    vy = ",".join("%.6f" % v for v in mesh_vertices[:, 1])
    vz = ",".join("%.6f" % v for v in mesh_vertices[:, 2])
    fx = ",".join("%d" % v for v in mesh_faces[:, 0])
    fy = ",".join("%d" % v for v in mesh_faces[:, 1])
    fz = ",".join("%d" % v for v in mesh_faces[:, 2])

    tip_n = len(tip_points_m)
    tx_str = ",".join("%.6f" % tp[0] for tp in tip_points_m) if tip_n > 0 else ""
    ty_str = ",".join("%.6f" % tp[1] for tp in tip_points_m) if tip_n > 0 else ""
    tz_str = ",".join("%.6f" % tp[2] for tp in tip_points_m) if tip_n > 0 else ""

    tip_text_js = "[]"
    if tip_n > 0:
        parts = []
        for i, tp in enumerate(tip_points_m):
            parts.append("'tip%d: (%.4f, %.4f, %.4f) m'" % (i+1, tp[0], tp[1], tp[2]))
        tip_text_js = "[" + ",".join(parts) + "]"

    H = []  # HTML lines
    H.append("<!DOCTYPE html>")
    H.append('<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">')
    H.append('<title>STEP 3D Viewer</title><script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>')
    H.append("<style>")
    H.append("* { margin:0; padding:0; box-sizing:border-box; }")
    H.append("body { background:%s; color:#e0e0e0; font-family:'Segoe UI',sans-serif; overflow:hidden; }" % bgcolor)
    H.append("#viewer { width:100vw; height:100vh; }")
    H.append("#info { position:fixed; top:10px; left:10px; z-index:10; background:rgba(0,0,0,0.7); padding:12px 16px; border-radius:8px; font-size:13px; line-height:1.6; max-width:300px; backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.1); }")
    H.append("#info h3 { margin:0 0 6px 0; color:#4a90d9; font-size:15px; }")
    H.append("#info .row { display:flex; justify-content:space-between; }")
    H.append("#info .label { color:#999; } #info .value { color:#fff; font-weight:600; }")
    H.append("#legend { position:fixed; bottom:10px; left:10px; z-index:10; background:rgba(0,0,0,0.7); padding:8px 14px; border-radius:8px; font-size:12px; border:1px solid rgba(255,255,255,0.1); }")
    H.append(".legend-item { display:flex; align-items:center; gap:6px; margin:2px 0; } .legend-dot { width:10px; height:10px; border-radius:50%; }")
    H.append("#controls { position:fixed; top:10px; right:10px; z-index:10; display:flex; gap:6px; }")
    H.append("#controls button { background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#e0e0e0; padding:6px 12px; border-radius:6px; cursor:pointer; font-size:12px; } #controls button:hover { background:rgba(255,255,255,0.2); }")
    H.append("#tip-info { position:fixed; top:10px; right:10px; z-index:10; background:rgba(0,0,0,0.8); padding:10px 14px; border-radius:8px; font-size:12px; border:1px solid rgba(255,50,50,0.3); display:none; max-height:60vh; overflow-y:auto; min-width:200px; } #tip-info.show { display:block; } #tip-info h4 { color:#ff3333; margin:0 0 6px 0; }")
    H.append("</style></head><body>")
    H.append('<div id="viewer"></div>')
    H.append('<div id="info"><h3>STEP Viewer</h3><div class="row"><span class="label">Vertices</span><span class="value" id="nverts">-</span></div><div class="row"><span class="label">Faces</span><span class="value" id="nfaces">-</span></div><div class="row"><span class="label">Tips</span><span class="value" id="ntips">-</span></div></div>')
    H.append('<div id="legend"><div class="legend-item"><div class="legend-dot" style="background:%s"></div><span>STEP Model</span></div><div class="legend-item"><div class="legend-dot" style="background:%s"></div><span>Tip Point</span></div></div>' % (model_color, tip_color))
    H.append('<div id="tip-info"><h4>Tip Points</h4><div id="tip-list"></div></div>')
    H.append('<div id="controls"><button onclick="resetCamera()">Reset</button><button onclick="toggleTips()">Toggle Tips</button></div>')

    # JS
    J = []
    J.append("var vx=[%s],vy=[%s],vz=[%s],fx=[%s],fy=[%s],fz=[%s];" % (vx, vy, vz, fx, fy, fz))
    J.append("var tipX=[%s],tipY=[%s],tipZ=[%s];" % (tx_str, ty_str, tz_str))
    J.append("var tipN=%d,tipText=%s;" % (tip_n, tip_text_js))
    J.append("document.getElementById('nverts').textContent=vx.length.toLocaleString();")
    J.append("document.getElementById('nfaces').textContent=(fx.length/3).toLocaleString();")
    J.append("document.getElementById('ntips').textContent=tipN;")
    J.append("var meshTrace={type:'mesh3d',x:vx,y:vy,z:vz,i:fx,j:fy,k:fz,color:'%s',flatshading:true,opacity:0.85,facecolor:'rgb(74,144,217)',lighting:{ambient:0.4,diffuse:0.6,specular:0.3,roughness:0.5,fresnel:0.2},name:'STEP Model'};" % model_color)
    J.append("var traces=[meshTrace];")
    J.append("if(tipN>0){traces.push({type:'scatter3d',mode:'markers',x:tipX,y:tipY,z:tipZ,marker:{size:8,color:'%s',symbol:'circle',line:{width:2,color:'white'}},text:tipText,hoverinfo:'text',name:'Tip Points'})}" % tip_color)
    J.append("Plotly.newPlot('viewer',traces,{scene:{xaxis:{showgrid:false,showticklabels:false},yaxis:{showgrid:false,showticklabels:false},zaxis:{showgrid:false,showticklabels:false},bgcolor:'%s',camera:{eye:{x:1.5,y:1.5,z:1.5}}},margin:{l:0,r:0,t:0,b:0},showlegend:false},{responsive:true,displayModeBar:false});" % bgcolor)
    J.append("var tipsVisible=true;")
    J.append("function resetCamera(){Plotly.relayout('viewer',{'scene.camera.eye':{x:1.5,y:1.5,z:1.5}});}")
    J.append("function toggleTips(){tipsVisible=!tipsVisible;var ti=traces.findIndex(function(t){return t.name==='Tip Points';});if(ti>=0){Plotly.restyle('viewer',{visible:tipsVisible?true:'legendonly'},[ti]);}document.getElementById('tip-info').classList.toggle('show',tipsVisible);if(tipsVisible)updateTipList();}")
    bullet = '\u25cf';
    J.append("if(tipN>0)updateTipList();")

    H.append("<script>" + J[-1].replace("var tipN=", "").replace("tipX=[", "var tipX=[").replace("tipY=[", "tipY=[").replace("tipZ=[", "tipZ=[") + "</script></body></html>")
    
    # Rebuild properly
    return _build_html(vx, vy, vz, fx, fy, fz, tx_str, ty_str, tz_str, tip_n, tip_text_js, model_color, tip_color, bgcolor)


def _build_html(vx, vy, vz, fx, fy, fz, tx_str, ty_str, tz_str, tip_n, tip_text_js, model_color, tip_color, bgcolor):
    """Build HTML string from components."""
    lines = []
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">')
    lines.append('<title>STEP 3D Viewer</title><script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>')
    lines.append("<style>")
    lines.append("* { margin:0; padding:0; box-sizing:border-box; }")
    lines.append("body { background:%s; color:#e0e0e0; font-family:'Segoe UI',sans-serif; overflow:hidden; }" % bgcolor)
    lines.append("#viewer { width:100vw; height:100vh; }")
    lines.append("#info { position:fixed; top:10px; left:10px; z-index:10; background:rgba(0,0,0,0.7); padding:12px 16px; border-radius:8px; font-size:13px; line-height:1.6; max-width:300px; backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,0.1); }")
    lines.append("#info h3 { margin:0 0 6px 0; color:#4a90d9; font-size:15px; }")
    lines.append("#info .row { display:flex; justify-content:space-between; }")
    lines.append("#info .label { color:#999; } #info .value { color:#fff; font-weight:600; }")
    lines.append("#legend { position:fixed; bottom:10px; left:10px; z-index:10; background:rgba(0,0,0,0.7); padding:8px 14px; border-radius:8px; font-size:12px; border:1px solid rgba(255,255,255,0.1); }")
    lines.append(".legend-item { display:flex; align-items:center; gap:6px; margin:2px 0; } .legend-dot { width:10px; height:10px; border-radius:50%; }")
    lines.append("#controls { position:fixed; top:10px; right:10px; z-index:10; display:flex; gap:6px; }")
    lines.append("#controls button { background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#e0e0e0; padding:6px 12px; border-radius:6px; cursor:pointer; font-size:12px; } #controls button:hover { background:rgba(255,255,255,0.2); }")
    lines.append("#tip-info { position:fixed; top:10px; right:10px; z-index:10; background:rgba(0,0,0,0.8); padding:10px 14px; border-radius:8px; font-size:12px; border:1px solid rgba(255,50,50,0.3); display:none; max-height:60vh; overflow-y:auto; min-width:200px; } #tip-info.show { display:block; } #tip-info h4 { color:#ff3333; margin:0 0 6px 0; }")
    lines.append("</style></head><body>")
    lines.append('<div id="viewer"></div>')
    lines.append('<div id="info"><h3>STEP Viewer</h3><div class="row"><span class="label">Vertices</span><span class="value" id="nverts">-</span></div><div class="row"><span class="label">Faces</span><span class="value" id="nfaces">-</span></div><div class="row"><span class="label">Tips</span><span class="value" id="ntips">-</span></div></div>')
    lines.append('<div id="legend"><div class="legend-item"><div class="legend-dot" style="background:%s"></div><span>STEP Model</span></div><div class="legend-item"><div class="legend-dot" style="background:%s"></div><span>Tip Point</span></div></div>' % (model_color, tip_color))
    lines.append('<div id="tip-info"><h4>Tip Points</h4><div id="tip-list"></div></div>')
    lines.append('<div id="controls"><button onclick="resetCamera()">Reset</button><button onclick="toggleTips()">Toggle Tips</button></div>')
    
    # JS
    js = "var vx=[%s],vy=[%s],vz=[%s],fx=[%s],fy=[%s],fz=[%s];" % (vx, vy, vz, fx, fy, fz)
    js += "\nvar tipX=[%s],tipY=[%s],tipZ=[%s];" % (tx_str, ty_str, tz_str)
    js += "\nvar tipN=%d,tipText=%s;" % (tip_n, tip_text_js)
    js += "\ndocument.getElementById('nverts').textContent=vx.length.toLocaleString();"
    js += "\ndocument.getElementById('nfaces').textContent=(fx.length/3).toLocaleString();"
    js += "\ndocument.getElementById('ntips').textContent=tipN;"
    js += "\nvar meshTrace={type:'mesh3d',x:vx,y:vy,z:vz,i:fx,j:fy,k:fz,color:'%s',flatshading:true,opacity:0.85,facecolor:'rgb(74,144,217)',lighting:{ambient:0.4,diffuse:0.6,specular:0.3,roughness:0.5,fresnel:0.2},name:'STEP Model'};" % model_color
    js += "\nvar traces=[meshTrace];"
    js += "\nif(tipN>0){traces.push({type:'scatter3d',mode:'markers',x:tipX,y:tipY,z:tipZ,marker:{size:8,color:'%s',symbol:'circle',line:{width:2,color:'white'}},text:tipText,hoverinfo:'text',name:'Tip Points'})}" % tip_color
    js += "\nPlotly.newPlot('viewer',traces,{scene:{xaxis:{showgrid:false,showticklabels:false},yaxis:{showgrid:false,showticklabels:false},zaxis:{showgrid:false,showticklabels:false},bgcolor:'%s',camera:{eye:{x:1.5,y:1.5,z:1.5}}},margin:{l:0,r:0,t:0,b:0},showlegend:false},{responsive:true,displayModeBar:false});" % bgcolor
    js += "\nvar tipsVisible=true;"
    js += "\nfunction resetCamera(){Plotly.relayout('viewer',{'scene.camera.eye':{x:1.5,y:1.5,z:1.5}});}"
    js += "\nfunction toggleTips(){tipsVisible=!tipsVisible;var ti=traces.findIndex(function(t){return t.name==='Tip Points';});if(ti>=0){Plotly.restyle('viewer',{visible:tipsVisible?true:'legendonly'},[ti]);}document.getElementById('tip-info').classList.toggle('show',tipsVisible);if(tipsVisible)updateTipList();}"
    # tip list - use bullet char directly
    bullet = "\u25cf"  # black circle
    js += "\nfunction updateTipList(){var l=document.getElementById('tip-list'),h='';for(var i=0;i<tipX.length;i++){h+='<div style=\'margin:2px 0\'><span style=\'color:#ff3333\'>' + bullet + '</span> tip'+(i+1)+': ('+parseFloat(tipX[i]).toFixed(4)+', '+parseFloat(tipY[i]).toFixed(4)+', '+parseFloat(tipZ[i]).toFixed(4)+') m</div>';}}l.innerHTML=h;}"
    js += "\nif(tipN>0)updateTipList();"
    
    lines.append("<script>" + js + "</script>")
    lines.append("</body></html>")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='STEP file to HTML viewer + tip detection')
    parser.add_argument('input', help='Input STEP file path')
    parser.add_argument('--tol', type=float, default=None, help='tip merge tolerance (m)')
    parser.add_argument('--method', type=str, default='convex', choices=['convex', 'projection', 'radial_x'],
                        help='tip detection method')
    parser.add_argument('--h1', type=float, default=0.0001, help='first BL cell height (m)')
    parser.add_argument('--nlayers', type=int, default=10, help='BL layer count')
    parser.add_argument('--growth', type=float, default=1.3, help='BL growth rate')
    parser.add_argument('--output-dir', type=str, default=None, help='output directory (default: same as STEP file)')
    parser.add_argument('--model-color', type=str, default='#4a90d9', help='model color (HTML)')
    parser.add_argument('--tip-color', type=str, default='#ff3333', help='tip color (HTML)')
    parser.add_argument('--bgcolor', type=str, default='#1a1a2e', help='background color (HTML)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("ERROR: file not found -- %s" % args.input)
        sys.exit(1)

    basename = os.path.splitext(os.path.basename(args.input))[0]
    out_dir = args.output_dir if args.output_dir else os.path.dirname(os.path.abspath(args.input))
    html_path = os.path.join(out_dir, basename + ".html")
    csv_path = os.path.join(out_dir, basename + "_tip_points.csv")

    print("Loading STEP file: %s" % args.input)

    declared_unit = read_step_header_unit(args.input)
    used_unit = declared_unit if declared_unit else 'MM'
    print("  STEP header unit: %s" % used_unit)

    shape_mm = cq.importers.importStep(args.input, unit='MM').val()
    print("  Loaded as mm")

    face_count = len(list(shape_mm.Faces()))
    edge_count = len(list(shape_mm.Edges()))
    print("  Faces: %d, Edges: %d" % (face_count, edge_count))

    bb = shape_mm.BoundingBox()
    bb_extent_mm = [bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin]
    bb_extent_m = [e / 1000.0 for e in bb_extent_mm]
    print("  BBox (mm): X[%.2f..%.2f] Y[%.2f..%.2f] Z[%.2f..%.2f]" % (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax))

    if args.tol is not None:
        tol_m = args.tol
        tol_mm = tol_m * 1000.0
    else:
        tol_mm = max(bb_extent_mm) * 0.01
        tol_m = tol_mm / 1000.0
    print("  tol: %.1f mm = %.4f m" % (tol_mm, tol_m))

    print("\nGenerating mesh...")
    all_faces = list(shape_mm.Faces())
    face_areas = [f.Area() for f in all_faces if hasattr(f, 'Area')]
    avg_face_area = np.mean(face_areas) if face_areas else 100.0
    mesh = step_to_uniform_mesh(shape_mm, target_face_area=avg_face_area)

    n_verts = len(mesh.vertices)
    n_faces = len(mesh.faces)
    print("  vertices: %d, faces: %d" % (n_verts, n_faces))

    print("\nDetecting tips (%s method)..." % args.method)
    if args.method == 'convex':
        tips_mm = find_tip_convex(mesh.vertices, mesh.faces, tol_mm)
    elif args.method == 'projection':
        tips_mm = find_tip_projection(mesh.vertices, mesh.faces, tol_mm)
    elif args.method == 'radial_x':
        tips_mm = find_tip_points_radial_x(mesh.vertices, mesh.faces, tol_mm, xl_mm=bb_extent_mm[0])

    tips_m = [[tp[0]/1000.0, tp[1]/1000.0, tp[2]/1000.0] for tp in tips_mm]
    print("  Tip points detected: %d" % len(tips_m))

    write_tip_csv(tips_m, csv_path)

    print("\nGenerating HTML viewer: %s" % html_path)
    html_content = generate_html(
        mesh.vertices, mesh.faces, tips_m,
        tip_color=args.tip_color, model_color=args.model_color, bgcolor=args.bgcolor
    )
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Done! HTML: %s" % html_path)
    print("Tip CSV: %s (%d points)" % (csv_path, len(tips_m)))


if __name__ == '__main__':
    main()
