#!/usr/bin/env python3
"""
step-tip-detect.py v3 — STEP 파일에서 tip 포인트 검출 (ortho silhouette edges)

Algorithm:
  1. STEP edges 추출
  2. 각 view(XZ/YZ/XY)에서 orthographic projection:
     - projection direction(숨김 axis)으로 depth 저장
     - depth가 min/max인 edge만 silhouette (외곽선)
  3. silhouette에서 corner / endpoint 추출
  4. 3방향 공통축 매칭 → 3D triangulation
  5. tip classification + CSV/PNG 출력

Dependencies:
    - pip install cadquery numpy opencv-python
"""

import sys
import os
import math
import numpy as np
import csv
import argparse

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery가 설치되어 있지 않습니다.")
    sys.exit(1)


def read_step_header_unit(path):
    """STEP 파일 헤더에서 LENGTH_UNIT을 읽어 반환."""
    with open(path, 'r') as f:
        for line in f:
            if 'SI_UNIT' in line and 'LENGTH_UNIT' in line:
                import re
                m = re.search(r'SI_UNIT\([.\$\s,]*\.(METRE|MMETER)\.', line)
                if m:
                    return 'M' if m.group(1) == 'METRE' else 'MM'
    return None


def get_all_edges(shape):
    """STEP shape의 고유 edges 추출 (중복 제거)."""
    edges = list(shape.Edges())
    edge_set = set()
    unique_edges = []
    for e in edges:
        verts = list(e.Vertices())
        key = tuple(sorted((v.X, v.Y, v.Z) for v in verts))
        if key not in edge_set:
            edge_set.add(key)
            unique_edges.append(e)
    return unique_edges


def get_bbox(shape):
    """shape의 BBox 계산."""
    bb = shape.BoundingBox()
    center = np.array([bb.xmin, bb.ymin, bb.zmin]) + np.array([bb.xmax, bb.ymax, bb.zmax]) / 2
    return {
        'xmin': bb.xmin, 'xmax': bb.xmax,
        'ymin': bb.ymin, 'ymax': bb.ymax,
        'zmin': bb.zmin, 'zmax': bb.zmax,
        'xl': bb.xmax - bb.xmin,
        'yl': bb.ymax - bb.ymin,
        'zl': bb.zmax - bb.zmin,
        'center': center,
    }


# silhouette detection: projection direction → view mapping
# XZ view → project along Y axis (hide Y, keep XZ)
#   silhouette = edges at Y_min or Y_max
# YZ view → project along X axis (hide X, keep YZ)  
#   silhouette = edges at X_min or X_max
# XY view → project along Z axis (hide Z, keep XY)
#   silhouette = edges at Z_min or Z_max

VIEW_PROJECTION = {
    'XZ': {'hide': 'y', 'keep': ('x', 'z'), 'min_key': 'ymin', 'max_key': 'ymax'},
    'YZ': {'hide': 'x', 'keep': ('y', 'z'), 'min_key': 'xmin', 'max_key': 'xmax'},
    'XY': {'hide': 'z', 'keep': ('x', 'y'), 'min_key': 'zmin', 'max_key': 'zmax'},
}


def project_edge_to_2d_with_depth(edge, view):
    """
    edge를 특정 view로 orthographic projection.
    projection direction(숨김 axis)의 min/max 값을 depth로 반환.
    """
    info = VIEW_PROJECTION[view]
    hide_axis = info['hide']
    
    pts, _ = edge.sample(50)
    pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
    
    # projection direction의 min/max
    if hide_axis == 'x':
        depth_min, depth_max = pts_arr[:, 0].min(), pts_arr[:, 0].max()
        projected = pts_arr[:, [1, 2]]  # YZ
    elif hide_axis == 'y':
        depth_min, depth_max = pts_arr[:, 1].min(), pts_arr[:, 1].max()
        projected = pts_arr[:, [0, 2]]  # XZ
    else:  # z
        depth_min, depth_max = pts_arr[:, 2].min(), pts_arr[:, 2].max()
        projected = pts_arr[:, [0, 1]]  # XY
    
    return projected, depth_min, depth_max


def extract_silhouette_edges(edges_3d, view, bbox):
    """
    edges를 projection direction에서 silhouette만 추출.
    
    각 edge의 projection direction min/max가 global bbox min/max에
    가까이 있으면 silhouette (외곽선).
    """
    info = VIEW_PROJECTION[view]
    hide_axis = info['hide']
    min_key = info['min_key']
    max_key = info['max_key']
    
    global_min = bbox[min_key]
    global_max = bbox[max_key]
    global_span = global_max - global_min
    
    # margin = max(1%, 5mm)
    margin = max(global_span * 0.01, 5.0)
    
    silhouette_3d = []
    for e in edges_3d:
        pts, _ = e.sample(50)
        pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
        
        if hide_axis == 'x':
            depth = pts_arr[:, 0]
        elif hide_axis == 'y':
            depth = pts_arr[:, 1]
        else:
            depth = pts_arr[:, 2]
        
        edge_min = depth.min()
        edge_max = depth.max()
        
        # edge가 global min/max에 가까이 있으면 silhouette
        if (edge_min >= global_min - margin and edge_min <= global_min + margin) or \
           (edge_max >= global_max - margin and edge_max <= global_max + margin):
            silhouette_3d.append(e)
    
    return silhouette_3d


def find_extreme_points_silhouette(silhouette_edges, view, bbox):
    """
    silhouette edges에서 sharp corner point만 추출.
    sharp corner: edge 위에서 tangent direction이 급격히 변하는 지점 (curvature peak).
    convexity 체크: outward normal과 같은 방향의 점만 tip으로 간주.
    """
    center = bbox['center']
    all_extremes = []
    
    for e in silhouette_edges:
        edge_faces = list(e.Faces())
        
        pts, _ = e.sample(50)
        pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
        n_pts = len(pts_arr)
        
        if n_pts < 3:
            continue
        
        # Compute tangent at each point (forward/backward difference)
        tangents = np.zeros((n_pts, 3))
        for i in range(n_pts):
            if i == 0:
                tangents[i] = pts_arr[i+1] - pts_arr[i]
            elif i == n_pts - 1:
                tangents[i] = pts_arr[i] - pts_arr[i-1]
            else:
                tangents[i] = (pts_arr[i+1] - pts_arr[i-1]) / 2.0
        
        # Normalize tangents
        t_norms = np.linalg.norm(tangents, axis=1, keepdims=True)
        t_norms[t_norms == 0] = 1e-10
        tangents = tangents / t_norms
        
        # Sharp corner: tangent change angle > threshold
        # delta_tangent[i] = angle between tangent[i-1] and tangent[i+1]
        corner_indices = []
        for i in range(1, n_pts - 1):
            # Cosine of angle between forward and backward tangent
            cos_angle = np.dot(tangents[i-1], tangents[i+1])
            # cos < 0.5 → angle > 60° → sharp corner
            if cos_angle < 0.5:
                corner_indices.append(i)
        
        # Also check endpoints
        corner_indices = [0, n_pts - 1] + corner_indices
        
        # For each sharp corner, determine outward direction based on view
        candidates = []
        outward_dirs = None
        
        if view == 'XZ':
            for idx in corner_indices:
                p = pts_arr[idx]
                candidates.append(p)
            outward_dirs = np.array([
                [-1, 0, 0],
                [1, 0, 0],
                [0, 0, -1],
                [0, 0, 1],
            ])
        elif view == 'YZ':
            for idx in corner_indices:
                p = pts_arr[idx]
                candidates.append(p)
            outward_dirs = np.array([
                [0, -1, 0],
                [0, 1, 0],
                [0, 0, -1],
                [0, 0, 1],
            ])
        elif view == 'XY':
            for idx in corner_indices:
                p = pts_arr[idx]
                candidates.append(p)
            outward_dirs = np.array([
                [-1, 0, 0],
                [1, 0, 0],
                [0, -1, 0],
                [0, 1, 0],
            ])
        
        for i, p in enumerate(candidates):
            # Calculate local normal from face geometry
            if len(edge_faces) == 0:
                tangent = pts_arr[i] - center
                tangent = tangent / (np.linalg.norm(tangent) + 1e-10)
                n = tangent
            else:
                n = np.zeros(3)
                for face in edge_faces:
                    try:
                        seg = face.Seams()
                        for s in seg:
                            sp, sf = s.computeGeometry()
                            if len(sp) >= 2:
                                sp_arr = np.array([[pp.x, pp.y, pp.z] for pp in sp])
                                if len(sp_arr) >= 2:
                                    dir_vec = sp_arr[1] - sp_arr[0]
                                    n += np.cross(dir_vec, [0, 0, 1])
                    except:
                        pass
                norm = np.linalg.norm(n)
                if norm > 1e-10:
                    n = n / norm
                else:
                    tangent = pts_arr[i] - center
                    tangent = tangent / (np.linalg.norm(tangent) + 1e-10)
                    n = tangent
            
            # Check convexity: dot product of normal with outward direction
            # Use the most relevant outward direction for this view
            best_dot = -1
            for od in outward_dirs:
                d = np.dot(n, od)
                if d > best_dot:
                    best_dot = d
            
            if best_dot > 0.3:  # Convex (outward pointing)만 tip으로 간주
                all_extremes.append({
                    'point_3d': p,
                    'x': p[0], 'y': p[1], 'z': p[2],
                    'convex': True,
                })
    
    return all_extremes





def match_3d_points(corners_by_view, tol_mm):
    """
    Y-Z 평면에서 dedup: Y와 Z가 tol 내로 가까운 점끼리 그룹핑.
    그룹 내에서 가장 큰 X 좌표를 tip으로 선택.
    """
    # corners_by_view에서 모든 점 수집 (XZ/YZ/XY 모두 같은 point_3d)
    all_pts = []
    for view, corners in corners_by_view.items():
        for c in corners:
            pt = c['point_3d']
            all_pts.append([pt[0], pt[1], pt[2]])
    
    if not all_pts:
        return []
    
    all_pts = np.array(all_pts)
    
    # Y-Z 평면에서 dedup
    deduped = []
    used = [False] * len(all_pts)
    
    for i, pt in enumerate(all_pts):
        if used[i]:
            continue
        used[i] = True
        
        # 그룹 찾기: Y와 Z가 tol 내로 가까운 점들
        group = [pt]
        for j in range(i + 1, len(all_pts)):
            if used[j]:
                continue
            if abs(pt[1] - all_pts[j][1]) < tol_mm and abs(pt[2] - all_pts[j][2]) < tol_mm:
                group.append(all_pts[j])
                used[j] = True
        
        # 그룹에서 가장 큰 X를 선택
        group = np.array(group)
        best_idx = np.argmax(group[:, 0])
        deduped.append(group[best_idx])
    
    return [np.array(p) for p in deduped]


def classify_tips(tips_mm, bbox):
    """tip을 wing_tip / tail_tip / nose로 분류.
    - X가 bbox center보다 작은(-X 방향) 점은 제외.
    - wing_tip: Y가 중심에서 먼 쪽
    - tail_tip: Z가 중심에서 먼 쪽
    """
    center = bbox['center']
    xl, yl, zl = bbox['xl'], bbox['yl'], bbox['zl']
    classified = []
    
    for tip in tips_mm:
        dx, dy, dz = tip[0] - center[0], tip[1] - center[1], tip[2] - center[2]
        
        # -X 방향 점(nose) 제외
        if dx < 0:
            continue
        
        tip_type = []
        if abs(dy) > yl / 4 and abs(dz) < zl / 4:
            tip_type.append('wing_tip')
        elif abs(dz) > zl / 4:
            tip_type.append('tail_tip')
        else:
            tip_type.append('other')
        
        classified.append({
            'vertex': tip,
            'radial': float(np.linalg.norm(tip - center)),
            'type': tip_type,
        })
    
    return classified


def project_to_cam(points_3d, cam_dir, view_center, img_size=800):
    """
    3D points to camera view (orthographic projection onto plane perpendicular to cam_dir).
    cam_dir: camera position direction (e.g., (1,1,1) means camera at (1,1,1) looking at origin).
    """
    import cv2
    cam_dir = np.array(cam_dir, dtype=float)
    cam_dir = cam_dir / np.linalg.norm(cam_dir)
    
    # Build camera basis: u, v on the image plane
    # Up vector (avoid parallel with cam_dir)
    up = np.array([0, 0, 1]) if abs(np.dot(cam_dir, np.array([0,0,1]))) < 0.9 else np.array([1, 0, 0])
    u = np.cross(cam_dir, up)
    u = u / np.linalg.norm(u)
    v = np.cross(cam_dir, u)
    v = v / np.linalg.norm(v)
    
    center = view_center
    max_extent = np.max(np.abs(points_3d - center)) if len(points_3d) > 0 else 1
    if max_extent == 0:
        max_extent = 1
    scale = (img_size * 0.7) / max_extent
    
    # Project each point onto u, v basis
    dx = points_3d[:, 0] - center[0]
    dy = points_3d[:, 1] - center[1]
    dz = points_3d[:, 2] - center[2]
    
    # Screen coords
    sx = dx * u[0] + dy * u[1] + dz * u[2]
    sy = dx * v[0] + dy * v[1] + dz * v[2]
    
    screen_x = sx * scale + img_size // 2
    screen_y = -sy * scale + img_size // 2  # flip Y for image coords
    
    return screen_x, screen_y


def render_cam_with_tips(points_list, tips_mm, bbox, img_size=800):
    """
    Camera view from (-1, 1, 1) direction looking at center — tail-back view.
    Rotation: -45° about Y, then 35.264° about X.
    """
    import cv2
    img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)
    
    center = bbox['center']
    max_extent = max(bbox['xl'], bbox['yl'], bbox['zl'])
    if max_extent == 0:
        max_extent = 1
    scale = (img_size * 0.7) / max_extent
    
    cos45 = np.cos(np.radians(45))
    sin45 = np.sin(np.radians(45))
    cos35 = np.cos(np.radians(35.264))
    sin35 = np.sin(np.radians(35.264))
    
    for pts in points_list:
        tx = pts[:, 0] - center[0]
        ty = pts[:, 1] - center[1]
        tz = pts[:, 2] - center[2]
        
        # Rotate -90° about X (Y→Z, Z→-Y)
        ty2 = ty * np.cos(np.radians(-90)) - tz * np.sin(np.radians(-90))
        tz2 = ty * np.sin(np.radians(-90)) + tz * np.cos(np.radians(-90))
        ty = ty2
        tz = tz2
        
        # Rotate -45° about Y
        rx = tx * cos45 - tz * sin45
        ry = ty
        rz = tx * sin45 + tz * cos45
        # Rotate 35.264° about X
        ry2 = ry * cos35 - rz * sin35
        rz2 = ry * sin35 + rz * cos35
        
        sx = rx * scale + img_size // 2
        sy = -ry2 * scale + img_size // 2
        
        for i in range(len(pts) - 1):
            x1, y1 = int(round(sx[i])), int(round(sy[i]))
            x2, y2 = int(round(sx[i+1])), int(round(sy[i+1]))
            cv2.line(img, (x1, y1), (x2, y2), (40, 40, 40), 1)
    
    # Tip circles (half size)
    for tip in tips_mm:
        tx = tip[0] - center[0]
        ty = tip[1] - center[1]
        tz = tip[2] - center[2]
        
        # Rotate -90° about X
        ty2 = ty * np.cos(np.radians(-90)) - tz * np.sin(np.radians(-90))
        tz2 = ty * np.sin(np.radians(-90)) + tz * np.cos(np.radians(-90))
        ty = ty2
        tz = tz2
        
        rx = tx * cos45 - tz * sin45
        ry = ty
        rz = tx * sin45 + tz * cos45
        ry2 = ry * cos35 - rz * sin35
        rz2 = ry * sin35 + rz * cos35
        
        sx = rx * scale + img_size // 2
        sy = -ry2 * scale + img_size // 2
        cv2.circle(img, (int(round(sx)), int(round(sy))), 4, (220, 40, 40), -1)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 5, (180, 20, 20), 2)
    
    return img


def main():
    parser = argparse.ArgumentParser(description='STEP tip detection (ortho silhouette edges)')
    parser.add_argument('input', help='Input STEP file')
    parser.add_argument('output', nargs='?', default=None, help='Output CSV path')
    parser.add_argument('--tol', type=float, default=5.0, help='Tip merge tolerance (mm)')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)
    
    step_dir = os.path.dirname(os.path.abspath(args.input))
    step_name = os.path.splitext(os.path.basename(args.input))[0]
    
    print(f"{'='*60}")
    print(f"STEP Tip Detection (ortho silhouette edges)")
    print(f"{'='*60}")
    print(f"STEP: {args.input}")
    print(f"Tolerance: {args.tol:.1f} mm")
    print(f"{'='*60}")
    
    # 1. Load STEP
    print("\n[1/3] Loading STEP...")
    declared_unit = read_step_header_unit(args.input)
    used_unit = declared_unit if declared_unit else 'MM'
    print(f"  Unit: {used_unit}")
    
    shape_mm = cq.importers.importStep(args.input, unit='MM').val()
    
    faces = list(shape_mm.Faces())
    edges = get_all_edges(shape_mm)
    print(f"  Faces: {len(faces)}, Edges: {len(edges)}")
    
    bbox = get_bbox(shape_mm)
    print(f"  BBox: X[{bbox['xmin']:.2f}..{bbox['xmax']:.2f}] Y[{bbox['ymin']:.2f}..{bbox['ymax']:.2f}] Z[{bbox['zmin']:.2f}..{bbox['zmax']:.2f}]")
    
    # 2. Per-view: silhouette extraction → extreme points
    print("\n[2/3] Per-view silhouette extraction...")
    
    corners_by_view = {}
    tol_mm = args.tol
    
    for view in ['XZ', 'YZ', 'XY']:
        print(f"  [{view}] Extracting silhouette edges...")
        silhouette = extract_silhouette_edges(edges, view, bbox)
        print(f"    Silhouette edges: {len(silhouette)} / {len(edges)}")
        
        extremes = find_extreme_points_silhouette(silhouette, view, bbox)
        
        # De-duplicate within view
        unique_extremes = []
        for e in extremes:
            if all(np.linalg.norm(e['point_3d'] - u['point_3d']) >= tol_mm for u in unique_extremes):
                unique_extremes.append(e)
        
        corners_by_view[view] = unique_extremes
        print(f"    Extreme points: {len(unique_extremes)}")
        
        if args.verbose:
            for e in unique_extremes[:5]:
                p = e['point_3d']
                print(f"      ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})")
    
    # 3. Triangulate
    print("\n[3/3] Triangulating 3D tips...")
    tips_3d = match_3d_points(corners_by_view, tol_mm)
    
    print(f"  Detected {len(tips_3d)} tip(s)")
    
    # Classify + mask: BBox 외부 점 제외
    classified = classify_tips(tips_3d, bbox)
    filtered = []
    for i, c in enumerate(classified):
        tip = c['vertex']
        inside = (tip[0] >= bbox['xmin'] and tip[0] <= bbox['xmax'] and
                  tip[1] >= bbox['ymin'] and tip[1] <= bbox['ymax'] and
                  tip[2] >= bbox['zmin'] and tip[2] <= bbox['zmax'])
        if inside:
            filtered.append(c)
    
    for i, c in enumerate(filtered):
        v = c['vertex']
        print(f"  Tip {i+1}: ({v[0]:8.2f}, {v[1]:8.2f}, {v[2]:8.2f}) mm -> {'/'.join(c['type'])}")
    
    # CSV output
    tips_m = [[tp['vertex'][0]/1000.0, tp['vertex'][1]/1000.0, tp['vertex'][2]/1000.0] for tp in filtered]
    csv_path = args.output or f"{os.path.splitext(args.input)[0]}_tip_points.csv"
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        for tp in tips_m:
            writer.writerow([f"{tp[0]:.6f}", f"{tp[1]:.6f}", f"{tp[2]:.6f}"])
    print(f"  CSV: {csv_path} ({len(tips_m)} points)")
    
    # Collect edge points for rendering
    edge_points_list = []
    for e in edges:
        try:
            pts, _ = e.sample(100)
            pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
            if len(pts_arr) >= 2:
                edge_points_list.append(pts_arr)
        except:
            continue
    
    # Camera view PNG (tail-back: -45° about Y → 35.264° about X)
    print("\n  Saving camera view (tail-back: -1, 1, 1) ...")
    png_path = os.path.join(step_dir, f"{step_name}_tip_cam.png")
    cam = render_cam_with_tips(edge_points_list, tips_3d, bbox, img_size=800)
    import cv2
    cv2.imwrite(png_path, cam)
    print(f"  PNG: {png_path}")
    
    print(f"\n{'='*60}")
    print(f"Done! {len(tips_m)} tips detected.")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
