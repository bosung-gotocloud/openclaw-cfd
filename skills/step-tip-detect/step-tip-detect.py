#!/usr/bin/env python3
"""
step-tip-detect — STEP 파일에서 tip 포인트 검출 (Hybrid: Graph Sharp Corner + DBSCAN Fusion + Convexity Check)

Algorithm:
  Approach 1: STEP edges graph sharp corner detection (>90 deg)
  Approach 2: DBSCAN-based radial clustering (vertex distribution 분석)
  Fusion: merge candidates + convexity check + silhouette contour filtering
  Classification: wing_tip / tail_tip / other

Dependencies:
    - pip install cadquery numpy opencv-python shapely scipy scikit-learn
"""

import sys
import os
import math
import numpy as np
import csv
import argparse
from collections import defaultdict

try:
    import cadquery as cq
except ImportError:
    print("ERROR: cadquery가 설치되어 있지 않습니다.")
    sys.exit(1)

try:
    from sklearn.cluster import DBSCAN
    HAS_DBSCAN = True
except ImportError:
    HAS_DBSCAN = False


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


def extract_face_normals(shape):
    """STEP faces의 normal vectors 추출 (CAD 좌표계 기준).
    
    Returns list of (face, normal_vector) tuples.
    """
    faces = list(shape.Faces())
    normals = []
    for f in faces:
        try:
            # face center
            center = np.array([f.Center().X, f.Center().Y, f.Center().Z])
            # face normal (outward)
            geo = f.geomAdapter
            normal = geo.normalAt(0.5, 0.5) if hasattr(geo, 'normalAt') else None
            if normal is not None:
                nx, ny, nz = normal.X, normal.Y, normal.Z
                n_len = np.sqrt(nx*nx + ny*ny + nz*nz)
                if n_len > 1e-10:
                    normals.append((center, np.array([nx/n_len, ny/n_len, nz/n_len])))
        except:
            pass
    return normals


def extract_face_edges(shape):
    """각 face의 edges를 추출하여 face-edge mapping 생성."""
    faces = list(shape.Faces())
    face_edges = []
    for f in faces:
        try:
            edges = list(f.Edges())
            if edges:
                # face centroid
                fc = np.array([f.Center().X, f.Center().Y, f.Center().Z])
                face_edges.append((fc, edges))
        except:
            pass
    return face_edges


def find_tip_dbscan(shape, tol_mm=5.0):
    """DBSCAN-based tip detection on STEP vertices (Hybrid Approach 2).
    
    Multi-directional radial clustering on STEP native vertices via tessellation.
    Returns tips in mm (cadquery coordinate system).
    
    Logic (adapted from stl-tip-detect):
    1. Collect all STEP native vertices from faces via tessellation
    2. 3-direction projection: YZ/XZ/XY
    3. Face centroid-based radial calculation
    4. Multi-percentile thresholding (30%, 50%, 70th percentile)
    5. Downsample if > 50000 vertices
    6. Normalize -> isotropic clustering
    7. Adaptive DBSCAN
    8. Peak selection -> tip candidates
    """
    if not HAS_DBSCAN:
        return [], "DBSCAN not available (pip install scikit-learn)"
    
    # Collect all vertices from all faces via tessellation
    faces = list(shape.Faces())
    all_verts = []
    face_centroids = []
    
    for f in faces:
        try:
            # tessellate to get surface vertices
            verts_list, _ = f.tessellate(1.0)
            for v in verts_list:
                all_verts.append(np.array([v.x, v.y, v.z]))
            # face centroid
            center = f.Center()
            face_centroids.append(np.array([center.x, center.y, center.z]))
        except Exception:
            continue
    
    all_verts = np.array(all_verts)
    if len(all_verts) < 50:
        return [], "Too few vertices for DBSCAN"
    
    face_centroid_mean = np.mean(face_centroids, axis=0) if face_centroids else np.zeros(3)
    tip_candidates = []
    
    max_verts = 50000
    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
        # Project vertices to 2D (face centroid as origin)
        verts_2d = all_verts[:, [axis1, axis2]]
        origin_2d = face_centroid_mean[[axis1, axis2]]
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
            if len(high_indices) > max_verts:
                rng = np.random.RandomState(42)
                idx = rng.choice(len(high_indices), max_verts, replace=False)
                high_coords = high_coords[idx]
                high_indices = high_indices[idx]
                high_radial = high_radial[idx]
            
            # Normalize for isotropic clustering
            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale
            
            # Adaptive DBSCAN
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
                tip_candidates.append(all_verts[peak_idx_3d].copy())
    
    # Dedup by 3D distance
    tips = []
    for t in tip_candidates:
        if not any(np.linalg.norm(t - q) < tol_mm for q in tips):
            tips.append(t)
    
    tips = tips[:20]
    msg = f"DBSCAN found {len(tips)} tip(s)"
    return tips, msg


def extract_silhouette_edges(edges_3d, view, bbox):
    """edges를 projection direction에서 silhouette만 추출."""
    hide_map = {'XZ': 1, 'YZ': 0, 'XY': 2}
    global_min_map = {'XZ': 'ymin', 'YZ': 'xmin', 'XY': 'zmin'}
    global_max_map = {'XZ': 'ymax', 'YZ': 'xmax', 'XY': 'zmax'}
    
    hide_axis = hide_map[view]
    global_min = bbox[global_min_map[view]]
    global_max = bbox[global_max_map[view]]
    global_span = global_max - global_min
    margin = max(global_span * 0.01, 5.0)
    
    silhouette_edges = []
    for e in edges_3d:
        pts, _ = e.sample(50)
        pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
        
        if hide_axis == 0:
            edge_min, edge_max = pts_arr[:, 0].min(), pts_arr[:, 0].max()
        elif hide_axis == 1:
            edge_min, edge_max = pts_arr[:, 1].min(), pts_arr[:, 1].max()
        else:
            edge_min, edge_max = pts_arr[:, 2].min(), pts_arr[:, 2].max()
        
        if (edge_min >= global_min - margin and edge_min <= global_min + margin) or \
           (edge_max >= global_max - margin and edge_max <= global_max + margin):
            silhouette_edges.append(e)
    
    return silhouette_edges


def build_2d_graph(edges_3d, view, tol=1.0):
    """모든 3D edges를 view 방향으로 투영 -> 2D graph 구성."""
    vertex_set = set()
    edge_pairs = []
    
    for e in edges_3d:
        pts, _ = e.sample(2)
        pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
        if len(pts_arr) < 2:
            continue
        
        if view == 'XZ':
            p0 = np.array([pts_arr[0, 0], pts_arr[0, 2]])
            p1 = np.array([pts_arr[1, 0], pts_arr[1, 2]])
        elif view == 'YZ':
            p0 = np.array([pts_arr[0, 1], pts_arr[0, 2]])
            p1 = np.array([pts_arr[1, 1], pts_arr[1, 2]])
        else:
            p0 = np.array([pts_arr[0, 0], pts_arr[0, 1]])
            p1 = np.array([pts_arr[1, 0], pts_arr[1, 1]])
        
        s0 = (round(p0[0]/tol)*tol, round(p0[1]/tol)*tol)
        s1 = (round(p1[0]/tol)*tol, round(p1[1]/tol)*tol)
        
        vertex_set.add(s0)
        vertex_set.add(s1)
        edge_pairs.append((s0, s1))
    
    vertex_list = sorted(vertex_set)
    v2idx = {v: i for i, v in enumerate(vertex_list)}
    
    adj = defaultdict(set)
    for s0, s1 in edge_pairs:
        i0, i1 = v2idx[s0], v2idx[s1]
        if i0 != i1:
            adj[i0].add(i1)
            adj[i1].add(i0)
    
    return vertex_list, adj


def find_all_sharp_vertices(vertex_list, adj, sharp_cos_threshold=0.0):
    """graph에서 모든 vertex의 angle 분석 -> sharp corners (>90 deg)."""
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


def map_sharp_to_3d(sharp_2d_pts, edges_3d, view, tol_mm=5.0):
    """2D sharp vertex를 3D 원본 edge에서 매핑."""
    candidates_3d = []
    
    for pt2d in sharp_2d_pts:
        best_match = None
        best_dist = float('inf')
        
        for e in edges_3d:
            pts, _ = e.sample(2)
            pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
            if len(pts_arr) < 2:
                continue
            
            if view == 'XZ':
                line_2d = np.array([[pts_arr[0, 0], pts_arr[0, 2]], [pts_arr[1, 0], pts_arr[1, 2]]])
            elif view == 'YZ':
                line_2d = np.array([[pts_arr[0, 1], pts_arr[0, 2]], [pts_arr[1, 1], pts_arr[1, 2]]])
            else:
                line_2d = np.array([[pts_arr[0, 0], pts_arr[0, 1]], [pts_arr[1, 0], pts_arr[1, 1]]])
            
            line_vec = line_2d[1] - line_2d[0]
            line_len = np.linalg.norm(line_vec)
            if line_len < 1e-10:
                continue
            
            t = np.dot(pt2d - line_2d[0], line_vec) / (line_len ** 2)
            t = max(0, min(1, t))
            proj_pt = line_2d[0] + t * line_vec
            
            dist = np.linalg.norm(pt2d - proj_pt)
            
            if dist < best_dist and dist < tol_mm:
                best_dist = dist
                best_match = pts_arr[0] if t < 0.5 else pts_arr[1]
        
        if best_match is not None:
            candidates_3d.append(best_match)
    
    return candidates_3d


def find_silhouette_contour(silhouette_edges, view):
    """silhouette edges에서 closed loop polygon contour를 구성."""
    hide_map = {'XZ': 1, 'YZ': 0, 'XY': 2}
    axes_map = {'XZ': (0, 2), 'YZ': (1, 2), 'XY': (0, 1)}
    axes = axes_map[view]
    
    lines = []
    for e in silhouette_edges:
        pts, _ = e.sample(50)
        for i in range(len(pts) - 1):
            p0 = np.array([pts[i].x, pts[i].y, pts[i].z])
            p1 = np.array([pts[i+1].x, pts[i+1].y, pts[i+1].z])
            lines.append((np.array([p0[axes[0]], p0[axes[1]]]), np.array([p1[axes[0]], p1[axes[1]]])))
    
    tol = 5.0
    endpoints = {}
    for l0, l1 in lines:
        for pt in [l0, l1]:
            key = (round(pt[0]/tol)*tol, round(pt[1]/tol)*tol)
            if key not in endpoints:
                endpoints[key] = [pt]
            else:
                endpoints[key].append(pt)
    
    if not endpoints:
        return None
    
    adj = defaultdict(list)
    keys = list(endpoints.keys())
    k2i = {k: i for i, k in enumerate(keys)}
    
    for l0, l1 in lines:
        k0 = (round(l0[0]/tol)*tol, round(l0[1]/tol)*tol)
        k1 = (round(l1[0]/tol)*tol, round(l1[1]/tol)*tol)
        if k0 in k2i and k1 in k2i:
            adj[k2i[k0]].append(k2i[k1])
            adj[k2i[k1]].append(k2i[k0])
    
    visited = set()
    contour = []
    start = 0
    
    odd_deg = [i for i in adj if len(adj[i]) % 2 == 1]
    if odd_deg:
        start = odd_deg[0]
    
    curr = start
    prev = None
    for _ in range(len(adj)):
        visited.add(curr)
        contour.append(keys[curr])
        neighbors = adj[curr]
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


def check_point_outside_contour(point_3d, silhouette_edges, view, tol_mm=5.0):
    """tip point가 silhouette contour polygon의 바깥에 있는지 판별."""
    from shapely.geometry import Polygon, Point as ShapelyPoint
    
    contour = find_silhouette_contour(silhouette_edges, view)
    
    if contour is None or len(contour) < 3:
        return True
    
    poly = Polygon(contour).buffer(0)
    
    axes_map = {'XZ': (0, 2), 'YZ': (1, 2), 'XY': (0, 1)}
    axes = axes_map[view]
    shapely_point = ShapelyPoint(point_3d[axes[0]], point_3d[axes[1]])
    
    is_outside = not shapely_point.within(poly)
    return is_outside


# ===== NEW: Convexity Check Enhancement =====

def check_face_normal_convexity(tip_candidate, shape, bbox):
    """tip candidate가 external surface에 위치하는지 convexity check.
    
    face normal outward dot product > 0.3 -> external (convex surface)
    face normal outward dot product < -0.3 -> internal (concave surface)
    
    Enhanced version:
    1. tip에 가장 가까운 face의 normal 방향 분석
    2. tip에서 bbox 중심까지의 vector와 face normal의 dot product
    3. 외부 돌출부: tip에서 외향 normal과 같은 방향
    """
    faces = list(shape.Faces())
    if not faces:
        return 0.0  # unknown
    
    tip = np.array(tip_candidate)
    center = bbox['center']
    
    best_score = 0.0
    
    for f in faces:
        try:
            fc = np.array([f.Center().X, f.Center().Y, f.Center().Z])
            dist = np.linalg.norm(tip - fc)
            if dist > max(bbox['xl'], bbox['yl'], bbox['zl']) * 0.1:
                continue  # far from this face
            
            # face normal
            geo = f.geomAdapter
            normal = geo.normalAt(0.5, 0.5) if hasattr(geo, 'normalAt') else None
            if normal is None:
                continue
            
            nx, ny, nz = normal.X, normal.Y, normal.Z
            n_len = np.sqrt(nx*nx + ny*ny + nz*nz)
            if n_len < 1e-10:
                continue
            normal = np.array([nx/n_len, ny/n_len, nz/n_len])
            
            # tip에서 outward direction (tip -> away from body center)
            outward = tip - center
            o_len = np.linalg.norm(outward)
            if o_len < 1e-10:
                continue
            outward = outward / o_len
            
            # dot product: positive = same direction (external convex)
            dot = np.dot(normal, outward)
            
            # Also check local edge curvature
            edge_edges = list(f.Edges())
            if edge_edges:
                # Check edge curvature near tip
                for edge in edge_edges:
                    pts, _ = edge.sample(10)
                    pts_arr = np.array([[p.X, p.Y, p.Z] for p in pts])
                    edge_center = np.mean(pts_arr, axis=0)
                    edge_tip_dist = np.linalg.norm(tip - edge_center)
                    if edge_tip_dist < 10.0:  # 10mm tolerance
                        # Check edge curvature (approximate)
                        if len(pts_arr) >= 3:
                            # Compute local curvature via tangent angle
                            for i in range(1, len(pts_arr)-1):
                                tangent_prev = pts_arr[i] - pts_arr[i-1]
                                tangent_next = pts_arr[i+1] - pts_arr[i]
                                tp_len = np.linalg.norm(tangent_prev)
                                tn_len = np.linalg.norm(tangent_next)
                                if tp_len > 1e-10 and tn_len > 1e-10:
                                    tangent_prev /= tp_len
                                    tangent_next /= tn_len
                                    cos_tangent = np.dot(tangent_prev, tangent_next)
                                    if cos_tangent < 0.5:  # > 60 deg local curvature
                                        dot += 0.1  # boost score for curved edges
        
            if dot > best_score:
                best_score = dot
        except:
            continue
    
    return best_score


def classify_tips(tips_mm, bbox, corners_by_view=None):
    """tip을 wing_tip / tail_tip / nose로 분류."""
    center = bbox['center']
    xl, yl, zl = bbox['xl'], bbox['yl'], bbox['zl']
    classified = []
    
    for tip in tips_mm:
        dx, dy, dz = tip[0] - center[0], tip[1] - center[1], tip[2] - center[2]
        
        if dx < 0:
            continue
        
        # Check sharp corner status
        is_sharp = False
        if corners_by_view:
            sharp_count = 0
            for view_pts in corners_by_view.values():
                for pt_entry in view_pts:
                    pt3d = pt_entry['point_3d'] if isinstance(pt_entry, dict) else pt_entry
                    if np.linalg.norm(np.array(tip) - np.array(pt3d)) < 5.0:  # 5mm tolerance
                        sharp_count += 1
                        break
            is_sharp = sharp_count >= 2
        
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
            'is_sharp': is_sharp,
        })
    
    return classified


def is_tip_likely_external(point_3d, bbox):
    """Heuristic: tips near bbox extremes in their primary axis are external."""
    xl, yl, zl = bbox['xl'], bbox['yl'], bbox['zl']
    
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


def postprocess_dedup(tips_3d, bbox, tol_mm):
    """3D 재조립 후 후처리 dedup. BBox 5% 이내 점들 평균."""
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


def match_3d_points(corners_by_view, tol_mm):
    """3-direction 매칭 -> dedup."""
    all_pts = []
    for view, corners in corners_by_view.items():
        for c in corners:
            pt = c['point_3d']
            all_pts.append([pt[0], pt[1], pt[2]])
    
    if not all_pts:
        return []
    
    all_pts = np.array(all_pts)
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
            if abs(pt[1] - all_pts[j][1]) < tol_mm and abs(pt[2] - all_pts[j][2]) < tol_mm:
                group.append(all_pts[j])
                used[j] = True
        
        group = np.array(group)
        best_idx = np.argmax(group[:, 0])
        deduped.append(group[best_idx])
    
    return [np.array(p) for p in deduped]


def render_cam_with_tips(points_list, tips_mm, bbox, img_size=800):
    """Camera view rendering (tail-back). Aircraft center at screen center."""
    import cv2
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
    
    for pts in points_list:
        tx = pts[:, 0] - bbox['center'][0]
        ty = pts[:, 1] - bbox['center'][1]
        tz = pts[:, 2] - bbox['center'][2]
        
        for i in range(len(pts) - 1):
            sx1, sy1 = _project(tx[i], ty[i], tz[i])
            sx2, sy2 = _project(tx[i+1], ty[i+1], tz[i+1])
            cv2.line(img, (int(round(sx1)), int(round(sy1))), (int(round(sx2)), int(round(sy2))), (40, 40, 40), 1)
    
    for tip in tips_mm:
        tx = tip[0] - bbox['center'][0]
        ty = tip[1] - bbox['center'][1]
        tz = tip[2] - bbox['center'][2]
        
        sx, sy = _project(tx, ty, tz)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 4, (220, 40, 40), -1)
        cv2.circle(img, (int(round(sx)), int(round(sy))), 5, (180, 20, 20), 2)
    
    return img


def main():
    parser = argparse.ArgumentParser(description='STEP tip detection (Hybrid: Graph Sharp Corner + DBSCAN Fusion + Convexity Check)')
    parser.add_argument('input', help='Input STEP file')
    parser.add_argument('output', nargs='?', default=None, help='Output CSV path')
    parser.add_argument('--tol', type=float, default=5.0, help='Tip merge tolerance (mm)')
    parser.add_argument('--sharp-angle', type=float, default=0.0, help='Sharp angle cos threshold (default: 0.0 = 90 deg)')
    parser.add_argument('--no-dbscan', action='store_true', help='Disable DBSCAN fusion')
    parser.add_argument('--no-convexity', action='store_true', help='Disable convexity check')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)
    
    step_dir = os.path.dirname(os.path.abspath(args.input))
    step_name = os.path.splitext(os.path.basename(args.input))[0]
    
    use_dbscan = HAS_DBSCAN and not args.no_dbscan
    
    print(f"{'='*60}")
    print(f"STEP Tip Detection v5 (Hybrid: Graph Sharp Corner + DBSCAN Fusion)")
    print(f"{'='*60}")
    print(f"STEP: {args.input}")
    print(f"Tolerance: {args.tol:.1f} mm")
    print(f"Sharp angle cos threshold: {args.sharp_angle} (90 deg)")
    print(f"DBSCAN fusion: {'ENABLED' if use_dbscan else 'DISABLED'}")
    print(f"Convexity check: {'ENABLED' if not args.no_convexity else 'DISABLED'}")
    print(f"{'='*60}")
    
    # 1. Load STEP
    print("\n[1/7] Loading STEP...")
    declared_unit = read_step_header_unit(args.input)
    used_unit = declared_unit if declared_unit else 'MM'
    print(f"  Unit: {used_unit}")
    
    shape_mm = cq.importers.importStep(args.input, unit='MM').val()
    
    faces = list(shape_mm.Faces())
    edges = get_all_edges(shape_mm)
    print(f"  Faces: {len(faces)}, Edges: {len(edges)}")
    
    bbox = get_bbox(shape_mm)
    print(f"  BBox: X[{bbox['xmin']:.2f}..{bbox['xmax']:.2f}] Y[{bbox['ymin']:.2f}..{bbox['ymax']:.2f}] Z[{bbox['zmin']:.2f}..{bbox['zmax']:.2f}]")
    
    # 2. Per-view: extract silhouette edges
    print("\n[2/7] Extracting silhouette edges...")
    silhouette_by_view = {}
    for view in ['XZ', 'YZ', 'XY']:
        silhouette = extract_silhouette_edges(edges, view, bbox)
        silhouette_by_view[view] = silhouette
        print(f"  [{view}] Silhouette edges: {len(silhouette)} / {len(edges)}")
    
    # 3. Per-view: build graph + sharp corner (Approach 1)
    print("\n[3/7] Sharp corner detection (Approach 1: Graph)...")
    corners_by_view = {}
    
    for view in ['XZ', 'YZ', 'XY']:
        print(f"  [{view}] Building graph...")
        vertex_list, adj = build_2d_graph(edges, view, tol=args.tol)
        print(f"    Graph: {len(vertex_list)} vertices, {sum(len(n) for n in adj.values())//2} edges")
        
        sharp_vertices_2d = find_all_sharp_vertices(vertex_list, adj, sharp_cos_threshold=args.sharp_angle)
        sharp_3d = map_sharp_to_3d(sharp_vertices_2d, edges, view, tol_mm=args.tol)
        
        unique_corners = []
        for pt3d in sharp_3d:
            if all(np.linalg.norm(pt3d - u['point_3d']) > args.tol for u in unique_corners):
                unique_corners.append({'point_3d': pt3d})
        
        corners_by_view[view] = unique_corners
        print(f"  [{view}] Unique corners: {len(unique_corners)}")
        
        if args.verbose:
            for c in unique_corners[:5]:
                p = c['point_3d']
                print(f"    ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})")
    
    # 4. Triangulate + postprocess dedup
    print("\n[4/7] Triangulating + postprocessing (Approach 1)...")
    tips_graph = match_3d_points(corners_by_view, args.tol)
    tips_graph = postprocess_dedup(tips_graph, bbox, args.tol)
    print(f"  Sharp-corner detected: {len(tips_graph)} tip(s)")
    
    # 5. DBSCAN-based radial clustering (Approach 2)
    tips_dbscan = []
    if use_dbscan:
        print("\n[5/7] DBSCAN radial clustering (Approach 2)...")
        tips_dbscan, dbscan_msg = find_tip_dbscan(shape_mm, tol_mm=args.tol)
        print(f"  {dbscan_msg}")
    
    # 6. Fusion: merge + filter
    print("\n[6/7] Fusion: merge candidates + filter...")
    
    # Merge all candidates
    all_candidates = tips_graph + [np.array(t) for t in tips_dbscan]
    print(f"  Total candidates: {len(tips_graph)} (sharp) + {len(tips_dbscan)} (dbscan) = {len(all_candidates)}")
    
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
    print(f"  After dedup ({dedup_tol:.1f} mm tol): {len(merged)} tips")
    
    # Classify + filter
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
            if check_point_outside_contour(tip, silhouette_by_view[view], view, tol_mm=args.tol):
                outside_count += 1
        c['outside_count'] = outside_count
    
    # Convexity check for each
    if not args.no_convexity:
        for c in classified_all:
            tip = c['vertex']
            c['convexity_score'] = check_face_normal_convexity(tip, shape_mm, bbox)
    else:
        for c in classified_all:
            c['convexity_score'] = 0.0
    
    # Filter: keep based on hybrid criteria
    # Real tip = sharp corner detected OR near bbox extremes OR convex external
    filtered = []
    for c in classified_all:
        tip = c['vertex']
        is_sharp = c.get('is_sharp', False)
        is_likely_ext = is_tip_likely_external(tip, bbox)
        is_convex_ext = c.get('convexity_score', 0.0) > 0.3  # convex external surface
        outside_count = c.get('outside_count', 0)
        
        # External check: 2+ views outside silhouette
        is_external = outside_count >= 2
        
        # Keep if:
        # - sharp corner detected, OR
        # - near bbox extreme, OR
        # - convex external surface, OR
        # - silhouette outside AND (convex OR extreme)
        is_real_tip = is_sharp or is_likely_ext or is_convex_ext or (is_external and (is_convex_ext or is_likely_ext))
        
        if is_real_tip:
            ext_label = []
            if is_sharp: ext_label.append('sharp')
            if is_likely_ext: ext_label.append('ext')
            if is_convex_ext: ext_label.append('convex')
            if is_external: ext_label.append('outside')
            
            print(f"  [KEEP {'/'.join(ext_label)}] Tip ({tip[0]:8.2f}, {tip[1]:8.2f}, {tip[2]:8.2f}) mm "
                  f"{'/'.join(c['type'])} (outside={c['outside_count']}, convex={c['convexity_score']:.3f})")
            filtered.append(c)
        else:
            if args.verbose:
                print(f"  [SKIP] Tip ({tip[0]:8.2f}, {tip[1]:8.2f}, {tip[2]:8.2f}) mm "
                      f"{'/'.join(c['type'])} (sharp={is_sharp}, ext={is_likely_ext}, "
                      f"convex={c['convexity_score']:.3f}, outside={outside_count})")
    
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
    
    # 7. Output
    print("\n[7/7] Output...")
    tips_csv = []
    for i, c in enumerate(filtered):
        v = c['vertex']
        src = 'sharp' if i < len(tips_graph) else 'dbscan'
        print(f"  Tip {i+1}: ({v[0]:8.2f}, {v[1]:8.2f}, {v[2]:8.2f}) mm [{src}] -> {'/'.join(c['type'])}")
        tips_csv.append([v[0], v[1], v[2]])
    
    # CSV output
    csv_path = args.output or f"{os.path.splitext(args.input)[0]}_tip_points.csv"
    tips_m = [[tp[0]/1000.0, tp[1]/1000.0, tp[2]/1000.0] for tp in tips_csv]
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        for tp in tips_m:
            writer.writerow([f"{tp[0]:.6f}", f"{tp[1]:.6f}", f"{tp[2]:.6f}"])
    print(f"  CSV: {csv_path} ({len(tips_m)} points)")
    
    # Edge points for rendering
    edge_points_list = []
    for e in edges:
        try:
            pts, _ = e.sample(100)
            pts_arr = np.array([[p.x, p.y, p.z] for p in pts])
            if len(pts_arr) >= 2:
                edge_points_list.append(pts_arr)
        except:
            continue
    
    # Camera view PNG
    print("\n  Saving camera view (tail-back) ...")
    png_path = os.path.join(step_dir, f"{step_name}_tip_cam.png")
    cam = render_cam_with_tips(edge_points_list, tips_graph, bbox, img_size=800)
    import cv2
    cv2.imwrite(png_path, cam)
    print(f"  PNG: {png_path}")
    
    print(f"\n{'='*60}")
    print(f"Done! {len(tips_m)} tips detected.")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
