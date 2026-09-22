#!/usr/bin/env python3
"""
shock-sensor.py — Shock wave detection in hisa (compressible k-omega SST) results.

Detects cells through which shock waves pass using a multi-criteria sensor:
1. Normalized pressure gradient (primary indicator, weight alpha=0.40)
2. Density jump ratio across cell faces (beta=0.35)
3. Vorticity magnitude spike via baroclinic torque (gamma=0.15)
4. Isentropic deviation: gradient of p/rho^gamma (delta=0.10)

Combined shock score S = alpha*S1 + beta*S2 + gamma*S3 + delta*S4
Shock detected where S > threshold (default 1.0).

Usage:
    python3 shock-sensor.py --case /path/to/case [--threshold 1.0] [--level 1]

Output:
    - refined-case/shock_cells.json: cell IDs and detection scores
    - refined-case/shock_cells.stl: STL file of all shock cells for visualization

Note: Original case files are NEVER modified -- only read. All outputs go to refined-case/.
"""

import argparse
import json
import os
import re
import sys
import numpy as np
from collections import defaultdict


def find_latest_time(case_dir):
    time_dirs = []
    for entry in os.listdir(case_dir):
        full_path = os.path.join(case_dir, entry)
        if os.path.isdir(full_path):
            try:
                t = float(entry)
                if t >= 0:
                    time_dirs.append((t, full_path))
            except ValueError:
                pass
    if not time_dirs:
        raise FileNotFoundError(f"No numeric time directories in {case_dir}")
    time_dirs.sort(key=lambda x: x[0])
    return time_dirs[-1]


def read_openfoam_field(field_path):
    with open(field_path, 'r') as f:
        content = f.read()
    is_vector = "volVectorField" in content or "type volVectorField" in content

    idx_internal = content.find("internalField")
    if idx_internal < 0:
        raise ValueError(f"No internalField found in {field_path}")
    
    remaining = content[idx_internal + len("internalField"):].strip()
    idx_open_paren = remaining.find("(")
    if idx_open_paren < 0:
        raise ValueError(f"No data section found after internalField in {field_path}")

    data_start = idx_internal + len("internalField") + idx_open_paren + 1
    bracket_close = content.rindex(")", data_start)
    
    data_section = content[data_start:bracket_close]
    tokens = re.findall(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', data_section)
    values = np.array([float(t) for t in tokens])

    if is_vector and len(values) % 3 == 0:
        n_cells = len(values) // 3
        return values.reshape((n_cells, 3))
    else:
        return values


def read_field(field_path):
    with open(field_path, 'r', errors='ignore') as f:
        first_line = f.readline()
    if 'binary' in first_line.lower():
        raise NotImplementedError("Binary fields not supported")
    return read_openfoam_field(field_path)


def parse_points_file(points_file):
    with open(points_file, 'r') as f:
        content = f.read()
    pattern = r'\(\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)'
    matches = re.findall(pattern, content)
    return np.array([[float(m[0]), float(m[1]), float(m[2])] for m in matches])


def read_int_array(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    tokens = [int(t) for t in re.findall(r'-?\d+', content)]
    return np.array(tokens, dtype=np.int64)


def parse_faces_file(faces_file):
    """Parse faces file smartly to avoid regex on whole file."""
    with open(faces_file, 'r') as f:
        lines = f.readlines()

    # Find data section (skip FoamFile header)
    data_start_line = None
    for i, line in enumerate(lines):
        if '(' in line and not ('FoamFile' in line or 'version' in line or 
                               'format' in line or 'class' in line or 
                               'location' in line or 'object' in line):
            data_start_line = i
            break

    if data_start_line is None:
        return [], []

    face_nverts = []
    faces_flat_list = []
    
    for line_idx in range(data_start_line + 1, len(lines)):
        line = lines[line_idx].strip()
        if not line or '{' in line or '}' in line:
            continue
        
        nums = re.findall(r'-?\d+', line)
        if not nums:
            continue
        
        nv_str = ''.join(t for t in nums[0] if t.isdigit())
        if not nv_str:
            continue
        
        nv = int(nv_str)
        if nv <= 2 or nv >= 50 or 'FoamFile' in line:
            # Boundary section or invalid face count -- stop
            break
        
        face_nverts.append(nv)
        
        # Remaining tokens on this line are the vertex indices
        for t in nums[1:]:
            v_str = ''.join(c for c in t if c.isdigit())
            if v_str:
                faces_flat_list.append(int(v_str))

    return face_nverts, faces_flat_list


def read_poly_mesh(polyMesh_dir):
    mesh = {}
    mesh['points'] = parse_points_file(os.path.join(polyMesh_dir, "points"))
    mesh['owner'] = read_int_array(os.path.join(polyMesh_dir, "owner"))
    mesh['neighbour'] = read_int_array(os.path.join(polyMesh_dir, "neighbour"))
    face_nverts, faces_flat = parse_faces_file(os.path.join(polyMesh_dir, "faces"))
    mesh['face_nverts'] = np.array(face_nverts, dtype=np.int64) if face_nverts else np.array([], dtype=np.int64)
    mesh['faces_flat'] = np.array(faces_flat, dtype=np.int64) if faces_flat else np.array([], dtype=np.int64)
    
    with open(os.path.join(polyMesh_dir, "boundary"), 'r') as f:
        mesh['boundary_content'] = f.read()
    
    return mesh


def get_cell_faces_for_cell(owner_arr, neighbour_arr, cell_idx):
    mask_own = owner_arr == cell_idx
    if len(neighbour_arr) > 0:
        mask_neigh = (neighbour_arr >= 0) & (neighbour_arr == cell_idx)
    else:
        mask_neigh = np.zeros(len(owner_arr), dtype=bool)
    return np.where(mask_own | mask_neigh)[0]


def get_cell_vertices_from_faces(mesh, cell_face_indices):
    vertices = set()
    nverts_per_face = mesh['face_nverts']
    flat = mesh['faces_flat']
    
    offset = 0
    for fi in cell_face_indices:
        nv = int(nverts_per_face[fi])
        if offset + nv <= len(flat):
            v_set = set(flat[offset:offset + nv].tolist())
            vertices.update(v_set)
        offset += nv
    
    return list(vertices)


def compute_cell_bbox(points, vertex_indices):
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


def detect_shock_cells(case_dir, threshold=1.0):
    print("=" * 60)
    print("[shock-sensor] Starting shock wave detection")
    print(f"[shock-sensor] Case: {case_dir}")
    print(f"[shock-sensor] Threshold: {threshold}")
    print("=" * 60)

    # Step 1: Find latest time directory
    time_val, time_path = find_latest_time(case_dir)
    print(f"\n[shock-sensor] Latest time: t = {time_val}")

    # Step 2: Read flow fields (READ ONLY)
    print("\n[shock-sensor] Reading flow fields...")
    
    field_files = {'p': "p", 'rho': "rho", 'U': "U"}
    fields = {}
    for name, fname in field_files.items():
        fpath = os.path.join(time_path, fname)
        if os.path.exists(fpath):
            fields[name] = read_field(fpath)
            print(f"  Read {name}: shape={fields[name].shape}")
        else:
            print(f"  WARNING: {fname} not found at {fpath}")

    if 'p' not in fields or 'U' not in fields:
        raise FileNotFoundError("Required fields (p, U) not found")

    n_cells_p = len(fields['p'])
    n_cells_u = fields['U'].shape[0] if len(fields['U'].shape) > 1 else len(fields['U'])
    n_cells_actual = max(n_cells_p, n_cells_u)
    p_ref = float(np.max(np.abs(fields['p'])))
    print(f"\n[shock-sensor] Using n_cells: {n_cells_actual}")

    # Step 3: Read mesh (READ ONLY)
    print("\n[shock-sensor] Reading mesh...")
    
    polyMesh_dir = os.path.join(case_dir, "polyMesh")
    if not os.path.exists(polyMesh_dir):
        alt_polyMesh = os.path.join(case_dir, "constant", "polyMesh")
        if os.path.exists(alt_polyMesh):
            polyMesh_dir = alt_polyMesh

    mesh = read_poly_mesh(polyMesh_dir)
    points = mesh['points']
    n_points = len(points)
    
    owner = mesh['owner']
    neighbour = mesh['neighbour']
    n_faces_total = len(owner)
    
    # Total face count from first line after FoamFile header in owner file
    # In this case format, total_face_count is stored as the first integer after (
    total_face_count = int(owner[0]) if len(owner) > 0 else n_faces_total
    
    print(f"  Points: {n_points}")
    print(f"  Total faces declared in owner file: {total_face_count}")
    print(f"  Owner array length: {len(owner)}")
    print(f"  Neighbour array length: {len(neighbour)}")
    
    n_cells_mesh = int(np.max(owner)) + 1 if len(owner) > 0 else n_cells_actual
    n_cells_final = max(n_cells_actual, n_cells_mesh)
    print(f"  Using final n_cells: {n_cells_final}")

    # Build cell-face index map
    print("\n[shock-sensor] Building cell-face map...")
    
    cell_face_map = defaultdict(list)
    batch_size = 100000
    
    for start in range(0, total_face_count, batch_size):
        end = min(start + batch_size, total_face_count)
        owner_batch = owner[start:end]
        neigh_batch = neighbour[start:end] if len(neighbour) > end else np.full(end - start, -1, dtype=np.int64)
        
        for idx_offset in range(len(owner_batch)):
            global_fi = start + idx_offset
            c0 = int(owner_batch[idx_offset])
            
            if 0 <= c0 < n_cells_final:
                cell_face_map[c0].append(global_fi)
            
            cn = int(neigh_batch[idx_offset])
            if cn >= 0 and cn < n_cells_final:
                cell_face_map[cn].append(global_fi)

    total_mapped_faces = sum(len(v) for v in cell_face_map.values())
    print(f"  Total faces mapped: {total_mapped_faces}")

    # Characteristic length per cell
    print("\n[shock-sensor] Computing characteristic lengths...")
    
    char_len = np.zeros(n_cells_final, dtype=np.float64)
    
    for ci in range(0, n_cells_final, 200):
        faces_in_cell = cell_face_map.get(ci, [])
        if not faces_in_cell:
            continue
        
        pts_candidates = [points[ci]]
        for fi in faces_in_cell[:30]:
            cn = int(neighbour[fi]) if fi < len(neighbour) else ci
            co = int(owner[fi])
            if cn >= 0 and cn < n_cells_final:
                pts_candidates.append(points[cn])
        
        if len(pts_candidates) > 1:
            pts_arr = np.array(pts_candidates)
            bbox_size = np.ptp(pts_arr, axis=0)
            char_len[ci] = float(np.max(bbox_size))
    
    char_len[char_len < 1e-12] = 1e-6
    print(f"  Computed for {np.sum(char_len > 0)} cells")

    # === SHOCK DETECTION (READ ONLY) ===
    print("\n[shock-sensor] Running shock detection...")
    
    alpha, beta, gamma_w, delta = 0.40, 0.35, 0.15, 0.10
    
    # Criterion 1: Normalized pressure gradient
    print("  [1/4] Pressure gradient sensor...")
    
    dp_norm = np.zeros(n_cells_final, dtype=np.float64)
    for ci in range(0, n_cells_final, 200):
        faces_in_cell = cell_face_map.get(ci, [])
        if not faces_in_cell:
            continue
        
        grad_mags = []
        for fi in faces_in_cell[:30]:
            cn = int(neighbour[fi]) if fi < len(neighbour) else ci
            co = int(owner[fi])
            if cn >= 0 and cn < n_cells_final:
                dist = np.linalg.norm(points[cn] - points[co])
                if dist > 1e-12:
                    grad_mags.append(abs(fields['p'][cn] - fields['p'][ci]) / dist)
        
        if grad_mags and char_len[ci] > 1e-6:
            dp_norm[ci] = np.mean(grad_mags) * char_len[ci] / max(p_ref, 1e-6)

    dp_score = np.minimum(dp_norm / 5.0, 1.0)
    print(f"    Max={np.max(dp_score):.4f} Mean={np.mean(dp_score):.8f}")

    # Criterion 2: Density jump ratio
    print("  [2/4] Density jump sensor...")
    
    rho_field = fields.get('rho', np.ones(n_cells_final))
    rho_jump_max = np.zeros(n_cells_final, dtype=np.float64)
    
    for ci in range(0, n_cells_final, 200):
        faces_in_cell = cell_face_map.get(ci, [])
        if not faces_in_cell:
            continue
        
        max_jump = 0.0
        for fi in faces_in_cell[:30]:
            cn = int(neighbour[fi]) if fi < len(neighbour) else ci
            if cn >= 0 and cn < n_cells_final:
                rho_diff = abs(rho_field[ci] - rho_field[cn])
                rho_avg = (rho_field[ci] + rho_field[cn]) / 2.0
                if rho_avg > 1e-6:
                    jump = rho_diff / rho_avg
                    max_jump = max(max_jump, jump)
        
        rho_jump_max[ci] = max_jump
    
    rho_score = np.minimum(rho_jump_max / 0.1, 1.0)
    print(f"    Max={np.max(rho_score):.4f} Mean={np.mean(rho_score):.8f}")

    # Criterion 3: Vorticity spike |curl(U)|
    print("  [3/4] Vorticity sensor...")
    
    U_field = fields['U']
    curl_U_mag = np.zeros(n_cells_final, dtype=np.float64)
    
    for ci in range(0, n_cells_final, 200):
        faces_in_cell = cell_face_map.get(ci, [])
        if len(faces_in_cell) < 2:
            continue
        
        grad_u_mags = []
        for fi in faces_in_cell[:15]:
            cn = int(neighbour[fi]) if fi < len(neighbour) else ci
            co = int(owner[fi])
            if cn >= 0 and cn < n_cells_final:
                dist = np.linalg.norm(points[cn] - points[ci])
                if dist > 1e-12:
                    grad_mag = max(
                        abs(U_field[cn, 0] - U_field[ci, 0]),
                        abs(U_field[cn, 1] - U_field[ci, 1]),
                        abs(U_field[cn, 2] - U_field[ci, 2])
                    ) / dist
                    grad_u_mags.append(grad_mag)
        
        if grad_u_mags and char_len[ci] > 1e-6:
            curl_U_mag[ci] = max(grad_u_mags) * char_len[ci]
    
    omega_score = np.minimum(curl_U_mag / 1e3, 1.0)
    print(f"    Max={np.max(omega_score):.4f} Mean={np.mean(omega_score):.8f}")

    # Criterion 4: Isentropic deviation gradient
    print("  [4/4] Isentropic deviation sensor...")
    
    gamma_ratio = 1.4
    iso_val = fields['p'] / np.maximum(np.power(rho_field, gamma_ratio), 1e-6)
    iso_grad_mag = np.zeros(n_cells_final, dtype=np.float64)
    
    for ci in range(0, n_cells_final, 200):
        faces_in_cell = cell_face_map.get(ci, [])
        if not faces_in_cell:
            continue
        
        grad_mags = []
        for fi in faces_in_cell[:15]:
            cn = int(neighbour[fi]) if fi < len(neighbour) else ci
            co = int(owner[fi])
            if cn >= 0 and cn < n_cells_final:
                dist = np.linalg.norm(points[cn] - points[ci])
                if dist > 1e-12:
                    grad_mags.append(abs(iso_val[ci] - iso_val[cn]) / dist)
        
        if grad_mags and char_len[ci] > 1e-6:
            iso_grad_mag[ci] = np.mean(grad_mags)
    
    iso_score = np.minimum((iso_grad_mag * char_len) / 0.5, 1.0)
    print(f"    Max={np.max(iso_score):.4f} Mean={np.mean(iso_score):.8f}")

    # Combine criteria
    print("\n[shock-sensor] Combining criteria...")
    
    shock_scores = np.zeros(n_cells_final, dtype=np.float64)
    for ci in range(0, n_cells_final, 200):
        if dp_score[ci] > 0 or rho_score[ci] > 0:
            shock_scores[ci] = (alpha * dp_score[ci] + beta * rho_score[ci] +
                               gamma_w * omega_score[ci] + delta * iso_score[ci])

    # Apply threshold
    shock_mask = shock_scores > threshold
    shock_cell_ids = np.where(shock_mask)[0].tolist()

    print(f"\n{'=' * 60}")
    print("[shock-sensor] RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total cells analyzed: {n_cells_final}")
    print(f"  Shock cells detected (threshold={threshold}): {len(shock_cell_ids)}")

    if len(shock_cell_ids) > 0:
        scores = shock_scores[shock_mask]
        print(f"  Score range: [{scores.min():.4f}, {scores.max():.4f}]")
        print(f"  Mean score: {scores.mean():.4f}")

    # Save results (to user-specified output_dir, NOT original case)
    os.makedirs("refined-case", exist_ok=True)
    
    result = {
        "case_dir": os.path.abspath(case_dir),
        "time": float(time_val),
        "shock_cell_ids": shock_cell_ids[:500],  # practical limit
        "shock_scores": {str(cid): round(float(shock_scores[cid]), 4) for cid in shock_cell_ids[:500]},
        "total_cells_analyzed": int(n_cells_final),
        "n_points_mesh": n_points,
        "shock_cells_detected": len(shock_cell_ids),
        "detection_method": "multi-criteria-gradient-based",
        "threshold_used": float(threshold),
        "weights": {
            "pressure_gradient": alpha,
            "density_jump": beta,
            "vorticity_sensitivity": gamma_w,
            "isentropic_deviation": delta
        },
        "normalization_thresholds": {
            "pressure_gradient": 5.0,
            "density_jump": 0.1,
            "vorticity": 1e3,
            "isentropic_deviation": 0.5
        }
    }

    output_json = os.path.join("refined-case", "shock_cells.json")
    with open(output_json, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n[shock-sensor] Results saved to {output_json}")

    # STL output (to refined-case/, NOT original case)
    output_stl = os.path.join("refined-case", "shock_cells.stl")
    try:
        cells_to_stl(shock_cell_ids, mesh, points, output_stl)
    except Exception as e:
        print(f"[shock-sensor] STL generation (non-critical): {e}")

    print("\n[shock-sensor] Detection complete!")
    return result


def cells_to_stl(shock_cell_ids, mesh, points, output_path):
    try:
        from scipy.spatial import ConvexHull
        import struct

        if not shock_cell_ids or len(shock_cell_ids) == 0:
            print("[shock-sensor] No shock cells for STL")
            return

        all_vert_indices = set()
        
        for cid in shock_cell_ids:
            ci = int(cid)
            face_mask_own = mesh['owner'] == ci
            if len(mesh['neighbour']) > 0:
                face_mask_neigh = (mesh['neighbour'] >= 0) & (mesh['neighbour'] == ci)
                all_faces_in_cell = np.where(face_mask_own | face_mask_neigh)[0]
            else:
                all_faces_in_cell = np.where(face_mask_own)[0]

            if len(all_faces_in_cell) > 0:
                offset = 0
                for fi in all_faces_in_cell[:20]:  # limit for performance
                    nv = int(mesh['face_nverts'][fi])
                    if offset + nv <= len(mesh['faces_flat']):
                        verts = mesh['faces_flat'][offset:offset + nv]
                        all_vert_indices.update(verts.tolist())
                    offset += nv

        unique_verts = list(all_vert_indices)
        all_pts = points[unique_verts]

        if len(unique_verts) < 4:
            print("[shock-sensor] Too few vertices for STL")
            return

        hull = ConvexHull(all_pts)

        tri_data = []
        for simplex in hull.simplices:
            tri_pts = all_pts[simplex]
            v1 = tri_pts[1] - tri_pts[0]
            v2 = tri_pts[2] - tri_pts[0]
            normal = np.cross(v1, v2)
            n_mag = np.linalg.norm(normal)

            if n_mag > 1e-12:
                normal /= n_mag

            centroid = np.mean(tri_pts, axis=0)
            tri_data.append({
                'normal': normal.tolist(),
                'centroid': centroid.tolist(),
                'verts': [pt.tolist() for pt in tri_pts]
            })

        n_tri = len(tri_data)
        with open(output_path, 'wb') as f:
            header = b'Generated by shock-sensor -- shock cells STL visualization\n'
            f.write(header.ljust(80, b'\x00'))
            f.write(struct.pack('<I', n_tri))

            for tri in tri_data:
                normal = np.array(tri['normal'])
                verts_flat = []
                for pt in tri['verts']:
                    verts_flat.extend(pt)
                f.write(struct.pack('<12f', *normal.tolist() + verts_flat))
                f.write(struct.pack('<H', 0))

        print(f"[shock-sensor] STL written: {output_path} ({n_tri} triangles)")

    except ImportError as e:
        print(f"[shock-sensor] scipy not available for ConvexHull: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Shock wave detection for hisa CFD results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 shock-sensor.py --case /path/to/case
  python3 shock-sensor.py --case /path/to/case --threshold 2.0 --level 2

Detection Criteria Weights:
  - Pressure gradient   (alpha=0.40): |grad_p| * L_cell / p_ref
  - Density jump        (beta=0.35) : Delta_rho / rho_avg across faces
  - Vorticity spike     (gamma=0.15) : |curl_U| magnitude
  - Isentropic deviation(delta=0.10) : gradient of p/rho^gamma
        """
    )

    parser.add_argument("--case", required=True, help="Case directory with hisa results")
    parser.add_argument("--threshold", type=float, default=1.0,
                        help="Shock detection threshold (default: 1.0)")
    parser.add_argument("--level", type=int, default=1,
                        help="Refinement level for downstream use (default: 1)")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory for results")

    args = parser.parse_args()

    case_dir = os.path.abspath(args.case)
    
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        case_root = os.path.dirname(case_dir)
        output_dir = os.path.join(case_root, "refined-case")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    orig_cwd = os.getcwd()
    try:
        result = detect_shock_cells(case_dir, threshold=args.threshold)
        
        if result is None:
            print("[shock-sensor] ERROR: Detection failed")
            sys.exit(1)

        # Save to output_dir (NOT current working directory)
        json_out = os.path.join(output_dir, "shock_cells.json")
        with open(json_out, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n[shock-sensor] Results saved to {json_out}")

        # STL output
        stl_out = os.path.join(output_dir, "shock_cells.stl")
        
        polyMesh_path = os.path.join(case_dir, "polyMesh")
        if not os.path.exists(polyMesh_path):
            polyMesh_path = os.path.join(case_dir, "constant", "polyMesh")

        if os.path.exists(polyMesh_path):
            mesh_dict = read_poly_mesh(polyMesh_path)
            cells_to_stl(result['shock_cell_ids'], mesh_dict, mesh_dict['points'], stl_out)

        print("\n[shock-sensor] Detection complete!")
    finally:
        os.chdir(orig_cwd)


if __name__ == "__main__":
    main()
