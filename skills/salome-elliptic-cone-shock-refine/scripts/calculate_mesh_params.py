#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 1: Calculate mesh parameters with xl-based sizing.
Unified with snappyMesh/salome-tip_refine sizing logic.

Step 1: max_size = max(cube_dx, cube_dy, cube_dz) / 50
Step 2: surf_size = 4 * T
Step 3: min_size = 2 * T
Step 4: refine_size (refine_local_size) = max_size / 4
Step 5: tip_wake_refine_size = surf_size * 2

Boundary layer thickness calculated from h1, layers, growth — displayed only.
"""

import sys
import os
import math
import json
import csv
import glob
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

    # Auto-discover tip points CSV
    tip_csv_auto = os.path.join(base_dir, f"{base_name}_tip_points.csv")
    tip_csv_path = None
    tip_points = []
    if os.path.exists(tip_csv_auto):
        tip_csv_path = tip_csv_auto
        with open(tip_csv_path, 'r') as f:
            reader = csv.reader(f)
            # Detect header: if first row looks like 'x,y,z' header, skip it
            first_row = next(reader, None)
            if first_row is not None:
                if len(first_row) >= 3:
                    # Check if first row is a header (non-numeric)
                    try:
                        float(first_row[0])
                        # First row is data, add it back
                        tip_points.append((float(first_row[0]), float(first_row[1]), float(first_row[2])))
                    except ValueError:
                        # First row is header, skip
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

    # Auto-discover shock CSV (pattern: *shock*.csv)
    shock_pattern = f"*shock*.csv"
    shock_files = glob.glob(os.path.join(base_dir, shock_pattern))
    shock_csv_path = shock_files[0] if shock_files else None
    shock_points = []
    if shock_csv_path:
        with open(shock_csv_path, 'r') as f:
            reader = csv.reader(f)
            # Skip header if present
            first_row = next(reader, None)
            if first_row is not None:
                try:
                    float(first_row[0])
                    # First row is data, add it back
                    shock_points.append((float(first_row[1]), float(first_row[2]), float(first_row[3])))
                except (ValueError, IndexError):
                    # First row is header, skip
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
    except:
        tool_shape = imported_shape
        print("  > Solid creation: Failed (using shell)")

    cube_dx, cube_dy, cube_dz = 10 * xl, 5 * yl, 10 * zl
    # Far-field Ellipsoid semi-axes (matches Stage 2 compute_mesh.py):
    #   half_x  = cube_dx/2  (x-extent = 10xl)
    #   half_yz = max(cube_dy, cube_dz)/2
    #   Position: STEP center at 25% of x-extent (upstream 25% / downstream 75%, flow = +x)
    half_x = cube_dx / 2.0
    half_yz = max(cube_dy, cube_dz) / 2.0
    far_x_extent = 2.0 * half_x
    far_x_offset = +0.25 * far_x_extent   # 25% upstream of STEP center
    c_xmin = cx + far_x_offset - half_x
    c_xmax = cx + far_x_offset + half_x
    c_ymin = cy - half_yz
    c_ymax = cy + half_yz
    c_zmin = cz - half_yz
    c_zmax = cz + half_yz
    print(f"\n[Domain Ellipsoid (bbox only — geometry rebuilt in Stage 2)]")
    print(f"  Semi-axes: x={half_x:.4f}, y=z={half_yz:.4f}")
    print(f"  Size:   {c_xmax - c_xmin:.4f} x {c_ymax - c_ymin:.4f} x {c_zmax - c_zmin:.4f}")
    print(f"  Bounds: X[{c_xmin:.2f}:{c_xmax:.2f}] Y[{c_ymin:.2f}:{c_ymax:.2f}] Z[{c_zmin:.2f}:{c_zmax:.2f}]")
    print(f"  Center: ({cx + far_x_offset:.2f}, {cy:.2f}, {cz:.2f})  [STEP center at 25% x-extent]")

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
    print(f"\n[Refine Box (wake capture)]")
    print(f"  Size:   {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f}")
    print(f"  Center: ({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})")
    print(f"  Translate: ({refine_tx:.2f}, {refine_ty:.2f}, {refine_tz:.2f})")

    # ------ Wake Lines (deferred until surf_size is known)
    _deferred_tip_points = tip_points if tip_points else []
    if _deferred_tip_points:
        print(f"\n[Tip Points]")
        print(f"  Found: {len(_deferred_tip_points)} points (wake lines will be generated after surf_size calc)")
    else:
        print(f"\n[Tip Points]")
        print(f"  Not found -> Wake lines will be skipped")

    # ------ Boolean Operation & Face Classification
    # Far-field ellipsoid via revolution (same pattern as Stage 2 compute_mesh.py):
    # MakeSphere+MakeScaleAlongAxes fails Netgen meshing (curved-surface connectivity),
    # so the solid is built by revolving a half-ellipse face 360° about OX.
    e_origin = geompy.MakeVertex(0, 0, 0)
    e_axis = geompy.MakeVectorDXDYDZ(0, 0, 1)
    ellipse = geompy.MakeEllipse(e_origin, e_axis, half_x, half_yz, geompy.MakeVectorDXDYDZ(1, 0, 0))
    ellipse_face = geompy.MakeFaceWires([ellipse], 1)
    cut_box = geompy.MakeFaceHW(cube_dx, 2.0 * half_yz, 1)
    geompy.TranslateDXDYDZ(cut_box, 0, -half_yz, 0)
    half_ellipse = geompy.MakeCutList(ellipse_face, [cut_box])
    revolution_axis = geompy.MakeVectorDXDYDZ(1, 0, 0)
    ellipsoid = geompy.MakeRevolution(half_ellipse, revolution_axis, 360.0 * math.pi / 180.0)
    ellipsoid = geompy.MakeTranslation(ellipsoid, cx + far_x_offset, cy, cz)
    geompy.addToStudy(ellipsoid, "03_Farfield_Ellipsoid")

    try:
        domain = geompy.MakeCut(ellipsoid, tool_shape)
        op_type = "Cut"
    except:
        domain = geompy.MakePartition([ellipsoid], [tool_shape])
        op_type = "Partition"

    geompy.addToStudy(domain, f"05_{base_name}_domain")

    all_faces = geompy.SubShapeAll(domain, geompy.ShapeType["FACE"])
    tol = 1e-4
    far_faces, model_faces = [], []

    for face in all_faces:
        fb = geompy.BoundingBox(face)
        is_far = any(abs(fb[i] - [c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax][i]) < tol for i in range(6))
        if is_far: far_faces.append(face)
        else: model_faces.append(face)

    group_far = geompy.CreateGroup(domain, geompy.ShapeType["FACE"])
    geompy.UnionList(group_far, far_faces)
    geompy.addToStudyInFather(domain, group_far, "far")

    group_model = geompy.CreateGroup(domain, geompy.ShapeType["FACE"])
    geompy.UnionList(group_model, model_faces)
    geompy.addToStudyInFather(domain, group_model, f"{base_name}_surface")

    salome.myStudy.SaveAs(geom_hdf, False, False)
    print(f"  > Boolean Operation: {op_type} Completed")
    print(f"  > Geometry Saved: {os.path.basename(geom_hdf)}")

    # === Boundary layer defaults ===
    h1 = 0.0001       # firstCellHeight (m)
    layers = 10       # number of layers
    growth = 1.3      # expansion ratio
    fineness = "Custom"  # Custom mesh quality

    # BL thickness: T = h1 * (growth^layers - 1) / (growth - 1)
    T = h1 * (math.pow(growth, layers) - 1) / (growth - 1)

    # === BL-based sizing (unified with snappyMesh / salome-tip_refine-snappy) ===
    # Step 1: max_size = max(cube_dx, cube_dy, cube_dz) / 50.0
    max_size = max(cube_dx, cube_dy, cube_dz) / 50.0

    # Step 2: surf_size = 4 * T
    surf_size = 4.0 * T

    # Step 3: min_size = 2 * T
    min_size = 2.0 * T

    # Step 4: refine_size (refine_local_size) = max_size / 4
    refine_local_size = max_size / 4.0

    # Step 5: tip_wake_refine_size = surf_size * 2 (set below after tip CSV check)
    tip_wake_refine_size = None

    # ------ User Input Section
    print(f"\n[Geometry Summary]")
    print(f"  xl = {xl:.6f} m")
    print(f"  Domain: 10xl x 5yl x 10zl = {cube_dx:.4f} x {cube_dy:.4f} x {cube_dz:.4f} m")

    print(f"\n[Mesh Parameters - User Input]")
    user_headers = ["Parameter", "Value", "Description"]
    user_rows = [
        ["h1", f"{h1:.6f} m", "First cell height (BL)"],
        ["layers", layers, "Boundary layer count (BL)"],
        ["growth", f"{growth:.4f}", "BL growth rate"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"]
    ]
    print(format_table(user_headers, user_rows))

    # ------ Display BL thickness (calculation only, not used for sizing)
    print(f"\n[Boundary Layer Thickness]")
    bl_headers = ["Parameter", "Value", "Formula"]
    bl_rows = [
        ["h1", f"{h1:.6f} m", "First layer height"],
        ["layers", layers, "Number of layers"],
        ["growth", f"{growth:.4f}", "Growth rate"],
        ["T (total thickness)", f"{T:.6f} m", "h1*(growth^layers-1)/(growth-1)"],
    ]
    print(format_table(bl_headers, bl_rows))

    # ------ Derived Parameters Section
    print(f"\n[Mesh Parameters - Derived]")
    derived_headers = ["Parameter", "Value", "Formula"]
    derived_rows = [
        ["max_size", f"{max_size:.6f} m", "max(cube_dx,cube_dy,cube_dz)/50 (far-field coarsest)"],
        ["surf_size", f"{surf_size:.6f} m", "4 * T (surface cell size)"],
        ["min_size", f"{min_size:.6f} m", "2 * T (BL-based)"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "max_size / 4"],
        ["refine_dx", f"{refine_dx:.4f} m", "= 0.5 x cube_dx"],
        ["refine_dy", f"{refine_dy:.4f} m", "= 2 x STEP yl"],
        ["refine_dz", f"{refine_dz:.4f} m", "= 2 x STEP zl"],
        ["refine_cx,y,z", f"{refine_cx:.2f},{refine_cy:.2f},{refine_cz:.2f}", "= far box center"],
        ["refine_tx,y,z", f"{refine_tx:.2f},{refine_ty:.2f},{refine_tz:.2f}", "= center - size/2 (min corner)"],
    ]
    print(format_table(derived_headers, derived_rows))

    print(f"\n  Boundary Layer Groups:")
    print(f"    - far:           {len(far_faces)} faces (far-field)")
    print(f"    - {base_name}_surface: {len(model_faces)} faces (model surface)")

    print(f"\n  Mesh Fitness:")
    aspect_ratio = xl / min_size
    print(f"    - Approx cell aspect ratio: {aspect_ratio:.0f}:1")
    if aspect_ratio > 1000:
        fitness = "LOW"
    elif aspect_ratio > 500:
        fitness = "MEDIUM"
    else:
        fitness = "HIGH"
    print(f"    - Fitness: {fitness}")

    # ------ Wake Cones (replaces tip wake lines) ------
    # User-editable parameters (JSON): wake_cone.aoa_degrees, wake_cone.aoa_max
    wake_cone = {
        "aoa_degrees": [-20.0, 20.0],   # AoA sweep, user-editable in JSON
        "aoa_max": 45.0,               # clamp upper bound
    }
    wake_lines = []
    tip_wake_refine_size = None
    wake_cone_r1 = None
    wake_cone_L = None
    if _deferred_tip_points:
        tip_wake_refine_size = surf_size * 2  # r1 = surf_size * 2
        rb_xmax = refine_cx + refine_dx / 2
        # max_AoA = abs(max of |AoA| list) — single symmetric cone covering the full sweep
        aoa_list = wake_cone.get("aoa_degrees")
        if isinstance(aoa_list, list) and aoa_list:
            max_aoa = abs(max(abs(a) for a in aoa_list))
        else:
            max_aoa = abs(float(wake_cone.get("aoa_degrees", 20.0)))
        max_aoa = min(max_aoa, float(wake_cone.get("aoa_max", 45.0)))

        # L = cone length (tip → downstream boundary)
        # Use the first tip point to estimate L (all tips are at similar x)
        tx0 = _deferred_tip_points[0][0]
        L = max(rb_xmax - tx0, 0.1)
        r1 = tip_wake_refine_size

        print(f"\n[Wake Cones (replaces wake lines)]")
        print(f"  AoA sweep: {aoa_list if isinstance(aoa_list, list) else f'+- {max_aoa:.1f}°'} (max clamp {wake_cone.get('aoa_max', 45.0):.0f}°)")
        print(f"  r1 (tip):  {r1:.6f} m (= surf_size × 2)")
        print(f"  r2 (far):  computed in compute_mesh.py as L × tan(max_aoa × 1.25)")
        print(f"  L (length):    {L:.4f} m (tip → downstream boundary)")
        for i, (tx, ty, tz) in enumerate(_deferred_tip_points):
            wake_line = (tx, ty, tz, rb_xmax, ty, tz)
            wake_lines.append(wake_line)
            print(f"    Cone {i+1}: tip=({tx:.4f}, {ty:.4f}, {tz:.4f}) → end=({rb_xmax:.4f}, {ty:.4f}, {tz:.4f})")

        # Save computed values to the wake_cone dict for JSON output
        wake_cone["r1"] = r1
        wake_cone["L"] = L


    # ------ Summary Table
    print(f"\n" + "="*60)
    print("MESH VARIABLES SUMMARY")
    print("="*60)

    summary_headers = ["Parameter", "Value", "Description"]
    summary_rows = [
        ["xl", f"{xl:.4f} m", "Model length"],
        ["yl", f"{yl:.4f} m", "Model width (half-span)"],
        ["zl", f"{zl:.4f} m", "Model height"],
        ["h1", f"{h1:.6f} m", "First cell height (BL)"],
        ["layers", layers, "Boundary layer count (BL)"],
        ["growth", f"{growth:.4f}", "BL growth rate"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"],
        ["T", f"{T:.6f} m", "BL total thickness (calc, display only)"],
        ["max_size", f"{max_size:.6f} m", "max(cube_dx,cube_dy,cube_dz)/50 (far-field coarsest)"],
        ["surf_size", f"{surf_size:.6f} m", "4 * T (surface cell size)"],
        ["min_size", f"{min_size:.6f} m", "2 * T (BL-based)"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "max_size / 4 (refine box)"],
        ["refine_dx", f"{refine_dx:.4f} m", "Wake capture X size"],
        ["refine_dy", f"{refine_dy:.4f} m", "Wake capture Y size"],
        ["refine_dz", f"{refine_dz:.4f} m", "Wake capture Z size"],
        ["tip_wake_refine_size", f"{tip_wake_refine_size:.6f} m" if tip_wake_refine_size else "N/A", "Step 5: surf_size * 2"],
        ["shock_refine_size", f"{surf_size * 2:.6f} m" if shock_points else "N/A", "surf_size × 2"],
        ["shock_points_count", len(shock_points), "Shock points count (from CSV)"],
        ["cube_dx", f"{cube_dx:.4f} m", "Domain length (10xl)"],
        ["cube_dy", f"{cube_dy:.4f} m", "Domain width (5yl)"],
        ["cube_dz", f"{cube_dz:.4f} m", "Domain height (10zl)"],
        ["far_faces", len(far_faces), "Far-field faces"],
        ["model_faces", len(model_faces), "Model surface faces"],
        ["tip_points_count", len(tip_points), "Tip points count (from CSV)"],
    ]
    print(format_table(summary_headers, summary_rows))

    # ------ Store to JSON
    args = {
        "step_path": step_path,
        "base_dir": base_dir,
        "base_name": base_name,
        "geom_hdf": geom_hdf,
        "xl": xl,
        "yl": yl,
        "zl": zl,
        "h1": h1,
        "layers": layers,
        "growth": growth,
        "fineness": fineness,
        "T": T,
        "min_size": min_size,
        "surf_size": surf_size,
        "max_size": max_size,
        "refine_local_size": refine_local_size,
        "far_faces_count": len(far_faces),
        "model_faces_count": len(model_faces),
        "cube_dx": cube_dx,
        "cube_dy": cube_dy,
        "cube_dz": cube_dz,
        "refine_dx": refine_dx,
        "refine_dy": refine_dy,
        "refine_dz": refine_dz,
        "refine_cx": refine_cx,
        "refine_cy": refine_cy,
        "refine_cz": refine_cz,
        "refine_tx": refine_tx,
        "refine_ty": refine_ty,
        "refine_tz": refine_tz,
        "tip_csv_path": tip_csv_path,
        "tip_points_count": len(tip_points),
        "tip_wake_lines": [[x1, y1, z1, x2, y2, z2] for (x1, y1, z1, x2, y2, z2) in wake_lines],
        "tip_wake_refine_size": tip_wake_refine_size,
        "wake_cone": {
            "aoa_degrees": wake_cone["aoa_degrees"],
            "aoa_max": wake_cone["aoa_max"],
            "r1": wake_cone.get("r1"),
            "L": wake_cone.get("L"),
            "refine_size": tip_wake_refine_size  # = r1, volume local size
        },
        "shock_csv_path": shock_csv_path,
        "shock_points_count": len(shock_points),
        "shock_refine_size": surf_size * 2,  # shock_refine_size = surf_size × 2
        "use_refine_ellipsoid": False,  # Refine ellipsoid generation: default OFF
    }

    with open(args_file, 'w') as f:
        json.dump(args, f, indent=2)

    print(f"\n" + "="*60)
    print("PARAMETERS CALCULATED")
    print("="*60)
    print(f"\n  Args saved to: {os.path.basename(args_file)}")
    print(f"\n  Files created:")
    print(f"    - {os.path.basename(geom_hdf)} (geometry)")
    print(f"    - {os.path.basename(args_file)} (mesh parameters)")
    print(f"\n  Next: Run compute_mesh.py to generate mesh")
    print("="*60)

if __name__ == "__main__":
    run_calculate()
