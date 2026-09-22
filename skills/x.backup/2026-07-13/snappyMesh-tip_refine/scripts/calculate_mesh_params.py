#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 1: Read STL file bounding box → calculate all mesh parameters → write JSON.
Supports tip wake line refinement via auto-discovered {basename}_tip_points.csv.

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
    import struct
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
    stl_cx = (xmin + xmax) / 2
    stl_cy = (ymin + ymax) / 2
    stl_cz = (zmin + zmax) / 2

    box_dx = 10 * xl
    box_dy = 5 * yl
    box_dz = 10 * zl

    tx = stl_cx - 2.5 * xl
    ty = stl_cy - 2.5 * yl
    tz = stl_cz - 5.0 * zl

    box_cx = tx + box_dx / 2
    box_cy = ty + box_dy / 2
    box_cz = tz + box_dz / 2

    far_xmax = box_cx + box_dx / 2

    return box_dx, box_dy, box_dz, tx, ty, tz, box_cx, box_cy, box_cz, stl_cx, stl_cy, stl_cz, far_xmax


def find_refinement_n(min_size, target_size):
    """Find n such that min_size * 2^n is closest to target_size."""
    if min_size <= 0:
        raise ValueError("min_size must be > 0")
    ratio = target_size / min_size
    if ratio <= 0:
        raise ValueError("Invalid ratio")
    n = round(math.log2(ratio))
    actual = min_size * (2 ** n)
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
    """Detect physical CPU cores (no HyperThreading)."""
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
        return max(1, int(subprocess.getoutput('nproc')) // 2)


def discover_tip_points(base_dir, base_name):
    """Auto-discover {basename}_tip_points.csv in the same directory.
    Supports both CSVs with header (x,y,z) and without header.
    Returns (csv_path, tip_points) or (None, []).
    tip_points is a list of dicts: [{'x': ..., 'y': ..., 'z': ...}, ...]
    """
    csv_path = os.path.join(base_dir, f"{base_name}_tip_points.csv")
    if not os.path.exists(csv_path):
        return None, []
    
    tip_points = []
    with open(csv_path, 'r') as f:
        first_line = f.readline().strip()
        if not first_line:
            return None, []
        # Detect header: if first field starts with a letter, it's a header (x,y,z or similar)
        is_header = first_line.split(',')[0].strip().lower()[0].isalpha()
        if is_header:
            # First line is header, skip it
            lines_to_process = [first_line]  # already read
            for line in f:
                pass  # skip header, read remaining lines below
            # Re-read: process all lines after header
            with open(csv_path, 'r') as f2:
                f2.readline()  # skip header
                for line in f2:
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        try:
                            tip_points.append({
                                'x': float(parts[0]),
                                'y': float(parts[1]),
                                'z': float(parts[2])
                            })
                        except ValueError:
                            continue
        else:
            # No header: first line is data
            parts = first_line.split(',')
            if len(parts) >= 3:
                try:
                    tip_points.append({
                        'x': float(parts[0]),
                        'y': float(parts[1]),
                        'z': float(parts[2])
                    })
                except ValueError:
                    pass
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    try:
                        tip_points.append({
                            'x': float(parts[0]),
                            'y': float(parts[1]),
                            'z': float(parts[2])
                        })
                    except ValueError:
                        continue
    return csv_path, tip_points


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

    # === Read STL bounds ===
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

    num_procs = detect_physical_cores()
    print(f"\n[System - CPU Cores]")
    print(f"  Physical cores (no HyperThreading): {num_procs}")
    print(f"  Recommended: mpirun -np {num_procs}")

    stl_surface_name = f"{base_name}_surface"
    print(f"\n[STL Surface Name]")
    print(f"  {stl_surface_name}")

    # === Far box ===
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

    # === Refine box (existing) ===
    refine_dx = 0.5 * box_dx
    refine_dy = 2 * yl
    refine_dz = 2 * zl
    refine_tx = cx - 1.25 * xl
    refine_ty = cy - yl
    refine_tz = cz - zl
    refine_cx = refine_tx + refine_dx / 2
    refine_cy = refine_ty + refine_dy / 2
    refine_cz = refine_tz + refine_dz / 2
    refine_mode = "inside"
    print(f"\n[Refine Box (refine_box_surface)]")
    print(f"  Size: {refine_dx:.6f} x {refine_dy:.6f} x {refine_dz:.6f} m")
    print(f"  Center: ({refine_cx:.6f}, {refine_cy:.6f}, {refine_cz:.6f})")
    print(f"  Translate: ({refine_tx:.6f}, {refine_ty:.6f}, {refine_tz:.6f})")
    print(f"  Mode: {refine_mode}")

    # === Refinement levels ===
    surf_size_level = 5
    max_level = surf_size_level + 2
    feature_level = max_level

    # Boundary layer
    h1 = 0.0001
    layers = 10

    # === Mesh sizes ===
    min_size_level = 6
    target_max = xl * 10 / 50.0
    n_max = round(math.log2(target_max))
    max_size = target_max
    surf_size = max_size * (0.5 ** surf_size_level)
    min_size = surf_size * (0.5 ** (min_size_level - surf_size_level))
    total_thickness = min_size
    totalThickness = total_thickness
    refine_size_level = 2

    # Verification
    print(f"  [VERIFICATION]")
    print(f"  max_size ≈ {target_max:.8f} m (target = 10xl/50 = {xl*10/50.0:.8f} m)")
    print(f"  surf_size = max_size × 0.5^6 = {surf_size:.8f} m (level {surf_size_level})")
    print(f"  min_size = surf_size × 0.5^2 = {min_size:.8f} m (level {min_size_level})")

    # Print all levels
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

    print(f"\n[Refinement Levels]")
    print(f"  surf_size_level = {surf_size_level}")
    print(f"  max_level = {max_level}")
    print(f"  feature_level = {feature_level}")

    print(f"\n[Boundary Layer Parameters]")
    print(f"  h1 = {h1:.6f} m")
    print(f"  nLayers = {layers}")
    print(f"  totalThickness = {totalThickness:.6f} m")
    print(f"  min_size = {min_size:.6f} m")
    print(f"  surf_size = {surf_size:.6f} m")

    print(f"\n[Mesh Sizes]")
    print(f"  surf_size = {surf_size:.8f} m")
    print(f"  min_size = {min_size:.8f} m")
    print(f"  max_size = {max_size:.8f} m")
    print(f"  refine_size_level = {refine_size_level}")

    # === Tip wake line discovery ===
    print(f"\n{'='*60}")
    print("TIP WAKE LINE DISCOVERY")
    print("="*60)
    tip_csv_path, tip_points = discover_tip_points(base_dir, base_name)
    tip_wake_lines = []
    tip_wake_refine_size = None

    if tip_csv_path and tip_points:
        tip_wake_refine_size = surf_size  # = cell size at surf_size_level
        wake_half_w = surf_size * 5  # half width of narrow wake box (total width = 10 × surf_size)
        wake_refine_level = surf_size_level  # tip wake refine level = surf_size_level
        for tip in tip_points:
            # Narrow wake box: tip-centered, 10×surf_size span in Y/Z
            # X: from tip_x → refine_box xmax
            wake_min_x = tip['x']
            wake_max_x = refine_cx + refine_dx / 2  # refine_box xmax
            wake_min_y = tip['y'] - wake_half_w
            wake_max_y = tip['y'] + wake_half_w
            wake_min_z = tip['z'] - wake_half_w
            wake_max_z = tip['z'] + wake_half_w
            tip_wake_lines.append({
                'origin': (tip['x'], tip['y'], tip['z']),
                'end': (wake_max_x, tip['y'], tip['z']),
                'min': (wake_min_x, wake_min_y, wake_min_z),
                'max': (wake_max_x, wake_max_y, wake_max_z),
            })
        print(f"\n  ✓ Tip CSV found: {os.path.basename(tip_csv_path)}")
        print(f"  ✓ Tip points: {len(tip_points)}")
        print(f"  ✓ tip_wake_refine_size = {tip_wake_refine_size:.8f} m (= surf_size)")
        print(f"  ✓ tip_wake_refine_level = {wake_refine_level} (level {wake_refine_level})")
        print(f"  ✓ Wake half-width = {wake_half_w:.8f} m (10×surf_size / 2)")
        print(f"  ✓ Wake lines ({len(tip_wake_lines)}):")
        for i, wline in enumerate(tip_wake_lines):
            print(f"    Line {i+1}: ({wline['origin'][0]:.4f}, {wline['origin'][1]:.4f}, {wline['origin'][2]:.4f})")
            print(f"             → X: {wline['origin'][0]:.4f} → {wline['end'][0]:.4f}")
            print(f"             → Y: {wline['min'][1]:.4f} → {wline['max'][1]:.4f} (span={wline['max'][1]-wline['min'][1]:.4f})")
            print(f"             → Z: {wline['min'][2]:.4f} → {wline['max'][2]:.4f} (span={wline['max'][2]-wline['min'][2]:.4f})")
    else:
        print(f"\n  ✗ No {base_name}_tip_points.csv found — refine-box-only mode")

    # === Summary table ===
    print(f"\n{'='*60}")
    print("MESH VARIABLES SUMMARY")
    print("="*60)
    summary_headers = ["Parameter", "Value", "Description"]
    location_in_mesh_x = (xmax + far_xmax) / 2
    summary_rows = [
        ["xl", f"{xl:.6f} m", "Object X dimension"],
        ["yl", f"{yl:.6f} m", "Object Y dimension"],
        ["zl", f"{zl:.6f} m", "Object Z dimension"],
        ["h1", f"{h1:.6f} m", "First cell height"],
        ["nLayers", layers, "Boundary layer count"],
        ["totalThickness", f"{totalThickness:.6f} m", "Total BL thickness"],
        ["min_size", f"{min_size:.8f} m", "total_thickness"],
        ["surf_size", f"{surf_size:.8f} m", "Surface minimal cell size"],
        ["max_size", f"{max_size:.8f} m", "level 0"],
        ["surf_size_level", surf_size_level, "Surface refinement level"],
        ["max_level", max_level, "= surf_size_level + 2"],
        ["feature_level", feature_level, "Feature edge refinement"],
        ["min_size_level", min_size_level, "= surf_size_level + 2"],
        ["BASE_MINTHICKNESS", f"{totalThickness/2:.8f} m", "= 0.5 × total_thickness"],
        ["box_dx", f"{box_dx:.6f} m", "Far box X"],
        ["box_dy", f"{box_dy:.6f} m", "Far box Y"],
        ["box_dz", f"{box_dz:.6f} m", "Far box Z"],
        ["refine_dx", f"{refine_dx:.6f} m", "Refine box X"],
        ["refine_dy", f"{refine_dy:.6f} m", "Refine box Y"],
        ["refine_dz", f"{refine_dz:.6f} m", "Refine box Z"],
        ["refine_cx,y,z", f"{refine_cx:.6f},{refine_cy:.6f},{refine_cz:.6f}", "Refine box center"],
        ["tx", f"{tx:.6f} m", "Far box corner X"],
        ["ty", f"{ty:.6f} m", "Far box corner Y"],
        ["tz", f"{tz:.6f} m", "Far box corner Z"],
        ["stl_surface_name", stl_surface_name, "STL surface name"],
        ["locationinmesh", f"({location_in_mesh_x:.6f}, {stl_cy:.6f}, {stl_cz:.6f})", "Point outside STL"],
    ]
    print(format_table(summary_headers, summary_rows))

    # === Build JSON ===
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
        "totalThickness": totalThickness,
        "total_thickness": total_thickness,
        "min_size": min_size,
        "surf_size": surf_size,
        "max_size": max_size,
        "surf_size_level": surf_size_level,
        "max_level": max_level,
        "feature_level": feature_level,
        "min_size_level": min_size_level,
        "max_size_level": 0,
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
        # Tip wake line fields (only if CSV found)
        "tip_csv_path": tip_csv_path,
        "tip_points_count": len(tip_points),
        "tip_points": [{"x": p['x'], "y": p['y'], "z": p['z']} for p in tip_points],
        "tip_wake_lines": tip_wake_lines,
        "tip_wake_refine_size": tip_wake_refine_size,
        "wake_refine_level": wake_refine_level,
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
