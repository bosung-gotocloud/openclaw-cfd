#!/usr/bin/env python3
"""
refine-mesh.py — Mesh refinement via edge subdivision for shock-captured cells.

Reads shock cell IDs from shock_cells.json, sub-divides each shock cell by (0.5)^level,
reconstructs the polyMesh, and writes it to the refined-case directory.

Handles OpenFOAM v7+ format: no separate cells file; face count per cell is stored in owner/neighbour.

Usage:
    python3 refine-mesh.py \
        --case /path/to/case \
        --refined-case /path/to/refined-case \
        --shock-cells shock_cells.json \
        --level 1

Note: original case files are NEVER modified — only read. All outputs go to refined-case/
"""

import argparse
import json
import os
import sys
import numpy as np
from pathlib import Path


def read_field_with_header(path):
    """Read a numeric array from an OpenFOAM file, skipping FoamFile header."""
    with open(path, 'r') as f:
        lines = f.readlines()

    # Skip until we find the opening '(' or '[' of data
    data_start = None
    for i, line in enumerate(lines):
        if '(' in line or '[' in line:
            # Check if it's not a FoamFile keyword (version, format, class, object)
            stripped = line.strip().lower()
            if stripped.startswith('(') or stripped.startswith('['):
                data_start = i
                break

    if data_start is None:
        raise ValueError(f"No data section found in {path}")

    # Read all remaining content
    data_str = ' '.join(lines[data_start:])
    tokens = []
    for ch in data_str.replace('(', ' ').replace(')', ' ').replace('[', ' ').replace(']', ' '):
        if not ch.isspace() and ch not in '(),[]':
            tokens.append(ch)

    return tokens


def read_poly_mesh(polyMesh_dir):
    """Read polyMesh files from OpenFOAM case (v7+ format).

    Returns dict with: points, faces_flat, face_nverts, owner, neighbour, nCells, boundary
    """
    mesh = {}

    # --- Points ---
    points_file = os.path.join(polyMesh_dir, "points")
    pts_tokens = read_field_with_header(points_file)
    pts_vals = np.array([float(t) for t in pts_tokens], dtype=np.float64)
    mesh['points'] = pts_vals.reshape(-1, 3)
    n_points = len(mesh['points'])
    print(f"  Points: {n_points}")

    # --- Owner & Neighbour (these contain the face count per cell in v7+ format) ---
    # In this case, owner and neighbour files are simple integer arrays.
    # The actual "cells" data (face list per cell) is embedded in faces file.
    # We need to parse: for each cell_i, how many faces it has, then which face indices.

    # Owner: one entry per face (the owner cell index)
    owner_tokens = read_field_with_header(os.path.join(polyMesh_dir, "owner"))
    mesh['owner'] = np.array([int(t) for t in owner_tokens], dtype=np.int64)
    n_faces_mesh = len(mesh['owner'])

    # Neighbour: one entry per face (the neighbour cell index, -1 if boundary)
    neigh_tokens = read_field_with_header(os.path.join(polyMesh_dir, "neighbour"))
    mesh['neighbour'] = np.array([int(t) for t in neigh_tokens], dtype=np.int64)

    # --- Faces: variable-length format ---
    # OpenFOAM v7+ with FoamFile header + boundary info
    # faces file contains: FoamFile header, then ( startFace face1 face2 ... ), repeated
    # But our case doesn't have a separate "faces" section — let's check

    faces_file = os.path.join(polyMesh_dir, "faces")
    with open(faces_file, 'r') as f:
        content = f.read()

    # Determine format: if contains FoamFile + polyBoundaryMesh or has startFace blocks
    has_foamfile_header = "FoamFile" in content and "polyBoundaryMesh" not in content

    # Count how many lines after FoamFile header
    lines = content.split('\n')
    data_lines = []
    skip_until_data = False
    for line in lines:
        if has_foamfile_header and 'FoamFile' in line:
            skip_until_data = True
            continue
        if skip_until_data and ('{' in line or '(' in line):
            # Check if this is a data block start
            pass
        data_lines.append(line)

    # Find all integer tokens after FoamFile section
    faces_raw_str = ' '.join(data_lines)
    import re
    faces_tokens_all = [t for t in re.split(r'[\s(),\[\]{}]+', faces_raw_str) if t.strip().isdigit()]

    face_nverts = []
    faces_flat_list = []
    i = 0
    while i < len(faces_tokens_all):
        try:
            nv = int(faces_tokens_all[i])
            if nv == 0 or nv > 10000:
                # Could be a boundary startFace index — skip it
                # In some cases, the face list starts with a block count then startFace values
                if i + 1 < len(faces_tokens_all):
                    try:
                        sf = int(faces_tokens_all[i + 1])
                        # This looks like a boundary block's startFace
                        # Skip to next numeric value that could be nv
                        i += 2
                        continue
                    except (ValueError, IndexError):
                        break
                else:
                    break
            face_nverts.append(nv)
            for j in range(1, nv + 1):
                if i + j < len(faces_tokens_all):
                    faces_flat_list.append(int(faces_tokens_all[i + j]))
            i += 1 + nv
        except (ValueError, IndexError):
            break

    mesh['face_nverts'] = np.array(face_nverts, dtype=np.int64) if face_nverts else np.array([], dtype=np.int64)
    mesh['faces_flat'] = np.array(faces_flat_list, dtype=np.int64) if faces_flat_list else np.array([], dtype=np.int64)

    # --- Count cells: total faces / avg_faces_per_cell ---
    # In v7+ format without explicit cells file, we count unique owner values + max(neighbour)
    n_cells = int(np.max(mesh['owner'])) + 1
    if len(mesh['neighbour']) > 0:
        n_cells = max(n_cells, int(np.max(np.abs(mesh['neighbour']))) + 1)
    mesh['nCells'] = n_cells

    # --- Boundary ---
    boundary_file = os.path.join(polyMesh_dir, "boundary")
    with open(boundary_file, 'r') as f:
        mesh['boundary'] = f.read()

    print(f"  Faces: {len(mesh['face_nverts'])}")
    print(f"  Owner entries: {n_faces_mesh}")
    print(f"  Neighbour entries: {len(mesh['neighbour'])}")
    print(f"  Estimated cells: {n_cells}")

    return mesh


def get_cell_face_indices(mesh, cell_idx):
    """Get face indices belonging to a given cell."""
    owner = mesh['owner']
    neighbour = mesh['neighbour']

    mask_own = owner == cell_idx
    if len(neighbour) > 0:
        mask_neigh = (neighbour >= 0) & (neighbour == cell_idx)
    else:
        mask_neigh = np.zeros(len(owner), dtype=bool)

    return np.where(mask_own | mask_neigh)[0]


def get_cell_vertices_from_faces(mesh, cell_face_indices):
    """Get unique vertex indices from faces of a cell."""
    vertices = set()
    nverts_per_face = mesh['face_nverts']

    offset = 0
    for fi in cell_face_indices:
        nv = int(nverts_per_face[fi])
        if offset + nv <= len(mesh['faces_flat']):
            verts = mesh['faces_flat'][offset:offset + nv]
            vertices.update(verts.tolist())
        offset += nv

    return list(vertices)


def get_cell_vertices_simple(mesh, cell_idx):
    """Get vertices of a cell by scanning all its faces.
    
    For large meshes this is expensive; use cached version if available.
    """
    faces_in_cell = get_cell_face_indices(mesh, cell_idx)
    return get_cell_vertices_from_faces(mesh, faces_in_cell)


def compute_cell_bbox(points, vertex_indices):
    """Compute bounding box from vertex indices."""
    if not vertex_indices:
        return None
    pts = points[vertex_indices]
    bbox_min = np.min(pts, axis=0)
    bbox_max = np.max(pts, axis=0)
    bbox_size = bbox_max - bbox_min
    char_length = float(np.max(bbox_size)) if np.max(bbox_size) > 1e-12 else 1e-6

    return {
        'min': bbox_min,
        'max': bbox_max,
        'size': bbox_size,
        'char_length': char_length
    }


def refine_mesh(case_dir, refined_case_dir, shock_cell_ids, level=1):
    """Refine mesh at shock locations via edge subdivision.

    Args:
        case_dir: Original case directory (read-only)
        refined_case_dir: Output directory for refined case (write here only)
        shock_cell_ids: List of cell IDs to refine
        level: Refinement level (default 1, subdivision by 0.5^level)

    Returns:
        dict with refinement statistics
    """
    ratio = 0.5 ** level
    n_sub = int(round(1.0 / ratio))  # e.g. level=1 → 2, level=2 → 4

    print(f"[refine-mesh] Refinement level {level}: subdivision ratio = {ratio}")
    print(f"[refine-mesh] Sub-cells per edge: {n_sub}")

    # --- Read original mesh (read-only) ---
    polyMesh_dir = os.path.join(case_dir, "polyMesh")
    if not os.path.exists(polyMesh_dir):
        raise FileNotFoundError(f"polyMesh not found at {polyMesh_dir}")

    print("[refine-mesh] Reading original mesh...")
    mesh = read_poly_mesh(polyMesh_dir)
    points = mesh['points']
    n_cells = mesh['nCells']
    owner = mesh['owner']
    neighbour = mesh['neighbour']
    n_faces = len(owner)

    # Build cell-to-faces mapping (cached for performance)
    print("[refine-mesh] Building cell-face index map...")
    cell_face_map = {}
    for ci in range(n_cells):
        faces_in_cell = get_cell_face_indices(mesh, ci)
        if len(faces_in_cell) > 0:
            cell_face_map[ci] = faces_in_cell

    # Pre-compute bounding box for each cell (cached)
    print("[refine-mesh] Computing cell bounding boxes...")
    cell_bbox = {}
    for ci in range(n_cells):
        if ci not in cell_face_map:
            continue
        verts = get_cell_vertices_from_faces(mesh, cell_face_map[ci])
        if len(verts) >= 3:
            bbox = compute_cell_bbox(points, verts)
            if bbox:
                cell_bbox[ci] = bbox

    # --- Create refined mesh ---
    print("[refine-mesh] Generating refined mesh...")
    os.makedirs(refined_case_dir, exist_ok=True)
    poly_out_dir = os.path.join(refined_case_dir, "polyMesh")
    os.makedirs(poly_out_dir, exist_ok=True)

    # Collect new points (bounding box based subdivision of shock cells)
    new_points_list = []
    new_cells_list = []  # Each entry: (face_count, [vertex_indices])
    point_offset = len(points)

    refined_count = 0

    for i, cid in enumerate(shock_cell_ids):
        ci = int(cid)
        bbox = cell_bbox.get(ci)

        if i % 200 == 0:
            print(f"[refine-mesh] Processing shock cell {i+1}/{len(shock_cell_ids)}...")

        if not bbox:
            continue

        # Generate subdivided points within bounding box
        xmin, ymin, zmin = bbox['min']
        xmax, ymax, zmax = bbox['max']

        xs = np.linspace(xmin, xmax, n_sub + 1)
        ys = np.linspace(ymin, ymax, n_sub + 1)
        zs = np.linspace(zmin, zmax, n_sub + 1)

        xx, yy, zz = np.meshgrid(xs, ys, zs, indexing='ij')
        grid_pts = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

        # Create hexahedral cells from the structured grid
        n_sub_p = n_sub + 1
        new_hex_count = n_sub ** 3

        for ii in range(n_sub):
            for jj in range(n_sub):
                for kk in range(n_sub):
                    idx000 = (ii * n_sub_p + jj) * n_sub_p + kk
                    # Eight corners of hexahedron (global point indices)
                    corners = [
                        idx000,
                        idx000 + 1,
                        idx000 + n_sub_p,
                        idx000 + n_sub_p + 1,
                        idx000 + n_sub_p * n_sub_p,
                        idx000 + n_sub_p * n_sub_p + 1,
                        idx000 + n_sub_p * n_sub_p + n_sub_p,
                        idx000 + n_sub_p * n_sub_p + n_sub_p + 1,
                    ]

                    # Split hex into 5 tetrahedra (standard decomposition)
                    tets = [
                        [corners[0], corners[2], corners[4], corners[7]],
                        [corners[0], corners[3], corners[5], corners[7]],
                        [corners[0], corners[1], corners[5], corners[7]],
                        [corners[0], corners[4], corners[6], corners[7]],
                        [corners[2], corners[6], corners[7], corners[3]],
                    ]

                    for tet in tets:
                        # Map global grid indices to local point indices
                        new_global_idx = [point_offset + c for c in corners]
                        new_cells_list.append((5, new_global_idx))  # face count + vertices

        new_points_list.append(grid_pts)
        refined_count += new_hex_count

    if len(new_points_list) > 0:
        all_points = np.vstack([points] + list(new_points_list))
    else:
        all_points = points.copy()

    total_cells = n_cells + len(new_cells_list)
    print(f"[refine-mesh] New cell count: {total_cells} (added {len(new_cells_list)} cells)")

    # --- Write refined polyMesh ---

    # Points
    pts_str = '\n'.join(f"({all_points[i][0]:.10g} {all_points[i][1]:.10g} {all_points[i][2]:.10g})" for i in range(len(all_points)))
    with open(os.path.join(poly_out_dir, "points"), 'w') as f:
        f.write(f"{len(all_points)}\n(\n{pts_str}\n)\n")

    # Owner file — all new cells are internal (owner = cell index, neighbour = neighbour)
    new_cells_list_flat = []
    for face_count, verts in new_cells_list:
        new_cells_list_flat.append((face_count, verts))

    owner_out = np.zeros(total_cells, dtype=np.int64)
    owner_count = n_cells  # Next cell index after original
    neigh_out = np.full(n_faces, -1, dtype=np.int64)  # Boundary faces get -1
    new_owner_start = n_cells

    face_count = 0
    for fc, verts in new_cells_list_flat:
        tet_verts = verts[:4]  # 4 vertices per tetrahedron
        # 4 faces per tet, each face shared with another cell or boundary
        faces_for_tet = [
            (tet_verts[0], tet_verts[2], tet_verts[3]),  # face 0: outward to neighbour below
            (tet_verts[0], tet_verts[1], tet_verts[3]),  # face 1
            (tet_verts[0], tet_verts[1], tet_verts[2]),  # face 2
            (tet_verts[1], tet_verts[3], tet_verts[2]),  # face 3
        ]

        for f_verts in faces_for_tet:
            owner_out[owner_count] = new_owner_start
            neigh_out[face_count] = -1  # Will need proper internal boundary handling
            face_count += 1
            new_owner_start += 1

    with open(os.path.join(poly_out_dir, "owner"), 'w') as f:
        f.write(f"{total_cells}\n(\n")
        for o in owner_out:
            f.write(f"{o}\n")
        f.write(")\n")

    # Neighbour file
    with open(os.path.join(poly_out_dir, "neighbour"), 'w') as f:
        f.write(f"{total_cells}\n(\n")
        for n in neigh_out:
            f.write(f"{n}\n")
        f.write(")\n")

    # Faces file — each tet has 4 triangular faces
    print("[refine-mesh] Writing faces (this may take a moment)...")
    new_faces_list = []
    for fc, verts in new_cells_list_flat:
        tet_verts = verts[:4]
        faces_for_tet = [
            (tet_verts[0], tet_verts[2], tet_verts[3]),
            (tet_verts[0], tet_verts[1], tet_verts[3]),
            (tet_verts[0], tet_verts[1], tet_verts[2]),
            (tet_verts[1], tet_verts[3], tet_verts[2]),
        ]
        for f_verts in faces_for_tet:
            new_faces_list.append((3, f_verts))

    with open(os.path.join(poly_out_dir, "faces"), 'w') as f:
        f.write(f"{len(new_faces_list)}\n(\n")
        for nv, verts in new_faces_list:
            verts_str = ' '.join(str(v) for v in verts)
            f.write(f"3 ({verts_str})\n")
        f.write(")\n")

    # Cells file (for this format, we store the count per cell)
    with open(os.path.join(poly_out_dir, "cells"), 'w') as f:
        f.write(f"{total_cells}\n(\n")
        offset = 0
        for ci in range(total_cells):
            if ci < n_cells:
                # Original cells — use a simplified representation (approximate)
                faces_in_cell = get_cell_face_indices(mesh, ci) if ci in cell_face_map else []
                f.write(f"{len(faces_in_cell)}\n")
                for fi in faces_in_cell:
                    f.write(f"{fi}\n")
            else:
                # New refined cells
                n_new = offset + 1
                while n_new < len(new_faces_list) and new_faces_list[n_new][0] == 3:
                    f.write("4\n")
                    nv, verts = new_faces_list[n_new]
                    for v in verts:
                        f.write(f"{v}\n")
                    offset += 1
                    n_new += 1
        f.write(")\n")

    # Boundary — copy from original
    if mesh.get('boundary'):
        with open(os.path.join(poly_out_dir, "boundary"), 'w') as f:
            f.write(mesh['boundary'])

    return {
        "original_cells": n_cells,
        "n_points_original": n_points,
        "refined_shock_cells_count": len(shock_cell_ids),
        "new_cells_added": total_cells - n_cells,
        "total_new_cells": total_cells,
        "total_new_points": len(all_points),
        "refinement_ratio": ratio,
        "subdivision_per_edge": n_sub
    }


def copy_case_config(src_case, dst_case):
    """Copy hisa configuration from source case to destination (refined case)."""
    import shutil

    dirs_to_copy = [
        "0",
        "constant/turbulenceProperties",
        "constant/transportProperties",
        "constant/fvOptions",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/decomposeParDict",
        "system/forceCoeffs"
    ]

    print("[refine-mesh] Copying configuration files...")

    for rel_path in dirs_to_copy:
        src = os.path.join(src_case, rel_path)
        dst = os.path.join(dst_case, rel_path)

        if os.path.exists(src):
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            print(f"  Copied: {rel_path}")
        else:
            print(f"  Not found (skipped): {rel_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refine mesh at shock locations")
    parser.add_argument("--case", required=True, help="Original case directory")
    parser.add_argument("--refined-case", required=True, help="Output refined case directory")
    parser.add_argument("--shock-cells", required=True, help="Path to shock_cells.json")
    parser.add_argument("--level", type=int, default=1, help="Refinement level (default: 1)")

    args = parser.parse_args()

    with open(args.shock_cells, 'r') as f:
        shock_data = json.load(f)

    shock_ids = shock_data.get("shock_cell_ids", [])
    if not shock_ids:
        print("[refine-mesh] ERROR: No shock cells found")
        sys.exit(1)

    print(f"[refine-mesh] Refining {len(shock_ids)} shock cells at level {args.level}")

    result = refine_mesh(args.case, args.refined_case, shock_ids, level=args.level)

    if result:
        print("\n[refine-mesh] Refinement complete:")
        for k, v in result.items():
            print(f"  {k}: {v}")

        copy_case_config(args.case, args.refined_case)
        print("[refine-mesh] Configuration copied to refined case")
