#!/usr/bin/env python3
"""
step_find_tip.py — STEP 파일에서 tip 포인트 검출

단위 처리 규칙 (2026-07-30):
  - STEP 파일은 **모두 mm로 로드**
  - **uniform tessellation**으로 균일한 mesh 생성
  - 출력은 m 단위로 CSV 저장

Algorithm:
  - **convex**: Convex hull distance → protruding vertices 검출
  - **projection**: Multi-direction 2D projection + DBSCAN
  - **radial_x**: X-axis radial sliding (익룡 등 X축 몸체에 적합)
    - STEP face edges → X 슬라이스별 교차 face 수집
    - 각 face edge를 YZ projection segment로 만들고 ray-segment intersection
    - center → circle radius R 방향으로 ray → face intersection = tip

Usage:
  python step_find_tip.py <input.stp> [output.csv]
  python step_find_tip.py <input.stp> --method convex
  python step_find_tip.py <input.stp> --method radial_x
"""

import sys
import os
import numpy as np
import csv
import re

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery가 설치되어 있지 않습니다.")
    sys.exit(1)

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh가 설치되어 있지 않습니다.")
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
    """STEP 파일 헤더에서 LENGTH_UNIT을 읽어 반환."""
    with open(path, 'r') as f:
        for line in f:
            if 'SI_UNIT' in line and 'LENGTH_UNIT' in line:
                m = re.search(r'SI_UNIT\([.\$\s,]*\.(METRE|MMETER)\.', line)
                if m:
                    return 'M' if m.group(1) == 'METRE' else 'MM'
    return None


def direction_aware_merge(candidates, tol_mm):
    """
    Direction-aware merge: 한 축 >= tol 차이, 다른 두 축 < tol 차이 → 같은 tip
    
    parameters:
        candidates: numpy array (N, 3) in mm
        tol_mm: mm
    returns:
        list of tip (mm)
    """
    tips = []
    for candidate in candidates:
        merged = False
        for i, existing in enumerate(tips):
            diffs = np.abs(candidate - existing)
            sorted_diffs = np.sort(diffs)
            # 가장 큰 축 >= tol AND 나머지 두 축 < tol
            if sorted_diffs[2] >= tol_mm and sorted_diffs[0] < tol_mm and sorted_diffs[1] < tol_mm:
                tips[i] = (existing + candidate) / 2.0
                merged = True
                break
        if not merged:
            tips.append(candidate.copy())
    return tips


def find_tip_convex(mesh_vertices, mesh_faces, tol_mm):
    """Convex hull distance-based tip detection with direction-aware merge."""
    if not HAS_CONVEXHULL:
        return []

    vertices = np.array(mesh_vertices)

    hull = ConvexHull(vertices)
    hull_simplices = hull.simplices

    # Hull face normals
    hull_faces_verts = vertices[hull_simplices]
    hull_normals = np.cross(
        hull_faces_verts[:, 1] - hull_faces_verts[:, 0],
        hull_faces_verts[:, 2] - hull_faces_verts[:, 0]
    )
    norm_n = np.linalg.norm(hull_normals, axis=1, keepdims=True)
    norm_n[norm_n == 0] = 1.0
    hull_normals /= norm_n

    # Distance from each vertex to nearest hull face
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

    # Tip candidates: positive distance + top 20%
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

    # Direction-aware merge
    return direction_aware_merge(tip_candidates, tol_mm)


def ray_seg_intersection(ray_o, ray_d, seg_a, seg_b):
    """
    2D ray-segment intersection.
    ray: origin + t*dir (t>0)
    segment: a + u*(b-a) (0<=u<=1)
    Returns intersection point if exists, else None
    """
    dx = ray_d[0]; dy = ray_d[1]
    sx = seg_b[0] - seg_a[0]; sy = seg_b[1] - seg_a[1]
    rx = seg_a[0] - ray_o[0]; ry = seg_a[1] - ray_o[1]
    denom = dx * sy - dy * sx
    if abs(denom) < 1e-12:
        return None
    t = (rx * sy - ry * sx) / denom
    u = (rx * dy - ry * dx) / denom
    if t > 1e-8 and 0 <= u <= 1:
        return (ray_o[0] + t * dx, ray_o[1] + t * dy)
    return None


def find_tip_points_radial_x(mesh_vertices, mesh_faces, tol_mm, step_path=None):
    """
    X-axis radial sliding with STEP face geometry (no tessellation).
    
    Algorithm:
      1. X축을 100등분 슬라이스로 분할
      2. 각 슬라이스 [x_lo, x_hi] 에서 해당 범위를 교차하는 STEP face 수집
      3. STEP face의 edge를 YZ projection segment로 만듦
      4. 슬라이스 중심 (y_center, z_center) 에서 각 theta 방향으로 ray 쏘기
         - ray direction = (cosθ, sinθ) in YZ plane
         - face edge와 ray-segment intersection → 교차점이 tip location
      5. 인접 슬라이스 간 radial distance ratio 계산
      6. ratio <= 0.5 인 지점을 tip 후보
      7. merge 없음: 모든 tip candidates 그대로 반환
    """
    if step_path and os.path.exists(step_path):
        return _find_tip_radial_x_from_step(step_path, tol_mm)
    
    vertices = np.array(mesh_vertices)
    faces = np.array(mesh_faces)
    bb_min = vertices.min(axis=0)
    bb_max = vertices.max(axis=0)
    x_extent = bb_max[0] - bb_min[0]
    y_center = (bb_min[1] + bb_max[1]) / 2.0
    z_center = (bb_min[2] + bb_max[2]) / 2.0
    
    return _radial_from_vertices_faces(vertices, faces, bb_min, bb_max, x_extent,
                                       y_center, z_center, tol_mm)


def _find_tip_radial_x_from_step(step_path, tol_mm):
    """STEP face geometry → X 슬라이스별 ray-segment intersection."""
    from shapely.geometry import LineString
    
    shape_mm = cq.importers.importStep(step_path, unit='MM').val()
    bbox = shape_mm.BoundingBox()
    bb_min = np.array([bbox.xmin, bbox.ymin, bbox.zmin])
    bb_max = np.array([bbox.xmax, bbox.ymax, bbox.zmax])
    x_extent = bb_max[0] - bb_min[0]
    
    face_list = list(shape_mm.Faces())
    n_faces = len(face_list)
    
    face_x_min = np.zeros(n_faces)
    face_x_max = np.zeros(n_faces)
    face_edges_yz = []
    for fi, face in enumerate(face_list):
        edges = list(face.Edges())
        x_vals = [v.X for e in edges for v in e.Vertices()]
        face_x_min[fi] = min(x_vals)
        face_x_max[fi] = max(x_vals)
        edges_yz = []
        for edge in edges:
            verts = list(edge.Vertices())
            if len(verts) >= 2:
                edges_yz.append(((verts[0].Y, verts[0].Z), (verts[1].Y, verts[1].Z)))
        face_edges_yz.append(edges_yz)
    
    return _radial_x_slice_step(face_list, face_x_min, face_x_max, face_edges_yz,
                                bb_min, bb_max, x_extent, tol_mm)


def _radial_x_slice_step(face_list, face_x_min, face_x_max, face_edges_yz,
                         bb_min, bb_max, x_extent, tol_mm):
    """X 슬라이스별 face edges + ray-segment intersection."""
    from shapely.geometry import LineString
    
    n_x_slices = 100
    x_step = x_extent / n_x_slices
    n_angles = 360
    angles_rad = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    
    all_radial = [None] * n_x_slices
    slice_centers = {}  # si -> (yc, zc)
    
    for si in range(n_x_slices):
        x_lo = bb_min[0] + si * x_step
        x_hi = x_lo + x_step
        
        ix = np.where((face_x_max >= x_lo) & (face_x_min <= x_hi))[0]
        if len(ix) == 0:
            all_radial[si] = np.full(n_angles, np.nan)
            continue
        
        # Local YZ bounding box of intersecting faces
        local_ys = []
        local_zs = []
        for fi in ix:
            for sa, sb in face_edges_yz[fi]:
                local_ys.extend([sa[0], sb[0]])
                local_zs.extend([sa[1], sb[1]])
        
        yc = (min(local_ys) + max(local_ys)) / 2.0
        zc = (min(local_zs) + max(local_zs)) / 2.0
        slice_centers[si] = (yc, zc)
        
        # Search radius = max(ΔY, ΔZ) * 1.2
        local_max = max(max(local_ys) - min(local_ys), max(local_zs) - min(local_zs))
        R = local_max * 1.2
        
        r = np.full(n_angles, np.nan)
        for ai in range(n_angles):
            theta = angles_rad[ai]
            # Start on search circle, ray toward center
            so = (yc + R * np.cos(theta), zc + R * np.sin(theta))
            sd = (-np.cos(theta), -np.sin(theta))
            
            hits = []
            for fi in ix:
                for sa, sb in face_edges_yz[fi]:
                    pt = ray_seg_intersection(so, sd, sa, sb)
                    if pt:
                        d = np.sqrt((pt[0]-yc)**2 + (pt[1]-zc)**2)
                        if d > 0:
                            hits.append((d, pt[0], pt[1]))
            
            if hits:
                hits.sort(key=lambda t: t[0])
                r[ai] = hits[0][0]
        
        all_radial[si] = r
    
    return _compute_tips(all_radial, bb_min, bb_max, x_step, slice_centers, tol_mm, n_x_slices)


def _radial_from_vertices_faces(vertices, faces, bb_min, bb_max, x_extent,
                                 y_center, z_center, tol_mm):
    """Legacy: mesh tessellation으로 face별 YZ polygon + polygonize."""
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import polygonize, unary_union
    
    n_x_slices = 100
    x_step = x_extent / n_x_slices
    n_angles = 360
    angles = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    
    face_x_min = np.array([
        min(vertices[f[0], 0], vertices[f[1], 0], vertices[f[2], 0]) for f in faces
    ])
    face_x_max = np.array([
        max(vertices[f[0], 0], vertices[f[1], 0], vertices[f[2], 0]) for f in faces
    ])
    
    all_radial = [None] * n_x_slices
    
    for si in range(n_x_slices):
        x_lo = bb_min[0] + si * x_step
        x_hi = x_lo + x_step
        mask = (face_x_max >= x_lo) & (face_x_min <= x_hi)
        
        polys = []
        for fi in np.where(mask)[0]:
            f = faces[fi]
            v0, v1, v2 = vertices[f[0]], vertices[f[1]], vertices[f[2]]
            poly = Polygon([(v0[1], v0[2]), (v1[1], v1[2]), (v2[1], v2[2])])
            if poly.area > 1e-6:
                polys.append(poly)
        
        if not polys:
            all_radial[si] = np.full(n_angles, np.nan)
            continue
        
        merged = unary_union(polys)
        radial_at_angle = np.full(n_angles, np.nan)
        
        for ai in range(n_angles):
            theta = angles[ai]
            cos_t, sin_t = np.cos(theta), np.sin(theta)
            ray = LineString([(y_center, z_center), (y_center + cos_t * 1e8, z_center + sin_t * 1e8)])
            intersects = merged.intersection(ray)
            if intersects.is_empty:
                continue
            max_dist = 0.0
            if intersects.geom_type == 'LineString':
                coords = list(intersects.coords)
                end_pt = coords[-1]
                max_dist = np.sqrt((end_pt[0] - y_center)**2 + (end_pt[1] - z_center)**2)
            elif intersects.geom_type == 'Point':
                max_dist = np.sqrt((intersects.x - y_center)**2 + (intersects.y - z_center)**2)
            elif intersects.geom_type == 'MultiPoint':
                for pt in intersects.geoms:
                    d = np.sqrt((pt.x - y_center)**2 + (pt.y - z_center)**2)
                    max_dist = max(max_dist, d)
            elif intersects.geom_type == 'MultiLineString':
                for line in intersects.geoms:
                    for line_pt in line.coords:
                        d = np.sqrt((line_pt[0] - y_center)**2 + (line_pt[1] - z_center)**2)
                        max_dist = max(max_dist, d)
            if max_dist > 0:
                radial_at_angle[ai] = max_dist
        
        all_radial[si] = radial_at_angle
    
    return _compute_tips(all_radial, bb_min, bb_max, x_step,
                        {si: (y_center, z_center) for si in range(n_x_slices)}, tol_mm, n_x_slices)


def _compute_tips(all_radial, bb_min, bb_max, x_step, slice_centers, tol_mm, n_x_slices):
    """radial data에서 tip candidates 추출. merge 없음."""
    threshold = 0.50
    tip_candidates_mm = []
    
    for xi in range(1, n_x_slices):
        s1 = xi - 1
        prev_r = all_radial[s1]
        curr_r = all_radial[xi]
        
        if prev_r is None or curr_r is None:
            continue
        
        valid_mask = (~np.isnan(prev_r)) & (~np.isnan(curr_r)) & (prev_r > 0) & (curr_r > 0)
        if valid_mask.sum() < 3:
            continue
        
        ratio = curr_r[valid_mask] / prev_r[valid_mask]
        sharp_idx = np.where((ratio <= threshold) & (ratio < 1.0))[0]
        if len(sharp_idx) == 0:
            continue
        
        yc, zc = slice_centers.get(s1, (0, 0))
        
        for ai in sharp_idx:
            r_n = prev_r[ai]
            ai_idx = np.where(valid_mask)[0][ai]
            actual_angle = np.linspace(0, 2 * np.pi, 360, endpoint=False)[ai_idx]
            cos_a = np.cos(actual_angle)
            sin_a = np.sin(actual_angle)
            
            tip_x = bb_min[0] + (xi - 1 + 0.5) * x_step
            tip_y = yc + r_n * cos_a
            tip_z = zc + r_n * sin_a
            
            tip_candidates_mm.append(np.array([tip_x, tip_y, tip_z]))
    
    return [np.array(t) for t in tip_candidates_mm] if tip_candidates_mm else []


def find_tip_projection(mesh_vertices, mesh_faces, tol_mm):
    """Multi-direction 2D projection + DBSCAN (original web-stl-viewer logic)."""
    mesh = trimesh.Trimesh(vertices=mesh_vertices, faces=mesh_faces, process=False)
    vertices = mesh.vertices
    faces = mesh.faces

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
                high_coords = high_coords[idx]
                high_indices = high_indices[idx]
                high_radial = high_radial[idx]

            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale
            eps_val = 0.3 / max(scale.min(), 1e-6)
            eps_val = max(0.05, min(eps_val, 0.999))

            if HAS_SKLEARN:
                clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
            elif HAS_LINKAGE:
                dist_matrix = pdist(features)
                Z = linkage(dist_matrix, method='complete')
                clustering_labels = fcluster(Z, t=eps_val, criterion='distance')
                clustering = type('obj', (object,), {'labels_': clustering_labels})()
            else:
                continue

            labels = clustering.labels_
            for label in set(labels):
                if label == -1:
                    continue
                cm_mask = labels == label
                cluster_idx_2d = high_indices[cm_mask]
                cluster_radial = high_radial[cm_mask]
                peak_local = cluster_radial.argmax()
                peak_idx_3d = cluster_idx_2d[peak_local]
                tip_candidates.append(vertices[peak_idx_3d].copy())

    # Merge: within tol_mm → keep X가 최대인 것
    merged = []
    for t in tip_candidates:
        placed = False
        for i, existing in enumerate(merged):
            d = np.linalg.norm(t - existing)
            if d < tol_mm:
                if t[0] > existing[0]:
                    merged[i] = t
                placed = True
                break
        if not placed:
            merged.append(t.copy())
    final = []
    for t in merged:
        if not any(np.linalg.norm(t - q) < tol_mm for q in final):
            final.append(t)
    return final[:20]


def step_to_uniform_mesh(shape_mm, target_face_area=None):
    """STEP shape → uniform tessellation mesh (mm)."""
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


def compute_boundary_layer_thickness(h1, nlayers, growth):
    if growth == 1.0:
        return h1 * nlayers
    return h1 * (growth ** nlayers - 1.0) / (growth - 1.0)


def write_tip_csv(tip_points_m, output_path):
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        for tp in tip_points_m:
            writer.writerow([f"{tp[0]:.6f}", f"{tp[1]:.6f}", f"{tp[2]:.6f}"])
    print(f"출력: {output_path} ({len(tip_points_m)}개 포인트, m 단위)")


def format_val(value_m, unit, decimals=6):
    if unit == 'MM':
        return f"{value_m * 1000:.{decimals}f} mm"
    return f"{value_m:.{decimals}f} m"


def print_table(headers, rows):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    hdr = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(hdr)
    print("=" * len(hdr))
    for row in rows:
        cells = [str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)]
        print(" | ".join(cells))
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='STEP 파일에서 tip 포인트 검출')
    parser.add_argument('input', help='입력 STEP 파일 경로')
    parser.add_argument('output', nargs='?', default=None, help='출력 CSV 파일 경로')
    parser.add_argument('--h1', type=float, default=0.0001, help='첫 경계층 셀 높이 (m)')
    parser.add_argument('--nlayers', type=int, default=10, help='경계층 레이어 수')
    parser.add_argument('--growth', type=float, default=1.3, help='경계층 growth rate')
    parser.add_argument('--method', type=str, default='convex',
                        choices=['convex', 'projection', 'radial_x'],
                        help='tip detection method: convex (기본), projection, radial_x')
    parser.add_argument('--target-face-area', type=float, default=None, help='uniform tessellation target (mm²)')
    parser.add_argument('--verbose', '-v', action='store_true', help='상세 출력')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"오류: 파일이 없습니다 — {args.input}")
        sys.exit(1)

    print(f"STEP 파일 로드 중: {args.input}")

    declared_unit = read_step_header_unit(args.input)
    used_unit = declared_unit if declared_unit else 'MM'
    print(f"  STEP 헤더 단위: {used_unit} ({'meter' if used_unit == 'M' else 'millimeter (기본)'})")

    shape_mm = cq.importers.importStep(args.input, unit='MM').val()
    print(f"  mm로 로드 완료")

    face_count = len(list(shape_mm.Faces()))
    edge_count = len(list(shape_mm.Edges()))
    print(f"  Face 수: {face_count}, Edge 수: {edge_count}")

    bb = shape_mm.BoundingBox()
    bb_extent = [bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin]
    print(f"  BBox (mm): X[{bb.xmin:.2f} .. {bb.xmax:.2f}] Y[{bb.ymin:.2f} .. {bb.ymax:.2f}] Z[{bb.zmin:.2f} .. {bb.zmax:.2f}]")
    print(f"  extent (mm): [{bb_extent[0]:.2f}, {bb_extent[1]:.2f}, {bb_extent[2]:.2f}]")

    tol_mm = max(bb_extent) * 0.01
    tol = tol_mm / 1000.0
    print(f"  tol 자동 계산: max({bb_extent[0]:.1f}, {bb_extent[1]:.1f}, {bb_extent[2]:.1f}) * 0.01 = {tol_mm:.1f} mm = {tol:.4f} m")

    T = compute_boundary_layer_thickness(args.h1, args.nlayers, args.growth)
    T_mm = T * 1000.0
    print(f"\n경계층 두께 T = h1({args.h1}) x ({args.growth}^{args.nlayers} - 1) / ({args.growth} - 1)")
    print(f"  T = {T:.6f} m = {T_mm:.2f} mm")

    # Step 1: uniform mesh
    print(f"\nStep 1: uniform mesh 생성 중...")
    if args.target_face_area:
        mesh = step_to_uniform_mesh(shape_mm, target_face_area=args.target_face_area)
    else:
        all_faces = list(shape_mm.Faces())
        face_areas = [f.Area() for f in all_faces if hasattr(f, 'Area')]
        avg_face_area = np.mean(face_areas) if face_areas else 100.0
        mesh = step_to_uniform_mesh(shape_mm, target_face_area=avg_face_area)

    n_verts = len(mesh.vertices)
    n_faces = len(mesh.faces)
    print(f"  vertices: {n_verts:,}개, faces: {n_faces:,}개")

    # Step 2: tip detection
    print(f"\nStep 2: tip 검출 중 ({args.method} method)...")
    if args.method == 'convex':
        tips_mm = find_tip_convex(mesh.vertices, mesh.faces, tol_mm)
    elif args.method == 'projection':
        tips_mm = find_tip_projection(mesh.vertices, mesh.faces, tol_mm)
    elif args.method == 'radial_x':
        tips_mm = find_tip_points_radial_x(mesh.vertices, mesh.faces, tol_mm, step_path=args.input)

    tips_m = [[tp[0]/1000.0, tp[1]/1000.0, tp[2]/1000.0] for tp in tips_mm]
    print(f"  tip 포인트: {len(tips_m)}개 검출")

    # Step 3: 출력
    two_T_m = 2.0 * T
    smallest_face_diag_m = (bb.xmax - bb.xmin) / 1000.0

    print("=" * 60)
    print(f"tip 검출 결과 ({args.method} method)")
    print("=" * 60)

    result_rows = [
        ["STEP file", os.path.basename(args.input), "Input file"],
        ["Header Unit", used_unit, "STEP declared unit"],
        ["Load Unit", "MM", "Loaded as mm"],
        ["h1", f"{args.h1:.6f} m", "First cell height (BL)"],
        ["nlayers", str(args.nlayers), "BL count"],
        ["growth", f"{args.growth:.4f}", "BL growth rate"],
        ["T", format_val(T, used_unit, 6), "BL total thickness"],
        ["2T", format_val(two_T_m, used_unit, 6), "2 x BL thickness"],
        ["xl", format_val(smallest_face_diag_m, used_unit, 6), "X extent"],
        ["yl", format_val((bb.ymax - bb.ymin)/1000, used_unit, 6), "Y extent"],
        ["zl", format_val((bb.zmax - bb.zmin)/1000, used_unit, 6), "Z extent"],
        ["uniform_face_area", f"{avg_face_area:.1f} mm²", "Tessellation target"],
        ["mesh_vertices", f"{n_verts:,}", "Vertices"],
        ["mesh_faces", f"{n_faces:,}", "Faces"],
        ["tol_mm", f"{tol_mm:.1f} mm (max_dim*0.01)", "Tip merge tolerance"],
        ["method", args.method, "Tip detection method"],
    ]
    print_table(["Parameter", "Value", "Description"], result_rows)

    print(f"\nTip 포인트 목록 ({len(tips_m)}개):")
    for i, tp in enumerate(tips_m):
        print(f"  tip{i+1}: ({tp[0]:.6f}, {tp[1]:.6f}, {tp[2]:.6f}) m")

    if args.output is None:
        base = os.path.splitext(args.input)[0]
        args.output = f"{base}_tip_points.csv"

    write_tip_csv(tips_m, args.output)
    print(f"\n완료! {len(tips_m)}개의 tip 포인트를 검출했습니다.")


if __name__ == '__main__':
    main()
