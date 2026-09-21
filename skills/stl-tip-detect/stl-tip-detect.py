#!/usr/bin/env python3
"""
stl-tip-detect — STL 파일에서 tip 포인트 검출

Algorithm:
  1. STL mesh edges 추출 (모든 face edge unique)
  2. 3방향 orthographic projection (XZ/YZ/XY) -> 2D graph
  3. graph에서 sharp corner detection (>90 deg tangent)
  4. 3방향 매칭 -> triangulation -> 3D 좌표 복원
  5. postprocess dedup (BBox 5% 이내 그룹핑)
  6. silhouette contour 내부/외부 판별 (shapely)
  7. tip classification + CSV/PNG 출력

Dependencies:
    pip install trimesh numpy opencv-python shapely scipy
"""

import sys
import os
import math
import numpy as np
import csv
import argparse

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh가 설치되어 있지 않습니다.")
    print("pip install trimesh")
    sys.exit(1)

try:
    import cv2
except ImportError:
    print("ERROR: opencv-python가 설치되어 있지 않습니다.")
    print("pip install opencv-python")
    sys.exit(1)

try:
    from sklearn.cluster import DBSCAN
    HAS_DBSCAN = True
except ImportError:
    HAS_DBSCAN = False


def load_stl(path):
    """Load STL file, detect unit heuristically, return mesh in meters.
    
    Unit heuristic:
    - max coordinate > 100 → mm로 간주 → 1000으로 나누어 m로 변환
    - max coordinate <= 100 → m로 간주 (변환 없음)
    """
    mesh = trimesh.load(path)
    if not isinstance(mesh, trimesh.Trimesh):
        if isinstance(mesh, trimesh.Scene):
            meshes = list(mesh.dump())
            if meshes:
                mesh = trimesh.util.concatenate(meshes)
            else:
                print("Error: No mesh data found.")
                sys.exit(1)
        else:
            print(f"Error: Cannot load {path}")
            sys.exit(1)

    max_coord = mesh.vertices.max()
    if max_coord > 100:
        unit = 'MM'
        mesh.vertices *= 0.001
    else:
        unit = 'M'

    return mesh, unit


def get_bbox(mesh):
    """Compute bounding box from mesh vertices. Returns dict with min/max/extent/center."""
    mins = mesh.vertices.min(axis=0)
    maxs = mesh.vertices.max(axis=0)
    extents = maxs - mins
    center = (mins + maxs) / 2.0

    return {
        'xmin': float(mins[0]), 'xmax': float(maxs[0]),
        'ymin': float(mins[1]), 'ymax': float(maxs[1]),
        'zmin': float(mins[2]), 'zmax': float(maxs[2]),
        'xl': float(extents[0]),
        'yl': float(extents[1]),
        'zl': float(extents[2]),
        'center': center,
    }


def get_all_edges(mesh):
    """Extract all unique mesh edges.
    
    Returns list of (v0, v1) vertex coordinate pairs (3D).
    Duplicate edges removed by coordinate matching.
    """
    edge_indices = mesh.edges_unique
    verts = mesh.vertices
    unique_edges = []

    seen = set()
    for e in edge_indices:
        v0_raw = verts[e[0]]
        v1_raw = verts[e[1]]
        v0_t = (float(v0_raw[0]), float(v0_raw[1]), float(v0_raw[2]))
        v1_t = (float(v1_raw[0]), float(v1_raw[1]), float(v1_raw[2]))
        key = tuple(sorted((v0_t, v1_t)))
        if key not in seen:
            seen.add(key)
            unique_edges.append((v0_raw, v1_raw))

    return unique_edges


def find_tip_dbscan(mesh, tol=0.5, verbose=False):
    """DBSCAN-based tip detection (same algorithm as stl-viewer).
    
    Multi-directional radial clustering on vertices.
    Returns tips in meters.
    """
    if not HAS_DBSCAN:
        return [], "DBSCAN not available (pip install scikit-learn)"

    vertices = mesh.vertices
    faces = mesh.faces
    
    # Large mesh downsampling
    if len(vertices) > 50000:
        try:
            sample_mesh = mesh.sample(50000, process=False)
            vertices = sample_mesh.vertices
            faces = sample_mesh.faces
            print(f"  [downsample] {len(mesh.vertices)} -> {len(vertices)} vertices")
        except Exception as e:
            print(f"  [downsample] Failed: {e}, using original")

    tip_candidates = []

    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
        centroids = vertices[faces].mean(axis=1)
        verts_2d = vertices[:, [axis1, axis2]]
        origin_2d = centroids[:, [axis1, axis2]].mean(axis=0)
        radial = np.linalg.norm(verts_2d - origin_2d, axis=1)

        for pct in [30, 50, 70]:
            threshold = np.percentile(radial, pct)
            high_mask = radial > threshold
            if high_mask.sum() == 0:
                continue
            high_coords = verts_2d[high_mask]
            high_indices = np.where(high_mask)[0]
            high_radial = radial[high_mask]

            if len(high_indices) < 10:
                continue
            # Downsample for performance
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
            eps_val = max(0.001, min(eps_val, 0.999))
            clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
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

    # Dedup by 3D distance
    tips = []
    for t in tip_candidates:
        if not any(np.linalg.norm(t - q) < tol for q in tips):
            tips.append(t)

    tips = tips[:20]
    msg = f"DBSCAN found {len(tips)} tip(s)"
    return tips, msg


def extract_silhouette_edges(edges_3d, view, bbox):
    """Extract silhouette edges from mesh edges in projection direction.
    
    Uses projected shape boundary (shapely convex hull).
    Keeps edges whose BOTH endpoints are on/near the hull boundary.
    """
    from shapely.geometry import MultiPoint
    
    axes_map = {'XZ': (0, 2), 'YZ': (1, 2), 'XY': (0, 1)}
    axes = axes_map[view]
    
    # Project all unique edge endpoints to 2D
    projected_endpoints = set()
    for e in edges_3d:
        v0, v1 = e
        p0 = (e[0][axes[0]], e[0][axes[1]])
        p1 = (e[1][axes[0]], e[1][axes[1]])
        # Snap to grid (1mm resolution)
        p0s = (round(p0[0]/0.001)*0.001, round(p0[1]/0.001)*0.001)
        p1s = (round(p1[0]/0.001)*0.001, round(p1[1]/0.001)*0.001)
        projected_endpoints.add(p0s)
        projected_endpoints.add(p1s)
    
    if len(projected_endpoints) < 3:
        return edges_3d
    
    pts_array = np.array(list(projected_endpoints))
    multipoint = MultiPoint(pts_array)
    hull = multipoint.convex_hull
    
    if hull.geom_type == 'MultiPolygon':
        hull = max(hull.geoms, key=lambda g: g.area)
    
    if hull.geom_type != 'Polygon':
        return edges_3d
    
    hull_coords = np.array(hull.exterior.coords)
    
    # Boundary tolerance: 0.5% of projected span (min 0.5mm)
    span_x = max(hull_coords[:, 0]) - min(hull_coords[:, 0])
    span_y = max(hull_coords[:, 1]) - min(hull_coords[:, 1])
    boundary_tol = max(span_x, span_y) * 0.005
    boundary_tol = max(boundary_tol, 0.0005)
    
    # Keep edges whose BOTH endpoints are on/near the hull boundary
    silhouette_edges = []
    for e in edges_3d:
        p0_2d = (e[0][axes[0]], e[0][axes[1]])
        p1_2d = (e[1][axes[0]], e[1][axes[1]])
        
        dist0 = dist1 = float('inf')
        for hc in hull_coords:
            d0 = abs(p0_2d[0] - hc[0]) + abs(p0_2d[1] - hc[1])
            d1 = abs(p1_2d[0] - hc[0]) + abs(p1_2d[1] - hc[1])
            if d0 < dist0: dist0 = d0
            if d1 < dist1: dist1 = d1
        
        if dist0 < boundary_tol and dist1 < boundary_tol:
            silhouette_edges.append(e)
    
    return silhouette_edges


def build_2d_graph(edges_3d, view, tol=0.001):
    """Project mesh edges to 2D and build adjacency graph.
    
    Snap vertices to grid (tol) to handle floating point differences.
    Returns (vertex_list, adjacency_dict).
    """
    vertex_set = set()
    edge_pairs = []

    for e in edges_3d:
        v0, v1 = e

        if view == 'XZ':
            p0_2d = np.array([v0[0], v0[2]])
            p1_2d = np.array([v1[0], v1[2]])
        elif view == 'YZ':
            p0_2d = np.array([v0[1], v0[2]])
            p1_2d = np.array([v1[1], v1[2]])
        else:  # XY
            p0_2d = np.array([v0[0], v0[1]])
            p1_2d = np.array([v1[0], v1[1]])

        s0 = (round(p0_2d[0]/tol)*tol, round(p0_2d[1]/tol)*tol)
        s1 = (round(p1_2d[0]/tol)*tol, round(p1_2d[1]/tol)*tol)

        vertex_set.add(s0)
        vertex_set.add(s1)
        edge_pairs.append((s0, s1))

    vertex_list = sorted(vertex_set)
    v2idx = {v: i for i, v in enumerate(vertex_list)}

    adj = {}
    for i in range(len(vertex_list)):
        adj[i] = set()

    for s0, s1 in edge_pairs:
        i0, i1 = v2idx[s0], v2idx[s1]
        if i0 != i1:
            adj[i0].add(i1)
            adj[i1].add(i0)

    return vertex_list, adj


def find_all_sharp_vertices(vertex_list, adj, sharp_cos_threshold=0.0):
    """Find all sharp corners (>90 deg) in the 2D graph.
    
    Criteria: exactly 2 neighbors AND cos(angle) < sharp_cos_threshold.
    Default sharp_cos_threshold=0.0 → angle > 90° (cos < 0).
    """
    sharp_vertices = []

    for vi, v in enumerate(vertex_list):
        neighbors = adj[vi]
        if len(neighbors) != 2:
            continue

        n1, n2 = list(neighbors)
        v1 = np.array(vertex_list[n1])
        v2 = np.array(vertex_list[n2])

        a = v1 - np.array(v)
        b = v2 - np.array(v)

        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)

        if na < 1e-10 or nb < 1e-10:
            continue

        a /= na
        b /= nb

        cos_angle = np.dot(a, b)

        if cos_angle < sharp_cos_threshold:
            sharp_vertices.append(np.array(v))

    return sharp_vertices


def map_sharp_to_3d(sharp_2d_pts, edges_3d, view, tol_m=0.005):
    """Map 2D sharp vertices back to 3D using original mesh edges.
    
    For each 2D sharp point, find the closest mesh edge projection.
    Returns list of 3D vertex coordinates.
    """
    candidates_3d = []

    for pt2d in sharp_2d_pts:
        best_match = None
        best_dist = float('inf')

        for e in edges_3d:
            v0, v1 = e
            if view == 'XZ':
                line_2d = np.array([[v0[0], v0[2]], [v1[0], v1[2]]])
            elif view == 'YZ':
                line_2d = np.array([[v0[1], v0[2]], [v1[1], v1[2]]])
            else:  # XY
                line_2d = np.array([[v0[0], v0[1]], [v1[0], v1[1]]])

            line_vec = line_2d[1] - line_2d[0]
            line_len = np.linalg.norm(line_vec)
            if line_len < 1e-10:
                continue

            t = np.dot(pt2d - line_2d[0], line_vec) / (line_len ** 2)
            t = max(0, min(1, t))
            proj_pt = line_2d[0] + t * line_vec

            dist = np.linalg.norm(pt2d - proj_pt)

            if dist < best_dist and dist < tol_m:
                best_dist = dist
                best_match = v0 if t < 0.5 else v1

        if best_match is not None:
            candidates_3d.append(best_match)

    return candidates_3d


def find_silhouette_contour(silhouette_edges, view):
    """Build closed loop polygon from silhouette edges via DFS.
    
    Uses odd-degree vertex as start point (Euler path property).
    Returns contour as list of 3D points or None if < 3 points.
    """
    hide_map = {'XZ': 1, 'YZ': 0, 'XY': 2}
    axes_map = {'XZ': (0, 2), 'YZ': (1, 2), 'XY': (0, 1)}
    axes = axes_map[view]

    tol = 0.005  # 5mm snap

    # Build endpoint index mapping
    endpoints = {}
    for p0, p1 in silhouette_edges:
        for pt in [p0, p1]:
            key = (round(pt[axes[0]]/tol)*tol, round(pt[axes[1]]/tol)*tol)
            if key not in endpoints:
                endpoints[key] = [pt]
            else:
                endpoints[key].append(pt)

    if not endpoints:
        return None

    # Build adjacency from snapped endpoints
    keys = list(endpoints.keys())
    k2i = {k: i for i, k in enumerate(keys)}
    adj = {i: set() for i in range(len(keys))}

    for p0, p1 in silhouette_edges:
        k0 = (round(p0[axes[0]]/tol)*tol, round(p0[axes[1]]/tol)*tol)
        k1 = (round(p1[axes[0]]/tol)*tol, round(p1[axes[1]]/tol)*tol)
        if k0 in k2i and k1 in k2i:
            adj[k2i[k0]].add(k2i[k1])
            adj[k2i[k1]].add(k2i[k0])

    # Closed loop via DFS from odd-degree vertex
    visited = set()
    contour = []
    odd_deg = [i for i in adj if len(adj[i]) % 2 == 1]
    start = odd_deg[0] if odd_deg else 0

    curr = start
    prev = None
    for _ in range(len(adj)):
        visited.add(curr)
        contour.append(keys[curr])
        neighbors = list(adj[curr])
        found_next = False
        for n in neighbors:
            if n != prev and n not in visited:
                prev, curr = curr, n
                found_next = True
                break
        if not found_next:
            break

    if len(contour) < 3:
        return None

    return contour


def check_point_outside_contour(point_3d, silhouette_edges, view, tol_m=0.005):
    """Check if a point is outside the silhouette contour polygon.
    
    Returns True if outside (external tip), False if inside (internal).
    Returns True if contour cannot be built (conservative -> external).
    """
    from shapely.geometry import Polygon, Point as ShapelyPoint

    contour = find_silhouette_contour(silhouette_edges, view)

    if contour is None or len(contour) < 3:
        return True  # Cannot build contour -> external

    poly = Polygon(contour).buffer(0)

    axes_map = {'XZ': (0, 2), 'YZ': (1, 2), 'XY': (0, 1)}
    axes = axes_map[view]
    shapely_point = ShapelyPoint(point_3d[axes[0]], point_3d[axes[1]])

    # outside = not within polygon
    return not shapely_point.within(poly)


def is_tip_likely_external(point_3d, bbox):
    """Heuristic: tips near bbox extremes in their primary axis are external.
    
    Criteria:
    - Y direction extremes (wing_tip): within 5% of yl from ymax/ymin
    - Z direction extremes (tail_tip): within 5% of zl from zmax/zmin
    - X direction extreme (nose): within 5% of xl from xmax
    - Local Y-extreme: |Y| > 50% of half-span from center
    - Local Z-extreme: |Z| > 50% of half-span from center
    """
    xl, yl, zl = bbox['xl'], bbox['yl'], bbox['zl']
    cx, cy, cz = bbox['center']
    
    # Y direction extremes (wing_tip)
    y_dist_top = abs(point_3d[1] - bbox['ymax'])
    y_dist_bot = abs(point_3d[1] - bbox['ymin'])
    if y_dist_top < yl * 0.05 or y_dist_bot < yl * 0.05:
        return True
    
    # Z direction extremes (tail_tip)
    z_dist_top = abs(point_3d[2] - bbox['zmax'])
    z_dist_bot = abs(point_3d[2] - bbox['zmin'])
    if z_dist_top < zl * 0.05 or z_dist_bot < zl * 0.05:
        return True
    
    # X direction extreme (nose tip / wing tip at X max)
    x_dist = abs(point_3d[0] - bbox['xmax'])
    if x_dist < xl * 0.05:
        return True
    
    # Local Y-extreme
    half_yl = abs(bbox['yl']) / 2
    if abs(point_3d[1]) > half_yl * 0.5:
        return True
    
    # Local Z-extreme
    half_zl = abs(bbox['zl']) / 2
    if abs(point_3d[2]) > half_zl * 0.5:
        return True
    
    return False


def classify_tips(tips_m, bbox, sharp_corners_by_view=None):
    """Classify tips as geometric direction type.
    
    Classification:
    - 'wing_tip': |dy| > yl/2 (Y direction extremum)
    - 'tail_tip': |dz| > zl/2 (Z direction extremum)
    - 'nose_tip': dx > xl/2 (X direction extremum at nose)
    - 'other': none of above
    
    Also tracks is_sharp (detected as sharp corner in 2+ views).
    """
    classified = []
    
    for tip in tips_m:
        dx = tip[0] - bbox['center'][0]
        dy = tip[1] - bbox['center'][1]
        dz = tip[2] - bbox['center'][1]
        
        # Check sharp corner status
        is_sharp = False
        if sharp_corners_by_view:
            sharp_count = 0
            for view_pts in sharp_corners_by_view.values():
                for pt_entry in view_pts:
                    pt3d = pt_entry['point_3d'] if isinstance(pt_entry, dict) else pt_entry
                    if np.linalg.norm(tip - pt3d) < 0.005:  # 5mm tolerance
                        sharp_count += 1
                        break
            is_sharp = sharp_count >= 2
        
        # Geometric classification
        xl, yl, zl = bbox['xl'], bbox['yl'], bbox['zl']
        geo_types = []
        if abs(dy) > yl / 2:
            geo_types.append('wing_tip')
        if abs(dz) > zl / 2:
            geo_types.append('tail_tip')
        if dx > xl / 2:
            geo_types.append('nose_tip')
        if not geo_types:
            geo_types.append('other')
        
        classified.append({
            'vertex': tip,
            'radial': float(np.linalg.norm(tip - bbox['center'])),
            'type': geo_types,
            'is_sharp': is_sharp,
        })
    
    return classified


def postprocess_dedup(tips_3d, bbox, tol_m):
    """Post-processing dedup: group points within BBox 5% and average.
    
    Uses max(bbox span) * 0.05 as grouping tolerance.
    Returns list of averaged tip points.
    """
    max_extent = max(bbox['xl'], bbox['yl'], bbox['zl'])
    group_tol = max_extent * 0.05

    if not tips_3d:
        return []

    all_pts = np.array(tips_3d)
    deduped = []
    used = [False] * len(all_pts)

    for i, pt in enumerate(all_pts):
        if used[i]:
            continue
        used[i] = True

        group = [pt]
        for j in range(i + 1, len(all_pts)):
            if used[j]:
                continue
            if np.linalg.norm(pt - all_pts[j]) < group_tol:
                group.append(all_pts[j])
                used[j] = True

        group = np.array(group)
        mean_pt = np.mean(group, axis=0)
        deduped.append(mean_pt)

    return [np.array(p) for p in deduped]


def match_3d_points(corners_by_view, tol_m):
    """Match sharp corners across 3 views -> 3D coordinates via triangulation.
    
    Strategy:
    1. For each pair of sharp corners (one from view A, one from view B),
       compute the 3D point that satisfies both projections
    2. Verify candidate matches in the third view
    3. Only keep points that match in ALL 3 views (with tolerance)
    
    Returns list of 3D numpy arrays.
    """
    # Collect sharp corners per view with their 2D coordinates
    corners_2d = {}
    for view, corners in corners_by_view.items():
        corners_2d[view] = []
        for c in corners:
            pt3d = c['point_3d']
            if view == 'XZ':
                pt2d = (pt3d[0], pt3d[2])
            elif view == 'YZ':
                pt2d = (pt3d[1], pt3d[2])
            else:  # XY
                pt2d = (pt3d[0], pt3d[1])
            corners_2d[view].append((pt3d, pt2d))
    
    if not corners_2d:
        return []
    
    view_names = ['XZ', 'YZ', 'XY']
    valid_3d_points = []
    
    for i, v1 in enumerate(view_names):
        for j, v2 in enumerate(view_names):
            if i >= j:
                continue
            for pt3d_a, pt2d_a in corners_2d[v1]:
                for pt3d_b, pt2d_b in corners_2d[v2]:
                    # Compute candidate 3D point
                    candidate = None
                    
                    if v1 == 'XZ' and v2 == 'YZ':
                        candidate = (pt2d_a[0], pt2d_b[0], pt2d_a[1])
                    elif v1 == 'XZ' and v2 == 'XY':
                        candidate = (pt2d_a[0], pt2d_a[1], pt2d_b[1])
                    elif v1 == 'YZ' and v2 == 'XY':
                        candidate = (pt2d_b[0], pt2d_b[1], pt2d_a[1])
                    
                    if candidate is None:
                        continue
                    
                    # Verify in the third view
                    third_view = [v for v in view_names if v != v1 and v != v2][0]
                    
                    if third_view == 'XZ':
                        proj_2d = (candidate[0], candidate[2])
                    elif third_view == 'YZ':
                        proj_2d = (candidate[1], candidate[2])
                    else:
                        proj_2d = (candidate[0], candidate[1])
                    
                    # Check if projected point matches any sharp corner
                    matches_third = False
                    for pt3d_c, pt2d_c in corners_2d[third_view]:
                        dist = abs(proj_2d[0] - pt2d_c[0]) + abs(proj_2d[1] - pt2d_c[1])
                        if dist < tol_m * 2:  # 2x tolerance for triangulation error
                            matches_third = True
                            break
                    
                    if matches_third:
                        valid_3d_points.append(np.array(candidate))
    
    # Dedup valid points
    deduped = []
    for p in valid_3d_points:
        if not any(np.linalg.norm(p - q) < tol_m for q in deduped):
            deduped.append(p)
    
    return deduped


def render_cam_with_tips(edge_points_list, tips_m, bbox, img_size=800):
    """Camera view rendering (tail-back). Mesh centered on screen.
    
    Camera configuration:
    - Direction: (-1, 1, 1) — tail-back view
    - Rotation: -90° X -> -45° Y -> +35.264° X
    - Canvas: 800x800, white background
    - Tip marker: red circle (r=4 filled, r=5 border)
    """
    img = np.full((img_size, img_size, 3), 255, dtype=np.uint8)

    max_extent = max(bbox['xl'], bbox['yl'], bbox['zl'])
    if max_extent == 0:
        max_extent = 1
    scale = (img_size * 0.7) / max_extent
    cos45 = np.cos(np.radians(45))
    sin45 = np.sin(np.radians(45))
    cos35 = np.cos(np.radians(35.264))
    sin35 = np.sin(np.radians(35.264))

    cx_screen = img_size // 2
    cy_screen = img_size // 2

    def _project(tx, ty, tz):
        ty2 = ty * np.cos(np.radians(-90)) - tz * np.sin(np.radians(-90))
        tz2 = ty * np.sin(np.radians(-90)) + tz * np.cos(np.radians(-90))
        rx = tx * cos45 + tz2 * sin45
        ry = ty2
        rz = -tx * sin45 + tz2 * cos45
        ry2 = ry * cos35 - rz * sin35
        sx = rx * scale + cx_screen
        sy = -ry2 * scale + cy_screen
        return sx, sy

    # Draw mesh edges — mid gray for clarity against white bg
    for pts in edge_points_list:
        tx = pts[:, 0] - bbox['center'][0]
        ty = pts[:, 1] - bbox['center'][1]
        tz = pts[:, 2] - bbox['center'][2]

        for i in range(len(pts) - 1):
            sx1, sy1 = _project(tx[i], ty[i], tz[i])
            sx2, sy2 = _project(tx[i+1], ty[i+1], tz[i+1])
            cv2.line(img, (int(round(sx1)), int(round(sy1))),
                     (int(round(sx2)), int(round(sy2))), (160, 160, 160), 1)

    # Draw tip markers — bright cyan circle with white halo for maximum contrast
    for tip in tips_m:
        tx = tip[0] - bbox['center'][0]
        ty = tip[1] - bbox['center'][1]
        tz = tip[2] - bbox['center'][2]

        sx, sy = _project(tx, ty, tz)
        # White halo (radius 8, filled)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 8, (255, 255, 255), -1)
        # Bright cyan ring (radius 7, width 2)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 7, (0, 255, 255), 2)
        # Bright cyan filled center (radius 5)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 5, (0, 255, 255), -1)

    return img


def main():
    parser = argparse.ArgumentParser(description='STL tip detection (2D orthographic projection + mesh edge graph)')
    parser.add_argument('input', help='Input STL file')
    parser.add_argument('output', nargs='?', default=None, help='Output CSV path')
    parser.add_argument('--tol', type=float, default=0.005, help='Tip merge tolerance (m, default: 0.005 = 5mm)')
    parser.add_argument('--sharp-angle', type=float, default=0.0, help='Sharp angle cos threshold (default: 0.0 = 90 deg)')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--unit', choices=['mm', 'm'], default='auto', help='Input unit (auto-detect by default)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    step_dir = os.path.dirname(os.path.abspath(args.input))
    step_name = os.path.splitext(os.path.basename(args.input))[0]

    print(f"{'='*60}")
    print(f"STL Tip Detection (2D orthographic projection + mesh edge graph)")
    print(f"{'='*60}")
    print(f"STL: {args.input}")
    print(f"Tolerance: {args.tol*1000:.1f} mm")
    print(f"Sharp angle cos threshold: {args.sharp_angle} (90 deg)")
    print(f"{'='*60}")

    # === [1/5] Load STL ===
    print("\n[1/5] Loading STL...")
    if args.unit == 'auto':
        mesh, detected_unit = load_stl(args.input)
        print(f"  Unit: {detected_unit} (auto-detected)")
    else:
        mesh = trimesh.load(args.input)
        if not isinstance(mesh, trimesh.Trimesh):
            if isinstance(mesh, trimesh.Scene):
                meshes = list(mesh.dump())
                if meshes:
                    mesh = trimesh.util.concatenate(meshes)
        if args.unit == 'mm':
            mesh.vertices *= 0.001
        print(f"  Unit: {args.unit}")

    bbox = get_bbox(mesh)
    edges = get_all_edges(mesh)
    print(f"  Edges: {len(edges)}")
    print(f"  BBox: X[{bbox['xmin']*1000:.2f}..{bbox['xmax']*1000:.2f}] "
          f"Y[{bbox['ymin']*1000:.2f}..{bbox['ymax']*1000:.2f}] "
          f"Z[{bbox['zmin']*1000:.2f}..{bbox['zmax']*1000:.2f}] mm")

    # === [2/5] Extract silhouette edges ===
    print("\n[2/5] Extracting silhouette edges...")
    silhouette_by_view = {}
    for view in ['XZ', 'YZ', 'XY']:
        silhouette = extract_silhouette_edges(edges, view, bbox)
        silhouette_by_view[view] = silhouette
        print(f"  [{view}] Silhouette edges: {len(silhouette)} / {len(edges)}")

    # === [3/5] Sharp corner detection ===
    print("\n[3/5] Sharp corner detection...")
    corners_by_view = {}

    for view in ['XZ', 'YZ', 'XY']:
        print(f"  [{view}] Building graph...")
        vertex_list, adj = build_2d_graph(edges, view, tol=args.tol)
        print(f"    Graph: {len(vertex_list)} vertices, {sum(len(n) for n in adj.values())//2} edges")

        sharp_vertices_2d = find_all_sharp_vertices(vertex_list, adj, sharp_cos_threshold=args.sharp_angle)
        sharp_3d = map_sharp_to_3d(sharp_vertices_2d, edges, view, tol_m=args.tol)

        # Within-view dedup
        unique_corners = []
        for pt3d in sharp_3d:
            if all(np.linalg.norm(pt3d - u['point_3d']) > args.tol for u in unique_corners):
                unique_corners.append({'point_3d': pt3d})

        corners_by_view[view] = unique_corners
        print(f"  [{view}] Unique corners: {len(unique_corners)}")

        if args.verbose:
            for c in unique_corners[:5]:
                p = c['point_3d']
                print(f"    ({p[0]*1000:.1f}, {p[1]*1000:.1f}, {p[2]*1000:.1f}) mm")

    # === [4/5] Triangulate + postprocess dedup ===
    print("\n[4/5] Triangulating + postprocessing...")
    tips_3d = match_3d_points(corners_by_view, args.tol)
    tips_3d = postprocess_dedup(tips_3d, bbox, args.tol)
    print(f"  Sharp-corner detected: {len(tips_3d)} tip(s)")

    # Fusion: DBSCAN-based tip detection
    if HAS_DBSCAN:
        tips_dbscan, dbscan_msg = find_tip_dbscan(mesh, tol=args.tol, verbose=args.verbose)
        print(f"  DBSCAN found: {len(tips_dbscan)} tip(s)")
    else:
        tips_dbscan = []

    # === [5/5] Merge, dedup, classify, output ===
    print("\n[5/5] Merging, dedup + classifying...")

    # Merge all candidates
    all_candidates = tips_3d + [np.array(t) for t in tips_dbscan]
    print(f"  Total candidates: {len(all_candidates)}")

    # Dedup with 5% of bbox max span
    dedup_tol = max(bbox['xl'], bbox['yl'], bbox['zl']) * 0.05
    merged = []
    for tip in all_candidates:
        if isinstance(tip, dict):
            tip = tip['vertex']
        if not isinstance(tip, np.ndarray):
            tip = np.array(tip)
        found = False
        for m in merged:
            if np.linalg.norm(tip - m) < dedup_tol:
                m[:] = (m + tip) / 2.0
                found = True
                break
        if not found:
            merged.append(tip)
    print(f"  After dedup ({dedup_tol*1000:.1f} mm tol): {len(merged)} tips")

    # Classify all
    classified_all = []
    for tip in merged:
        c = classify_tips([tip], bbox, corners_by_view)
        if c:
            classified_all.append(c[0])

    # Compute outside count for each
    for c in classified_all:
        tip = c['vertex']
        outside_count = 0
        for view in ['XZ', 'YZ', 'XY']:
            if check_point_outside_contour(tip, silhouette_by_view[view], view, tol_m=args.tol):
                outside_count += 1
        c['outside_count'] = outside_count

    # Filter: keep sharp corners or near bbox extremes
    edge_threshold = max(bbox['xl'], bbox['yl'], bbox['zl']) * 0.45
    filtered = []
    for c in classified_all:
        tip = c['vertex']
        cx, cy, cz = bbox['center']
        dx = abs(tip[0] - cx)
        dy = abs(tip[1] - cy)
        dz = abs(tip[2] - cz)
        
        is_sharp = c.get('is_sharp', False)
        is_likely_ext = is_tip_likely_external(tip, bbox)
        
        # Real tip = sharp corner detected OR near bbox/extent extreme
        is_real_tip = is_sharp or is_likely_ext
        
        if is_real_tip:
            filtered.append(c)
            ext_label = 'sharp' if is_sharp else 'ext'
            print(f"  [KEEP {ext_label}] Tip ({tip[0]*1000:.1f}, {tip[1]*1000:.1f}, {tip[2]*1000:.1f}) mm "
                  f"{'/'.join(c['type'])} (outside={c['outside_count']})")

    # Type-specific clustering
    final_tips = []
    by_type = {}
    for c in filtered:
        t = c['type'][0]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(c)
    
    max_extent = max(bbox['xl'], bbox['yl'], bbox['zl'])
    
    for t_type, items in by_type.items():
        cluster = []
        for c in items:
            found = False
            for f in cluster:
                tip = c['vertex']
                base = f['vertex']
                
                if t_type == 'wing_tip':
                    if abs(tip[0]-base[0]) < max_extent*0.05 and abs(tip[2]-base[2]) < max_extent*0.025:
                        f['vertex'] = (f['vertex'] + c['vertex']) / 2.0
                        f['outside_count'] = max(f['outside_count'], c['outside_count'])
                        found = True
                elif t_type == 'tail_tip':
                    if abs(tip[1]-base[1]) < max_extent*0.05 and abs(tip[2]-base[2]) < max_extent*0.05:
                        f['vertex'] = (f['vertex'] + c['vertex']) / 2.0
                        f['outside_count'] = max(f['outside_count'], c['outside_count'])
                        found = True
                elif t_type == 'nose_tip':
                    if abs(tip[1]-base[1]) < max_extent*0.05 and abs(tip[2]-base[2]) < max_extent*0.05:
                        f['vertex'] = (f['vertex'] + c['vertex']) / 2.0
                        f['outside_count'] = max(f['outside_count'], c['outside_count'])
                        found = True
                else:
                    if np.linalg.norm(tip - base) < max_extent * 0.05:
                        f['vertex'] = (f['vertex'] + c['vertex']) / 2.0
                        f['outside_count'] = max(f['outside_count'], c['outside_count'])
                        found = True
            if not found:
                cluster.append(c)
        final_tips.extend(cluster)
    
    filtered = final_tips
    print(f"\n  After type-specific clustering: {len(filtered)} tips")

    # Print final results
    tips_csv = []
    for i, c in enumerate(filtered):
        v = c['vertex']
        src = 'sharp' if i < len(tips_3d) else 'dbscan'
        print(f"  Tip {i+1}: ({v[0]*1000:8.2f}, {v[1]*1000:8.2f}, {v[2]*1000:8.2f}) mm [{src}] -> {'/'.join(c['type'])}")
        tips_csv.append([v[0], v[1], v[2]])

    # CSV output
    csv_path = args.output or f"{os.path.splitext(args.input)[0]}_tip_points.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        for tp in tips_csv:
            writer.writerow([f"{tp[0]:.6f}", f"{tp[1]:.6f}", f"{tp[2]:.6f}"])
    print(f"  CSV: {csv_path} ({len(tips_csv)} points)")

    # Camera view PNG
    print("\n  Saving camera view (tail-back)...")
    edge_points_list = []
    for e in edges:
        v0, v1 = e
        edge_points_list.append(np.array([v0, v1]))

    png_path = os.path.join(step_dir, f"{step_name}_tip_cam.png")
    cam = render_cam_with_tips(edge_points_list, tips_csv, bbox, img_size=800)
    cv2.imwrite(png_path, cam)
    print(f"  PNG: {png_path}")

    print(f"\n{'='*60}")
    print(f"Done! {len(tips_csv)} tips detected.")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
