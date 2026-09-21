#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 1: Calculate mesh parameters with xl-based sizing + shock CSV auto-discovery.
Unified with snappyMesh/salome-tip_refine/snappy-sizing logic.

Sizing logic:
  Step 1: max_size       = max(cube_dx, cube_dy, cube_dz) / 50   (background mesh)
  Step 2: surf_size      = xl * 0.01         (surface cell size)
  Step 3: min_size       = surf_size / 2     (minimum cell size)
  Step 4: refine_size    = max_size / 4      (refine box local size)
  Step 5: tip_wake_refine_size = surf_size * 2
  Step 6: shock_refine_size = surf_size * 2   (shock point local size)

Boundary layer thickness calculated from h1, layers, growth — displayed only.
Auto-discovers {basename}-shock-wave*.csv for shock point refinement.
"""

import sys
import os
import math
import json
import csv
import glob as glob_mod
import salome
import GEOM
from salome.geom import geomBuilder

# Redirect stdout to log file
_script_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
_log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), f"{_script_name}.log")
sys.stdout = open(_log_file, 'w')

# Initialize
salome.salome_init()
geompy = geomBuilder.New()

def format_table(headers, rows):
    """Format data as ASCII table"""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    lines = []
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(f" {h:^{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
    lines.append(separator)
    lines.append(header_line)
    lines.append(separator)
    for row in rows:
        row_line = "|" + "|".join(f" {str(cell):<{col_widths[i]}} " for i, cell in enumerate(row)) + "|"
        lines.append(row_line)
    lines.append(separator)
    return "\n".join(lines)

def run_calculate():
    # ------ Parse Arguments
    step_path = None
    for arg in sys.argv:
        if arg.lower().endswith(('.stp', '.step')):
            if ':' in arg:
                directory, filename = arg.split(':', 1)
                step_path = os.path.join(directory, filename)
            else:
                step_path = os.path.abspath(arg)
            break

    if not step_path or not os.path.exists(step_path):
        print("ERROR: STEP file not found.")
        return

    base_dir = os.path.dirname(step_path)
    base_name = os.path.splitext(os.path.basename(step_path))[0]

    # ===== Auto-discover tip points CSV =====
    tip_csv_auto = os.path.join(base_dir, f"{base_name}_tip_points.csv")
    tip_csv_path = None
    tip_points = []
    if os.path.exists(tip_csv_auto):
        tip_csv_path = tip_csv_auto
        with open(tip_csv_path, 'r') as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
            if first_row is not None:
                try:
                    float(first_row[0])
                    tip_points.append((float(first_row[0]), float(first_row[1]), float(first_row[2])))
                except ValueError:
                    pass
                for row in reader:
                    if len(row) >= 3:
                        try:
                            x, y, z = float(row[0]), float(row[1]), float(row[2])
                            tip_points.append((x, y, z))
                        except ValueError:
                            pass
        print(f"\n[Tip Points CSV]")
        print(f"  Found: {os.path.basename(tip_csv_path)}")
        print(f"  Count: {len(tip_points)} points")
    else:
        print(f"\n[Tip Points CSV]")
        print(f"  Not found: {base_name}_tip_points.csv")
        print(f"  -> Skipping tip wake refinement (will use refine box only)")

    # ===== Auto-discover shock CSV =====
    shock_pattern = f"{base_name}-shock-wave*.csv"
    shock_files = glob_mod.glob(os.path.join(base_dir, shock_pattern))
    shock_csv_path = shock_files[0] if shock_files else None
    shock_points = []
    if shock_csv_path:
        with open(shock_csv_path, 'r') as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
            if first_row is not None:
                try:
                    float(first_row[0])
                    shock_points.append((float(first_row[1]), float(first_row[2]), float(first_row[3])))
                except (ValueError, IndexError):
                    pass
            for row in reader:
                if len(row) >= 4:
                    try:
                        x, y, z = float(row[1]), float(row[2]), float(row[3])
                        shock_points.append((x, y, z))
                    except ValueError:
                        pass
        print(f"\n[Shock Points CSV]")
        print(f"  Found: {os.path.basename(shock_csv_path)}")
        print(f"  Count: {len(shock_points)} points")
    else:
        print(f"\n[Shock Points CSV]")
        print(f"  Not found (pattern: {shock_pattern})")
        print(f"  -> Skipping shock refinement")

    geom_hdf = os.path.join(base_dir, f"{base_name}_geom.hdf")
    args_file = os.path.join(base_dir, f"{base_name}_mesh_args.json")

    # ------ Geometry Stage
    print("\n" + "="*60)
    print(f"STAGE 1: GEOMETRY PROCESSING - {base_name}")
    print("="*60)

    imported_shape = geompy.ImportSTEP(step_path)
    geompy.addToStudy(imported_shape, "01_Imported_STEP")

    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(imported_shape)
    xl, yl, zl = x_max - x_min, y_max - y_min, z_max - z_min
    cx, cy, cz = (x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2

    print(f"[Object Dimensions]")
    print(f"  X-Size: {xl:.4f} (min: {x_min:.4f}, max: {x_max:.4f})")
    print(f"  Y-Size: {yl:.4f} (min: {y_min:.4f}, max: {y_max:.4f})")
    print(f"  Z-Size: {zl:.4f} (min: {z_min:.4f}, max: {z_max:.4f})")
    print(f"  Center: ({cx:.4f}, {cy:.4f}, {cz:.4f})")

    try:
        tool_shape = geompy.MakeSolid([imported_shape])
        geompy.addToStudy(tool_shape, "02_Tool_Solid")
        print("  > Solid creation: Success")
    except Exception:
        tool_shape = imported_shape
        print("  > Solid creation: Failed (using shell)")

    cube_dx, cube_dy, cube_dz = 10 * xl, 5 * yl, 10 * zl
    cube = geompy.MakeBoxDXDYDZ(cube_dx, cube_dy, cube_dz)
    geompy.addToStudy(cube, "03_Raw_Cube")

    tx, ty, tz = cx - 2.5 * xl, cy - 2.5 * yl, cz - 5.0 * zl
    moved_cube = geompy.MakeTranslation(cube, tx, ty, tz)
    geompy.addToStudy(moved_cube, "04_Farfield_Box")

    c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax = geompy.BoundingBox(moved_cube)
    far_box_center = ((c_xmin + c_xmax) / 2, (c_ymin + c_ymax) / 2, (c_zmin + c_zmax) / 2)
    print(f"\n[Domain Box (Cube)]")
    print(f"  Size:   {cube_dx:.4f} x {cube_dy:.4f} x {cube_dz:.4f}")
    print(f"  Bounds: X[{c_xmin:.2f}:{c_xmax:.2f}] Y[{c_ymin:.2f}:{c_ymax:.2f}] Z[{c_zmin:.2f}:{c_zmax:.2f}]")

    # Refine Box
    refine_dx = 5 * xl
    refine_dy = 2 * yl
    refine_dz = 2 * zl
    refine_tx = cx - 1.25 * xl
    refine_ty = cy - yl
    refine_tz = cz - zl
    refine_cx = refine_tx + refine_dx / 2
    refine_cy = refine_ty + refine_dy / 2
    refine_cz = refine_tz + refine_dz / 2

    refined_refine_box = geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)
    geompy.addToStudy(refined_refine_box, "05_Refine_Box_Raw")

    moved_refined_box = geompy.MakeTranslation(refined_refine_box, refine_tx, refine_ty, refine_tz)
    geompy.addToStudy(moved_refined_box, "06_Refine_Box_Moved")

    print(f"\n[Refine Box (wake capture)]")
    print(f"  Size:   {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f}")
    print(f"  Center: ({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})")
    print(f"  Translate: ({refine_tx:.2f}, {refine_ty:.2f}, {refine_tz:.2f})")

    # ===== Boolean Operations =====
    print("\n[Boolean Operations]")
    cut_result = geompy.MakeCut(moved_cube, tool_shape)
    geompy.addToStudy(cut_result, "07_Cut_Result")
    partition_result = geompy.MakePartition([cut_result], [tool_shape], [], [], 0)
    geompy.addToStudy(partition_result, "08_Partition_Result")

    # Extract model faces (faces of the tool shape on the cut part)
    sub_shapes = geompy.getSubShapes(partition_result, 1, 2)
    model_faces_list = [s for s in sub_shapes if geompy.getType(s) == 'Face']
    print(f"  Model faces: {len(model_faces_list)}")

    # Extract far-field faces (remaining from cut cube)
    far_face_ids = geompy.getSubShapeIds(moved_cube, "Face")
    model_face_ids = set(geompy.getSubShapeIds(s, "Face") for s in model_faces_list)
    all_cut_ids = geompy.getSubShapeIds(cut_result, "Face")
    far_face_ids_diff = [fid for fid in all_cut_ids if fid not in model_face_ids]

    # ===== Tip Wake Lines (deferred until surf_size known) =====
    _deferred_tip_points = tip_points if tip_points else []
    wake_line_objs = []
    wake_lines_list = []
    tip_wake_refine_size = 0
    if _deferred_tip_points:
        print(f"\n[Tip Points]")
        print(f"  Found: {len(_deferred_tip_points)} points (wake lines will be generated after surf_size calc)")

    # ===== Shock Points (deferred until surf_size known) =====
    _deferred_shock_points = shock_points if shock_points else []
    shock_vertex_objs = []
    shock_refine_size = 0
    if _deferred_shock_points:
        print(f"\n[Shock Points]")
        print(f"  Found: {len(_deferred_shock_points)} points (will generate vertices after surf_size calc)")

    # ===== Mesh Size Calculation =====
    # Step 1: max_size = max(cube_dx, cube_dy, cube_dz) / 50.0
    max_size = max(cube_dx, cube_dy, cube_dz) / 50.0
    surf_size = 4.0 * T
    min_size = 2.0 * T
    refine_local_size = max_size / 4.0
    tip_wake_refine_size = surf_size * 2.0
    shock_refine_size = surf_size * 2.0

    # ===== Boundary Layer Params =====
    h1, layers, growth = 0.0001, 10, 1.3
    T = h1 * (math.pow(growth, layers) - 1) / (growth - 1)

    far_faces_count = len(far_face_ids_diff) if far_face_ids_diff else 0
    model_faces_count = len(model_faces_list)

    # ===== min_size auto-correction =====
    face_diag_min = None
    for face in geompy.SubShapeAllSorted(imported_shape, geompy.ShapeType['FACE']):
        bnd = geompy.BoundingBox(face)
        dx = bnd[1] - bnd[0]
        dy = bnd[2] - bnd[1]
        dz = bnd[3] - bnd[4]
        diag = math.sqrt(dx*dx + dy*dy + dz*dz)
        if face_diag_min is None or diag < face_diag_min:
            face_diag_min = diag

    corrected = False
    if face_diag_min and min_size > face_diag_min:
        print(f"\n[min_size auto-correction]")
        print(f"  Original min_size: {min_size:.6f}")
        print(f"  Smallest face diag: {face_diag_min:.6f}")
        print(f"  -> Corrected to: {face_diag_min:.6f}")
        min_size = face_diag_min
        corrected = True

    # ===== Generate Wake Lines (if tips found) =====
    if _deferred_tip_points:
        print(f"\n[Wake Line Generation]")
        for i, tp in enumerate(_deferred_tip_points):
            x1, y1, z1 = tp
            x2 = refine_cx + refine_dx / 2 + xl * 0.5
            pt1 = geompy.MakeVertex(x1, y1, z1)
            pt2 = geompy.MakeVertex(x2, y1, z1)
            wake_line = geompy.MakeLine(pt1, pt2)
            geompy.addToStudy(wake_line, f"{i+1}_Wake_Line")
            wake_line_objs.append(wake_line)
            wake_lines_list.append([x1, y1, z1, x2, y1, z1])
            print(f"  Tip {i+1}: ({tp[0]:.4f}, {tp[1]:.4f}, {tp[2]:.4f}) -> X={x2:.4f}")

    # ===== Generate Shock Vertices (if shock CSV found) =====
    if _deferred_shock_points:
        print(f"\n[Shock Vertex Generation]")
        for i, sp in enumerate(_deferred_shock_points):
            x, y, z = sp
            sh_vtx = geompy.MakeVertex(x, y, z)
            geompy.addToStudy(sh_vtx, f"{base_name}_shock_vtx_{i}")
            shock_vertex_objs.append(sh_vtx)
        print(f"  Created {len(shock_vertex_objs)} shock vertices (local size = {shock_refine_size:.6f}m)")

    # ===== Save JSON =====
    args = {
        "step_path": os.path.abspath(step_path),
        "base_dir": base_dir,
        "base_name": base_name,
        "geom_hdf": geom_hdf,
        "xl": xl, "yl": yl, "zl": zl,
        "h1": h1, "layers": layers, "growth": growth,
        "fineness": 2,
        "T": round(T, 6),
        "min_size": min_size,
        "surf_size": surf_size,
        "max_size": max_size,
        "far_faces_count": far_faces_count,
        "model_faces_count": model_faces_count,
        "cube_dx": cube_dx, "cube_dy": cube_dy, "cube_dz": cube_dz,
        "refine_dx": refine_dx, "refine_dy": refine_dy, "refine_dz": refine_dz,
        "refine_local_size": refine_local_size,
        "refine_cx": refine_cx, "refine_cy": refine_cy, "refine_cz": refine_cz,
        "refine_tx": refine_tx, "refine_ty": refine_ty, "refine_tz": refine_tz,
    }

    if tip_csv_path:
        args["tip_csv_path"] = tip_csv_path
        args["tip_points_count"] = len(tip_points)
        args["tip_wake_lines"] = wake_lines_list
        args["tip_wake_refine_size"] = tip_wake_refine_size

    if shock_csv_path:
        args["shock_csv_path"] = shock_csv_path
        args["shock_points_count"] = len(shock_points)
        args["shock_refine_size"] = shock_refine_size

    with open(args_file, 'w') as f:
        json.dump(args, f, indent=2)

    # Save geometry study
    import salome_notebook
    salome_notebook.notebook.ExportStudy(geom_hdf, 0)

    # ===== Print Parameters Table =====
    rows = [
        ["xl", f"{xl:.4f}"],
        ["yl", f"{yl:.4f}"],
        ["zl", f"{zl:.4f}"],
        ["max_size", f"{max_size:.6f} (max(cube)/50)"],
        ["surf_size", f"{surf_size:.6f} (xl × 0.01)"],
        ["min_size", f"{min_size:.6f}" + (" ← corrected" if corrected else " (uncorrected)")],
        ["refine_local_size", f"{refine_local_size:.6f} (max_size / 4)"],
        ["tip_wake_refine_size", f"{tip_wake_refine_size:.6f} (surf_size × 2)"] if tip_csv_path else ["tip_wake_refine_size", "N/A (no tip CSV)"],
    ]

    if shock_csv_path:
        rows.append(["shock_refine_size", f"{shock_refine_size:.6f} (surf_size × 2)"])
    else:
        rows.append(["shock_refine_size", "N/A (no shock CSV)"])

    rows.extend([
        ["BL h1", f"{h1:.6f}"],
        ["BL growth", f"{growth}"],
        ["BL layers", str(layers)],
        ["BL T (thickness)", f"{T:.6f}"],
        ["fineness", str(2)],
    ])

    print("\n" + format_table(["Parameter", "Value"], rows))
    print(f"\n[Outputs]")
    print(f"  geom_hdf: {geom_hdf}")
    print(f"  mesh_args.json: {args_file}")
    print("  Stage 1 complete.")

run_calculate()
