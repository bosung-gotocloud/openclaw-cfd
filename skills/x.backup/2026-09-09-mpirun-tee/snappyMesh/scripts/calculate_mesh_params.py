#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 1: Read STL file bounding box → calculate all mesh parameters → write JSON.

No SALOME dependency — reads STL directly.

Usage: calculate_mesh_params.py <filename>.stl
Output: {filename}_mesh_args.json
"""
import sys
import os
import math
import json

_log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "calculate_mesh_params.log")
sys.stdout = open(_log_file, 'w')

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

def read_binary_stl_bounds(filename):
    """Read binary STL and extract bounding box."""
    with open(filename, 'rb') as f:
        f.read(80)  # skip header
        num_triangles = struct.unpack('<I', f.read(4))[0]
        xmin = xmax = ymin = ymax = zmin = zmax = None
        for _ in range(num_triangles):
            data = struct.unpack('<9f', f.read(36))
            for i in range(3, 12, 3):
                x, y, z = data[i], data[i+1], data[i+2]
                if xmin is None or x < xmin: xmin = x
                if xmax is None or x > xmax: xmax = x
                if ymin is None or y < ymin: ymin = y
                if ymax is None or y > ymax: ymax = y
                if zmin is None or z < zmin: zmin = z
                if zmax is None or z > zmax: zmax = z
        return xmin, xmax, ymin, ymax, zmin, zmax

def read_ascii_stl_bounds(filename):
    """Read ASCII STL and extract bounding box."""
    xmin = xmax = ymin = ymax = zmin = zmax = None
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if parts and parts[0] == 'vertex':
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                if xmin is None or x < xmin: xmin = x
                if xmax is None or x > xmax: xmax = x
                if ymin is None or y < ymin: ymin = y
                if ymax is None or y > ymax: ymax = y
                if zmin is None or z < zmin: zmin = z
                if zmax is None or z > zmax: zmax = z
    return xmin, xmax, ymin, ymax, zmin, zmax

def compute_far_box(xmin, xmax, ymin, ymax, zmin, zmax, xl, yl, zl):
    """Compute far box with asymmetric margins for aircraft/aerospace (small front, large back).
    Returns: box_dx, box_dy, box_dz, tx, ty, tz, box_cx, box_cy, box_cz
    """
    # Center of the STL (this must NOT be overwritten by box center!)
    stl_cx = (xmin + xmax) / 2
    stl_cy = (ymin + ymax) / 2
    stl_cz = (zmin + zmax) / 2

    # Box dimensions
    box_dx = 10 * xl
    box_dy = 5 * yl
    box_dz = 10 * zl

    # Asymmetric offsets: smaller margin at the front, larger at the back
    tx = stl_cx - 2.5 * xl
    ty = stl_cy - 2.5 * yl
    tz = stl_cz - 5.0 * zl

    # Actual far box center
    box_cx = tx + box_dx / 2
    box_cy = ty + box_dy / 2
    box_cz = tz + box_dz / 2

    # far_xmax = box corner (max side)
    far_xmax = box_cx + box_dx / 2

    return box_dx, box_dy, box_dz, tx, ty, tz, box_cx, box_cy, box_cz, stl_cx, stl_cy, stl_cz, far_xmax

def find_refinement_n(min_size, target_size):
    """Find n such that min_size * 2^n is closest to target_size.
    Return (n, actual_size).
    """
    if min_size <= 0:
        raise ValueError("min_size must be > 0")
    ratio = target_size / min_size
    if ratio <= 0:
        raise ValueError("Invalid ratio")
    n = round(math.log2(ratio))
    actual = min_size * (2 ** n)
    # Verify closest
    n_minus = min_size * (2 ** (n - 1))
    n_plus = min_size * (2 ** (n + 1))
    if abs(n_minus - target_size) < abs(actual - target_size):
        n -= 1
        actual = n_minus
    elif abs(n_plus - target_size) < abs(actual - target_size):
        n += 1
        actual = n_plus
    return n, actual

def detect_physical_cores():
    """Detect physical CPU cores (no HyperThreading) for parallel execution.
    Works on any Linux system via /proc/cpuinfo."""
    import subprocess
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        sockets = len(set(
            line.split(':')[1].strip()
            for line in cpuinfo.splitlines()
            if line.startswith('physical id')
        ))
        cores_per_socket = int(
            [line for line in cpuinfo.splitlines()
             if line.startswith('cpu cores')][0].split(':')[1].strip()
        )
        return sockets * cores_per_socket
    except Exception:
        # Fallback: use nproc // 2 (for HT systems)
        return max(1, int(subprocess.getoutput('nproc')) // 2)

def main():
    import struct

    stl_path = None
    for arg in sys.argv:
        if arg.lower().endswith(('.stl', '.stp', '.step')):
            if ':' in arg:
                _, filename = arg.split(':', 1)
                stl_path = filename
            else:
                stl_path = os.path.abspath(arg)

    if not stl_path or not os.path.exists(stl_path):
        print("ERROR: STL file not found.")
        return

    base_dir = os.path.dirname(os.path.abspath(stl_path))
    base_name = os.path.splitext(os.path.basename(stl_path))[0]
    args_file = os.path.join(base_dir, f"{base_name}_mesh_args.json")

    # Read STL bounds
    print(f"\n{'='*60}")
    print(f"STAGE 1: STL BOUNDING BOX ANALYSIS")
    print(f"{'='*60}")

    if stl_path.lower().endswith('.stl'):
        with open(stl_path, 'rb') as f:
            first_bytes = f.read(256)
            f.seek(0)
        if first_bytes[:5] == b'solid':
            xmin, xmax, ymin, ymax, zmin, zmax = read_ascii_stl_bounds(stl_path)
            fmt = "ASCII"
        else:
            xmin, xmax, ymin, ymax, zmin, zmax = read_binary_stl_bounds(stl_path)
            fmt = "Binary"
    else:
        # For STEP files, use a fallback or warn
        print("WARNING: STEP file detected — using placeholder bounds.")
        xmin, xmax, ymin, ymax, zmin, zmax = 0, 1, 0, 1, 0, 1
        fmt = "STEP"

    xl = xmax - xmin
    yl = ymax - ymin
    zl = zmax - zmin
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    cz = (zmin + zmax) / 2

    print(f"\n[STL Bounds] ({fmt} format)")
    print(f"  xmin={xmin:.8f}  xmax={xmax:.8f}")
    print(f"  ymin={ymin:.8f}  ymax={ymax:.8f}")
    print(f"  zmin={zmin:.8f}  zmax={zmax:.8f}")
    print(f"\n[Object Dimensions]")
    print(f"  xl = {xl:.8f} m")
    print(f"  yl = {yl:.8f} m")
    print(f"  zl = {zl:.8f} m")
    print(f"  Center: ({cx:.6f}, {cy:.6f}, {cz:.6f})")

    # Detect physical cores
    num_procs = detect_physical_cores()
    print(f"\n[System - CPU Cores]")
    print(f"  Physical cores (no HyperThreading): {num_procs}")
    print(f"  Recommended: mpirun -np {num_procs}")

    # STL surface name
    stl_surface_name = f"{base_name}_surface"
    print(f"\n[STL Surface Name]")
    print(f"  {stl_surface_name}")

    # Far box
    box_dx, box_dy, box_dz, tx, ty, tz, box_cx, box_cy, box_cz, stl_cx, stl_cy, stl_cz, far_xmax = compute_far_box(xmin, xmax, ymin, ymax, zmin, zmax, xl, yl, zl)
    far_box_center = (box_cx, box_cy, box_cz)
    margin_x = (box_dx - xl) / 2
    margin_y = (box_dy - yl) / 2
    margin_z = (box_dz - zl) / 2
    print(f"\n[Far Box (far_surface)]")
    print(f"  Size: {box_dx:.6f} x {box_dy:.6f} x {box_dz:.6f} m")
    print(f"  Center: ({far_box_center[0]:.6f}, {far_box_center[1]:.6f}, {far_box_center[2]:.6f})")
    print(f"  Corner (outside STL): ({tx:.6f}, {ty:.6f}, {tz:.6f})")
    print(f"  Margin from STL: ({margin_x:.6f}, {margin_y:.6f}, {margin_z:.6f})")

    # Refine box (region refinement around STL object in castellatedMeshControls)
    # X size = 0.5 * farbox_xsize, Y = 2 * stl_ysize, Z = 2 * stl_zsize
    # Translate: (cx - 1.25*xl), (cy - yl), (cz - zl) relative to STL center
    refine_dx = 0.5 * box_dx
    refine_dy = 2 * yl
    refine_dz = 2 * zl
    # Calculate translate amounts (same as salome-snappy)
    refine_tx = cx - 1.25 * xl
    refine_ty = cy - yl
    refine_tz = cz - zl
    # Center after translate: tx + size/2
    refine_cx = refine_tx + refine_dx / 2
    refine_cy = refine_ty + refine_dy / 2
    refine_cz = refine_tz + refine_dz / 2
    # Refine mode: "inside" or "outside"
    refine_mode = "inside"
    # Print refine box info (refine_size_level set after min_size_level calc below)
    print(f"\n[Refine Box (refine_box_surface)]")
    print(f"  Size: {refine_dx:.6f} x {refine_dy:.6f} x {refine_dz:.6f} m")
    print(f"  Center: ({refine_cx:.6f}, {refine_cy:.6f}, {refine_cz:.6f})")
    print(f"  Translate: ({refine_tx:.6f}, {refine_ty:.6f}, {refine_tz:.6f})")
    print(f"  Mode: {refine_mode}")

    # === Refinement levels (FIXED) ===
    surf_size_level = 6          # default surface size level
    max_level = surf_size_level + 2   # 8
    feature_level = max_level            # 8

    # Boundary layer defaults (all modifiable in {filename}_mesh_args.json)
    h1 = 0.0001     # first cell height
    layers = 10     # number of boundary layer
    growth = 1.3    # expansionRatio

    # === Compute mesh sizes from top-down ===
    # Step 1: Compute min_size_level first
    min_size_level = surf_size_level + 2   # = 8

    # Step 2: Compute target_max and find max_size
    target_max = xl * 10 / 50.0
    # We need n such that max_size = min_size × 2^n ≈ target_max
    # Since min_size = surf_size × 0.5^2 and surf_size = max_size × 0.5^6
    # => min_size = max_size × 0.5^8
    # => max_size = min_size × 2^8 = min_size × 256
    # So: target_max ≈ min_size × 256 × 2^n => n ≈ log2(target_max / min_size / 256)
    # But simpler: use find_refinement_n with a known min_size estimate
    # First pass: use target_max directly to find max_size at level 0
    n, max_size = find_refinement_n(target_max, target_max)  # max_size ≈ target_max
    # Actually, max_size IS the nearest 2^n of target_max
    # So we just set max_size = target_max rounded to nearest 2^n
    n_max = round(math.log2(target_max))
    max_size = target_max * (2 ** (n_max - round(math.log2(target_max))))
    # Simpler: just use find_refinement_n properly
    # find_refinement_n(min_size, target) returns (n, actual)
    # We want max_size such that n ≈ log2(target_max / some_ref)
    # Let's do it differently:
    n_max = round(math.log2(target_max))
    max_size = target_max  # approximate, will be refined
    # Actually max_size should be the nearest power-of-2 multiple of some base
    # The original logic: find n so that min_size * 2^n ≈ target_max
    # But now min_size depends on surf_size which depends on max_size!
    # So we iterate:
    #   max_size ≈ target_max (initial guess)
    #   surf_size = max_size × 0.5^6
    #   min_size = surf_size × 0.5^2 = max_size × 0.5^8
    #   Check: min_size × 2^n ≈ target_max → n = log2(target_max / min_size) = log2(target_max / (max_size × 0.5^8))
    #   n = log2(target_max) - log2(max_size) + 8 ≈ 8 (since max_size ≈ target_max)
    # So min_size_level = 8 is correct, and max_size ≈ target_max
    
    # Step 3: surf_size at level 6
    surf_size = max_size * (0.5 ** surf_size_level)

    # Step 4: min_size = surf_size × 0.5^(min_size_level - surf_size_level) = surf_size × 0.5^2
    # This is the boundary layer total thickness
    min_size = surf_size * (0.5 ** (min_size_level - surf_size_level))
    total_thickness = min_size
    totalThickness = total_thickness  # alias

    max_size_level = 0
    refine_size_level = 2
    
    # Verification
    print(f"  [VERIFICATION]")
    print(f"  max_size ≈ {target_max:.8f} m (target = 10xl/50 = {xl*10/50.0:.8f} m)")
    print(f"  surf_size = max_size × 0.5^6 = {surf_size:.8f} m (level {surf_size_level})")
    print(f"  min_size = surf_size × 0.5^2 = {min_size:.8f} m (level {min_size_level} = surf_size_level + 2)")
    print(f"  min_size_level = {min_size_level}")

    # Print all levels with corresponding cell sizes
    print(f"\n{'='*60}")
    print("REFINEMENT LEVELS WITH CELL SIZES")
    print("="*60)
    print(f"  max_size (base) = {max_size:.10f} m")
    print(f"  {'Level':>8} | {'Cell Size (m)':>18} | {'Formula':>30}")
    print(f"  {'-'*6:>8} | {'-'*16:>18} | {'-'*28:>30}")
    for lvl in range(0, min_size_level + 1):
        cell_size = max_size * (0.5 ** lvl)
        print(f"  {lvl:>8} | {cell_size:>18.10f} | max_size * (1/2)^{lvl}")
    print(f"\n  surf_size  = {surf_size:.10f} m  (level {surf_size_level})")
    print(f"  min_size   = {min_size:.10f} m  (level {min_size_level})")
    print(f"  max_size   = {max_size:.10f} m  (level 0)")

    print(f"\n[Refinement Levels]")
    print(f"  surf_size_level = {surf_size_level}")
    print(f"  max_level = {max_level} (surf_size_level + 2)")
    print(f"  feature_level = {feature_level}")

    print(f"\n[Boundary Layer Parameters]")
    print(f"  h1 = {h1:.6f} m (first cell height)")
    print(f"  nLayers = {layers}")
    print(f"  growth = {growth} (expansionRatio)")
    print(f"  totalThickness = {totalThickness:.6f} m (user input)")
    print(f"  total_thickness = {total_thickness:.6f} m (= surf_size × 0.5^(max_level-surf_size_level) = {totalThickness:.6f} × 0.5^({max_level - surf_size_level}))")
    print(f"  min_size = {min_size:.6f} m (= total_thickness)")
    print(f"  surf_size = {surf_size:.6f} m (= surface minimal cell size at max_level={max_level})")

    print(f"\n[Mesh Sizes]")
    print(f"  surf_size = {surf_size:.8f} m (surface minimal cell size, user input at max_level={max_level})")
    print(f"  total_thickness = {total_thickness:.8f} m (= surf_size × 0.5^({min_size_level - surf_size_level}) = surf_size × 0.5^2)")
    print(f"  min_size = {min_size:.8f} m (= total_thickness)")
    print(f"  max_size = {max_size:.8f} m (level 0, target = {target_max:.8f} m)")
    print(f"  min_size_level = {min_size_level} (= surf_size_level + 2)")
    print(f"  surf_size_level = {surf_size_level}")
    print(f"  max_level = {max_level}, feature_level = {feature_level}")

    print(f"\n{'='*60}")
    print("MESH VARIABLES SUMMARY")
    print("="*60)
    summary_headers = ["Parameter", "Value", "Description"]
    # locationInMesh: midpoint between STL xmax and far_xmax (outside STL)
    location_in_mesh_x = (xmax + far_xmax) / 2
    summary_rows = [
        ["xl", f"{xl:.6f} m", "Object X dimension"],
        ["yl", f"{yl:.6f} m", "Object Y dimension"],
        ["zl", f"{zl:.6f} m", "Object Z dimension"],
        ["h1", f"{h1:.6f} m", "First cell height"],
        ["nLayers", layers, "Boundary layer count"],
        ["growth", f"{growth}", "Expansion ratio"],
        ["totalThickness", f"{totalThickness:.6f} m", "Total BL thickness (= min_size)"],
        ["total_thickness", f"{total_thickness:.8f} m", f"= surf_size × 0.5^(max_level-surf_size_level) = surf_size × 0.5^({max_level - surf_size_level})"],
        ["min_size", f"{min_size:.8f} m", "= total_thickness"],
        ["surf_size", f"{surf_size:.8f} m", f"Surface minimal cell size (max_level={max_level})"],
        ["max_size", f"{max_size:.8f} m", "level 0"],
        ["surf_size_level", surf_size_level, "Surface refinement level (default 6)"],
        ["max_level", max_level, "= surf_size_level + 2"],
        ["feature_level", feature_level, "Feature edge refinement level"],
        ["BASE_MINTHICKNESS", f"{total_thickness/2:.8f} m", f"= 0.5 × total_thickness (T={total_thickness:.6f})"],
        ["box_dx", f"{box_dx:.6f} m", "Far box X"],
        ["box_dy", f"{box_dy:.6f} m", "Far box Y"],
        ["box_dz", f"{box_dz:.6f} m", "Far box Z"],
        ["refine_dx", f"{refine_dx:.6f} m", "Refine box X (0.5 * farbox_x)"],
        ["refine_dy", f"{refine_dy:.6f} m", "Refine box Y (2 * stl_ysize)"],
        ["refine_dz", f"{refine_dz:.6f} m", "Refine box Z (2 * stl_zsize)"],
        ["refine_cx,y,z", f"{refine_cx:.6f},{refine_cy:.6f},{refine_cz:.6f}", "Refine box center"],
        ["refine_tx,y,z", f"{refine_tx:.6f},{refine_ty:.6f},{refine_tz:.6f}", "Refine box translate"],
        ["tx", f"{tx:.6f} m", "Far box corner X"],
        ["ty", f"{ty:.6f} m", "Far box corner Y"],
        ["tz", f"{tz:.6f} m", "Far box corner Z"],
        ["stl_surface_name", stl_surface_name, "STL surface name"],
        ["locationinmesh", f"({location_in_mesh_x:.6f}, {stl_cy:.6f}, {stl_cz:.6f}) m", f"Point outside STL (between xmax={xmax:.6f} and far_xmax={far_xmax:.6f})"],
    ]
    print(format_table(summary_headers, summary_rows))

    args = {
        "stl_path": stl_path,
        "base_dir": base_dir,
        "base_name": base_name,
        "num_procs": num_procs,
        "xl": xl,
        "yl": yl,
        "zl": zl,
        "cx": stl_cx,
        "cy": stl_cy,
        "cz": stl_cz,
        "h1": h1,
        "layers": layers,
        "growth": growth,
        "totalThickness": totalThickness,      # user input = surf_size at max_level
        "total_thickness": total_thickness,    # = surf_size × 0.5²
        "min_size": min_size,
        "surf_size": surf_size,                # surface minimal cell size (max_level=8)
        "max_size": max_size,
        "surf_size_level": surf_size_level,    # default 6
        "max_level": max_level,                # = surf_size_level + 2
        "feature_level": feature_level,        # = max_level
        "min_size_level": min_size_level,
        "max_size_level": max_size_level,
        "box_dx": box_dx,
        "box_dy": box_dy,
        "box_dz": box_dz,
        "tx": tx,
        "ty": ty,
        "tz": tz,
        "far_box_center": [box_cx, box_cy, box_cz],
        "stl_surface_name": stl_surface_name,
        "locationinmesh": [location_in_mesh_x, stl_cy, stl_cz],
        "BASE_MINTHICKNESS": totalThickness / 2,
        "refine_dx": refine_dx,
        "refine_dy": refine_dy,
        "refine_dz": refine_dz,
        "refine_cx": refine_cx,
        "refine_cy": refine_cy,
        "refine_cz": refine_cz,
        "refine_tx": refine_tx,
        "refine_ty": refine_ty,
        "refine_tz": refine_tz,
        "refine_mode": refine_mode,
        "refine_size_level": refine_size_level,
    }

    with open(args_file, 'w') as f:
        json.dump(args, f, indent=2)

    print(f"\n{'='*60}")
    print("PARAMETERS CALCULATED")
    print("="*60)
    print(f"\n  📄 Args saved to: {os.path.basename(args_file)}")
    print(f"\n  ⚠️  Please review and edit {os.path.basename(args_file)} if needed.")
    print(f"  🔒 Workflow is PAUSED — no further steps will execute automatically.")
    print(f"\n  To proceed:")
    print(f"    1. Review {os.path.basename(args_file)}")
    print(f"    2. Modify any parameter values as needed")
    print(f"    3. Confirm by replying with 'proceed', 'go', or 'yes'")
    print("="*60)

if __name__ == "__main__":
    main()
