#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 1: Calculate mesh parameters with default h1=0.0001
Shows all values in table format and stores args to file for compute_mesh.py
Adds refineBox for wake capture volumetric refinement in SALOME.
"""

import sys
import os
import math
import json
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
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Build table
    lines = []
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    # Header
    header_line = "|" + "|".join(f" {h:^{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
    lines.append(separator)
    lines.append(header_line)
    lines.append(separator)
    
    # Rows
    for row in rows:
        row_line = "|" + "|".join(f" {str(cell):<{col_widths[i]}} " for i, cell in enumerate(row)) + "|"
        lines.append(row_line)
    
    lines.append(separator)
    return "\n".join(lines)

def run_calculate():
    # -------------------------------------------------
    # 1. Parse Arguments
    # -------------------------------------------------
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
    
    geom_hdf = os.path.join(base_dir, f"{base_name}_geom.hdf")
    args_file = os.path.join(base_dir, f"{base_name}_mesh_args.json")

    # -------------------------------------------------
    # 2. Geometry Stage
    # -------------------------------------------------
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
    
    # Refine Box: volumetric refinement around STL object for wake capture
    # Size: 5*xl x 2*STEP_yl x 2*STEP_zl (half of farBox in X)
    # Translate: (cx - 1.25*xl), (cy - yl), (cz - zl) relative to STEP center
    refine_dx = 5 * xl
    refine_dy = 2 * yl
    refine_dz = 2 * zl
    refine_tx = cx - 1.25 * xl  # translate amount relative to origin
    refine_ty = cy - yl
    refine_tz = cz - zl
    # center after translate: tx + size/2
    refine_cx = refine_tx + refine_dx / 2
    refine_cy = refine_ty + refine_dy / 2
    refine_cz = refine_tz + refine_dz / 2
    print(f"\n[Refine Box (wake capture)]")
    print(f"  Size:   {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f}")
    print(f"  Center: ({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})")
    print(f"  Translate: ({refine_tx:.2f}, {refine_ty:.2f}, {refine_tz:.2f})")

    try:
        domain = geompy.MakeCut(moved_cube, tool_shape)
        op_type = "Cut"
    except:
        domain = geompy.MakePartition([moved_cube], [tool_shape])
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

    # -------------------------------------------------
    # 3. Mesh Parameter Calculation (Preview)
    # -------------------------------------------------
    print("\n" + "="*60)
    print("STAGE 2: MESH PARAMETERS (h1 = 0.0001)")
    print("="*60)

    # DEFAULT VALUES
    h1 = 0.0001
    layers = 10
    growth = 1.3
    fineness = 3

    T = h1 * (math.pow(growth, layers) - 1) / (growth - 1)
    base_minthickness = T * 0.1
    
    # Determine min_size and surf_size (check JSON for user overrides)
    min_size = T
    surf_size = 10 * T
    
    if os.path.exists(args_file):
        with open(args_file, 'r') as f:
            existing_args = json.load(f)
            h1 = existing_args.get('h1', h1)
            layers = existing_args.get('layers', layers)
            growth = existing_args.get('growth', growth)
            fineness = existing_args.get('fineness', fineness)
            min_size = existing_args.get('min_size', min_size)
            surf_size = existing_args.get('surf_size', surf_size)
    
    # Recompute T with user overrides
    T = h1 * (math.pow(growth, layers) - 1) / (growth - 1)
    base_minthickness = T * 0.1
    
    # refine_local_size: absolute value, default = surf_size x 2
    refine_local_size = surf_size * 2
    if os.path.exists(args_file):
        with open(args_file, 'r') as f:
            existing_args = json.load(f)
            refine_local_size = existing_args.get('refine_local_size', refine_local_size)
        
    max_size = (10 * xl) / 50.0

    print(f"\n[Geometry Summary]")
    print(f"  xl = {xl:.6f} m")
    print(f"  yl = {yl:.6f} m  (half-span)")
    print(f"  zl = {zl:.6f} m")
    print(f"  Domain: 10xl x 5yl x 10zl")
    print(f"         = {cube_dx:.4f} x {cube_dy:.4f} x {cube_dz:.4f} m")

    print(f"\n[Mesh Parameters - User Input]")
    user_headers = ["Parameter", "Value", "Description"]
    user_rows = [
        ["h1", f"{h1:.6f} m", "First cell height"],
        ["layers", layers, "Boundary layer count"],
        ["growth", f"{growth:.4f}", "BL growth rate"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"]
    ]
    print(format_table(user_headers, user_rows))

    print(f"\n[Mesh Parameters - Derived]")
    derived_headers = ["Parameter", "Value", "Formula"]
    derived_rows = [
        ["T (BL total)", f"{T:.6f} m", "h1x(growth^layers-1)/(growth-1)"],
        ["BASE_MINTHICKNESS", f"{base_minthickness:.6f} m", "T x 0.1"],
        ["min_size (=T)", f"{min_size:.6f} m", "= T"],
        ["surf_size (=10xT)", f"{surf_size:.6f} m", "= 10xT"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "= surf_size x 2 = {surf_size * 2:.6f} m"],
        ["max_size (=10xl/50)", f"{max_size:.6f} m", "= 10xl/50"],
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

    # -------------------------------------------------
    # Summary Table (for easy reference)
    # -------------------------------------------------
    print(f"\n" + "="*60)
    print("MESH VARIABLES SUMMARY")
    print("="*60)
    
    summary_headers = ["Parameter", "Value", "Description"]
    summary_rows = [
        # Geometry
        ["xl", f"{xl:.4f} m", "Model length"],
        ["yl", f"{yl:.4f} m", "Model width (half-span)"],
        ["zl", f"{zl:.4f} m", "Model height"],
        # Mesh - User Input
        ["h1", f"{h1:.6f} m", "First cell height"],
        ["layers", layers, "Boundary layer count"],
        ["growth", f"{growth:.4f}", "BL growth rate"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"],
        # Mesh - Derived
        ["T", f"{T:.6f} m", "BL total thickness"],
        ["BASE_MINTHICKNESS", f"{base_minthickness:.6f} m", "T x 0.1"],
        ["min_size", f"{min_size:.6f} m", "T"],
        ["surf_size", f"{surf_size:.6f} m", "10xT"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "= surf_size x 2 = {surf_size * 2:.6f} m"],
        ["max_size", f"{max_size:.6f} m", "10xl/50"],
        # Domain
        ["cube_dx", f"{cube_dx:.4f} m", "Domain length (10xl)"],
        ["cube_dy", f"{cube_dy:.4f} m", "Domain width (5yl)"],
        ["cube_dz", f"{cube_dz:.4f} m", "Domain height (10zl)"],
        # Refine Box
        ["refine_dx", f"{refine_dx:.4f} m", "Wake capture X size (10xl)"],
        ["refine_dy", f"{refine_dy:.4f} m", "Wake capture Y size (2\u00d7STEP yl)"],
        ["refine_dz", f"{refine_dz:.4f} m", "Wake capture Z size (2\u00d7STEP zl)"],
        ["refine_cx,y,z", f"{refine_cx:.2f},{refine_cy:.2f},{refine_cz:.2f}", "Wake capture center"],
        ["refine_tx,y,z", f"{refine_tx:.2f},{refine_ty:.2f},{refine_tz:.2f}", "Translate (-2.5xl, -yl, -zl)"],
        # Faces
        ["far_faces", len(far_faces), "Far-field faces"],
        ["model_faces", len(model_faces), "Model surface faces"],
    ]
    print(format_table(summary_headers, summary_rows))

    # -------------------------------------------------
    # Store arguments to JSON file
    # -------------------------------------------------
    # Preserve user-modified values if they exist
    if os.path.exists(args_file):
        with open(args_file, 'r') as f:
            existing_args = json.load(f)
            min_size = existing_args.get('min_size', min_size)
            surf_size = existing_args.get('surf_size', surf_size)

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
        "BASE_MINTHICKNESS": base_minthickness,
        "min_size": min_size,
        "surf_size": surf_size,
        "max_size": max_size,
        "far_faces_count": len(far_faces),
        "model_faces_count": len(model_faces),
        "cube_dx": cube_dx,
        "cube_dy": cube_dy,
        "cube_dz": cube_dz,
        # Refine Box
        "refine_dx": refine_dx,
        "refine_dy": refine_dy,
        "refine_dz": refine_dz,
        "refine_local_size": refine_local_size,
        "refine_cx": refine_cx,
        "refine_cy": refine_cy,
        "refine_cz": refine_cz,
        "refine_tx": refine_tx,
        "refine_ty": refine_ty,
        "refine_tz": refine_tz,
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
