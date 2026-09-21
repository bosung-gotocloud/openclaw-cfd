#!/usr/bin/env python3
"""step_compare_tips.py — 3가지 tip 검출 방법 비교"""

import sys
import os
import numpy as np
import csv

import cadquery as cq


def load_step(path):
    wp = cq.importers.importStep(path)
    return wp.val()


def tessellate(shape, target_size):
    verts_list, faces_list = shape.tessellate(target_size)
    if verts_list is None or len(verts_list) == 0:
        return None, None
    verts = np.array([[v.x, v.y, v.z] for v in verts_list])
    faces = np.array(faces_list)
    return verts, faces


# === METHOD 1: Normal variance (curvature) ===
def find_tips_method1(shape, h1=0.0001, nlayers=10, growth=1.3, top_k_ratio=0.01):
    """인접 face normal의 분산이 큰 vertex를 tip으로 검출."""
    T = h1 * (growth ** nlayers - 1) / (growth - 1)
    smallest_face_diag = float('inf')
    for face in shape.Faces():
        try:
            vl, _ = face.tessellate(1.0)
            if vl is None or len(vl) == 0:
                continue
            va = np.array([[v.x, v.y, v.z] for v in vl])
            diag = np.linalg.norm(va.max(axis=0) - va.min(axis=0))
            if diag > 1e-15 and diag < smallest_face_diag:
                smallest_face_diag = diag
        except Exception:
            continue
    min_surf_size = min(2.0 * T, smallest_face_diag)
    verts, faces = tessellate(shape, min_surf_size)
    if verts is None:
        return []

    # face normals
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-15)
    normals = normals / lengths

    # vertex-face adjacency
    n_verts = verts.shape[0]
    vertex_faces = [[] for _ in range(n_verts)]
    for fi, face in enumerate(faces):
        for vi in face:
            vertex_faces[vi].append(fi)

    # normal variance per vertex
    scores = np.zeros(n_verts)
    for vi in range(n_verts):
        fi_list = vertex_faces[vi]
        if len(fi_list) < 3:
            continue
        n_at_v = normals[fi_list]
        mean_n = np.mean(n_at_v, axis=0)
        mean_n /= np.linalg.norm(mean_n) + 1e-15
        variance = np.sum((n_at_v - mean_n) ** 2)
        scores[vi] = variance

    # top_k_ratio 상위만 tip
    n_tips = max(1, int(len(scores) * top_k_ratio))
    top_indices = np.argsort(scores)[-n_tips:]
    tips = [verts[vi].copy() for vi in top_indices]
    return tips


# === METHOD 2: Sphere fitting radius ===
def find_tips_method2(shape, h1=0.0001, nlayers=10, growth=1.3, top_k_ratio=0.01, sphere_tol=0.001):
    """각 vertex에 sphere fitting → 곡률 반지름이 작은 vertex를 tip."""
    T = h1 * (growth ** nlayers - 1) / (growth - 1)
    smallest_face_diag = float('inf')
    for face in shape.Faces():
        try:
            vl, _ = face.tessellate(1.0)
            if vl is None or len(vl) == 0:
                continue
            va = np.array([[v.x, v.y, v.z] for v in vl])
            diag = np.linalg.norm(va.max(axis=0) - va.min(axis=0))
            if diag > 1e-15 and diag < smallest_face_diag:
                smallest_face_diag = diag
        except Exception:
            continue
    min_surf_size = min(2.0 * T, smallest_face_diag)
    verts, faces = tessellate(shape, min_surf_size)
    if verts is None:
        return []

    # vertex-face adjacency
    n_verts = verts.shape[0]
    vertex_faces = [[] for _ in range(n_verts)]
    for fi, face in enumerate(faces):
        for vi in face:
            vertex_faces[vi].append(fi)

    face_normals = np.zeros((len(faces), 3))
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-15)
    face_normals = normals / lengths

    # normal variance로 top 5%만 sphere fitting
    scores = np.zeros(n_verts)
    for vi in range(n_verts):
        fi_list = vertex_faces[vi]
        if len(fi_list) < 3:
            continue
        n_at_v = face_normals[fi_list]
        mean_n = np.mean(n_at_v, axis=0)
        mean_n /= np.linalg.norm(mean_n) + 1e-15
        scores[vi] = np.sum((n_at_v - mean_n) ** 2)

    top_n = max(100, int(n_verts * 0.05))
    top_indices = np.argsort(scores)[-top_n:]

    radii = np.full(n_verts, np.inf)
    for vi in top_indices:
        fi_list = vertex_faces[vi]
        if len(fi_list) < 4:
            continue
        # get neighboring vertices (from the faces)
        neigh_verts = set()
        for fi in fi_list:
            for vi2 in faces[fi]:
                if vi2 != vi:
                    neigh_verts.add(vi2)
        if len(neigh_verts) < 4:
            continue

        p_center = verts[vi]
        neigh_arr = verts[list(neigh_verts)]
        # fit sphere: minimize sum(|x-c|^2 - r^2)^2
        # linearize: |x|^2 - 2x·c + |c|^2 = r^2
        A = neigh_arr
        b = np.sum(A ** 2, axis=1)
        # solve A*c = b/2
        try:
            c, _, _, _ = np.linalg.lstsq(A, b / 2, rcond=None)
            r = np.sqrt(np.sum((neigh_arr - c) ** 2, axis=1)).mean()
            if 0 < r < radii[vi]:
                radii[vi] = r
        except Exception:
            continue

    # small radius = sharp point
    valid = radii[radii < np.inf]
    if len(valid) == 0:
        return []
    n_tips = max(1, int(len(valid) * top_k_ratio))
    tip_indices = np.argsort(radii)[:n_tips]
    tips = [verts[vi].copy() for vi in tip_indices if radii[vi] < np.inf]
    return tips


# === METHOD 3: Feature edge + sharp corner ===
def find_tips_method3(shape, h1=0.0001, nlayers=10, growth=1.3, top_k_ratio=0.01, feature_angle=150.0):
    """sharp edge 끝나는 vertex 중에서 curvature 추가로 tip 선별."""
    T = h1 * (growth ** nlayers - 1) / (growth - 1)
    smallest_face_diag = float('inf')
    for face in shape.Faces():
        try:
            vl, _ = face.tessellate(1.0)
            if vl is None or len(vl) == 0:
                continue
            va = np.array([[v.x, v.y, v.z] for v in vl])
            diag = np.linalg.norm(va.max(axis=0) - va.min(axis=0))
            if diag > 1e-15 and diag < smallest_face_diag:
                smallest_face_diag = diag
        except Exception:
            continue
    min_surf_size = min(2.0 * T, smallest_face_diag)
    verts, faces = tessellate(shape, min_surf_size)
    if verts is None:
        return []

    n_verts = verts.shape[0]
    vertex_faces = [[] for _ in range(n_verts)]
    for fi, face in enumerate(faces):
        for vi in face:
            vertex_faces[vi].append(fi)

    face_normals = np.zeros((len(faces), 3))
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-15)
    face_normals = normals / lengths

    feature_angle_rad = np.radians(feature_angle)
    cos_threshold = np.cos(feature_angle_rad)

    # sharp edge detection (edge-hash)
    edge_normals = {}  # edge -> [n1, n2]
    for fi, face in enumerate(faces):
        v0, v1, v2 = face
        edges = [(min(v0, v1), max(v0, v1)), (min(v1, v2), max(v1, v2)), (min(v0, v2), max(v0, v2))]
        for edge in edges:
            if edge not in edge_normals:
                edge_normals[edge] = []
            edge_normals[edge].append(fi)

    sharp_vertices = set()
    for edge, fi_list in edge_normals.items():
        if len(set(fi_list)) < 2:
            continue
        n1 = face_normals[fi_list[0]]
        n2 = face_normals[fi_list[1]]
        dot = np.clip(np.dot(n1, n2), -1.0, 1.0)
        if dot < cos_threshold:
            sharp_vertices.add(edge[0])
            sharp_vertices.add(edge[1])

    # curvature 추가: sharp edge vertex 중 normal variance로 tip 선별
    scores = np.zeros(len(sharp_vertices))
    vi_list = list(sharp_vertices)
    for idx, vi in enumerate(vi_list):
        fi_list = vertex_faces[vi]
        if len(fi_list) < 2:
            continue
        n_at_v = face_normals[fi_list]
        mean_n = np.mean(n_at_v, axis=0)
        mean_n /= np.linalg.norm(mean_n) + 1e-15
        scores[idx] = np.sum((n_at_v - mean_n) ** 2)

    n_tips = max(1, int(len(scores) * top_k_ratio))
    tip_vi = [vi_list[i] for i in np.argsort(scores)[-n_tips:]]
    tips = [verts[vi].copy() for vi in tip_vi]
    return tips


def main():
    import argparse
    parser = argparse.ArgumentParser(description='3가지 tip 검출 방법 비교')
    parser.add_argument('input', help='STEP 파일')
    parser.add_argument('--h1', type=float, default=0.0001)
    parser.add_argument('--nlayers', type=int, default=10)
    parser.add_argument('--growth', type=float, default=1.3)
    parser.add_argument('--top-k', type=float, default=0.01, help='top k ratio')
    parser.add_argument('--feature-angle', type=float, default=150.0, help='sharp edge 판정 임계각 (도, 기본: 150)')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    print(f"STEP 로드: {args.input}")
    shape = load_step(args.input)
    print(f"  Faces: {len(list(shape.Faces()))}, Edges: {len(list(shape.Edges()))}")

    # Method 1: Normal variance
    print("\n[Method 1] Normal variance (curvature) ...", end=" ")
    tips1 = find_tips_method1(shape, args.h1, args.nlayers, args.growth, args.top_k)
    print(f"{len(tips1)}개")
    if args.verbose:
        for i, t in enumerate(tips1[:10]):
            print(f"  tip{i+1}: ({t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f})")

    # Method 2: Sphere fitting
    print("\n[Method 2] Sphere fitting radius ...", end=" ")
    tips2 = find_tips_method2(shape, args.h1, args.nlayers, args.growth, args.top_k)
    print(f"{len(tips2)}개")
    if args.verbose:
        for i, t in enumerate(tips2[:10]):
            print(f"  tip{i+1}: ({t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f})")

    # Method 3: Sharp edge + curvature
    print("\n[Method 3] Sharp edge + curvature ...", end=" ")
    tips3 = find_tips_method3(shape, args.h1, args.nlayers, args.growth, args.top_k, args.feature_angle)
    print(f"{len(tips3)}개")
    if args.verbose:
        for i, t in enumerate(tips3[:10]):
            print(f"  tip{i+1}: ({t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f})")


if __name__ == '__main__':
    main()
