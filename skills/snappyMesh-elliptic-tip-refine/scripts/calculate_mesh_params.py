#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 1 for snappyMesh-elliptic-tip-refine.

Reads an STL bounding box, calculates elliptic far/refine parameters,
generates watertight axisymmetric ellipsoid STLs, discovers optional tip
points, and writes {basename}_mesh_args.json.

The far ellipsoid follows the SALOME elliptic convention:
    dx, max(dy, dz) axisymmetric about X.

Usage:
    python3 calculate_mesh_params.py model.stl

Output:
    model_mesh_args.json
    model_far_ellipsoid.stl
    model_refine_ellipsoid.stl
"""

import sys
import os
import math
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ellipsoid_stl import generate_axisymmetric_ellipsoid_stl

_log_file = os.path.join(_SCRIPT_DIR, "calculate_mesh_params.log")
sys.stdout = open(_log_file, "w")


def format_table(headers, rows):
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
    import struct
    with open(filename, "rb") as f:
        f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]
        xmin = xmax = ymin = ymax = zmin = zmax = None
        for _ in range(num_triangles):
            data = struct.unpack("<12fH", f.read(50))
            for i in range(3, 12, 3):
                x, y, z = data[i], data[i + 1], data[i + 2]
                if xmin is None or x < xmin:
                    xmin = x
                if xmax is None or x > xmax:
                    xmax = x
                if ymin is None or y < ymin:
                    ymin = y
                if ymax is None or y > ymax:
                    ymax = y
                if zmin is None or z < zmin:
                    zmin = z
                if zmax is None or z > zmax:
                    zmax = z
    return xmin, xmax, ymin, ymax, zmin, zmax


def read_ascii_stl_bounds(filename):
    xmin = xmax = ymin = ymax = zmin = zmax = None
    with open(filename, "r") as f:
        for line in f:
            parts = line.strip().split()
            if parts and parts[0] == "vertex":
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                if xmin is None or x < xmin:
                    xmin = x
                if xmax is None or x > xmax:
                    xmax = x
                if ymin is None or y < ymin:
                    ymin = y
                if ymax is None or y > ymax:
                    ymax = y
                if zmin is None or z < zmin:
                    zmin = z
                if zmax is None or z > zmax:
                    zmax = z
    return xmin, xmax, ymin, ymax, zmin, zmax


def detect_physical_cores():
    import subprocess
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        sockets = len(set(
            line.split(":")[1].strip()
            for line in cpuinfo.splitlines()
            if line.startswith("physical id")
        ))
        cores_per_socket = int(
            [line for line in cpuinfo.splitlines() if line.startswith("cpu cores")][0]
            .split(":")[1].strip()
        )
        return max(1, sockets * cores_per_socket)
    except Exception:
        return max(1, int(subprocess.getoutput("nproc")) // 2)


def discover_tip_points(base_dir, base_name):
    csv_path = os.path.join(base_dir, f"{base_name}_tip_points.csv")
    if not os.path.exists(csv_path):
        return None, []

    tip_points = []
    with open(csv_path, "r") as f:
        first_line = f.readline().strip()
        if not first_line:
            return None, []

        def _parse_line(line):
            parts = line.strip().split(",")
            if len(parts) >= 3:
                try:
                    return {"x": float(parts[0]), "y": float(parts[1]), "z": float(parts[2])}
                except ValueError:
                    return None
            return None

        first_field = first_line.split(",")[0].strip().lower()
        is_header = first_field and first_field[0].isalpha()
        if is_header:
            for line in f:
                pt = _parse_line(line)
                if pt:
                    tip_points.append(pt)
        else:
            pt = _parse_line(first_line)
            if pt:
                tip_points.append(pt)
            for line in f:
                pt = _parse_line(line)
                if pt:
                    tip_points.append(pt)

    return csv_path, tip_points


def main():
    stl_path = None
    for arg in sys.argv:
        if arg.lower().endswith((".stl", ".stp", ".step")):
            if ":" in arg:
                _, filename = arg.split(":", 1)
                stl_path = filename
            else:
                stl_path = os.path.abspath(arg)
            break

    if not stl_path or not os.path.exists(stl_path):
        print("ERROR: STL file not found.")
        return

    base_dir = os.path.dirname(os.path.abspath(stl_path))
    base_name = os.path.splitext(os.path.basename(stl_path))[0]
    args_file = os.path.join(base_dir, f"{base_name}_mesh_args.json")

    print(f"\n{'=' * 60}")
    print("STAGE 1: STL BOUNDING BOX + ELLIPTIC FAR/REFINE PARAMETERS")
    print("=" * 60)

    if stl_path.lower().endswith(".stl"):
        with open(stl_path, "rb") as f:
            first_bytes = f.read(256)
        if first_bytes[:5] == b"solid":
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
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    cz = (zmin + zmax) / 2.0

    print(f"\n[STL Bounds] ({fmt})")
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
    print(f"  Physical cores: {num_procs}")

    model_surface_name = f"{base_name}_surface"

    # ------------------------------------------------------------------
    # Far ellipsoid: SALOME-like axisymmetric x-ellipsoid.
    # Base far box dimensions:
    #   dx = 10 xl
    #   dy = 5 yl
    #   dz = 10 zl
    # Ellipsoid semi-axes:
    #   a_x  = dx / 2
    #   a_yz = max(dy, dz) / 2
    # Position:
    #   model center is 25% from upstream / 75% to downstream.
    # ------------------------------------------------------------------
    far_dx = 10.0 * xl
    far_dy = 5.0 * yl
    far_dz = 10.0 * zl

    far_a_x = far_dx / 2.0
    far_a_yz = max(far_dy, far_dz) / 2.0

    far_center = [
        cx + 0.25 * far_dx,
        cy,
        cz,
    ]

    far_xmin = far_center[0] - far_a_x
    far_xmax = far_center[0] + far_a_x
    far_ymax = far_center[1] + far_a_yz
    far_zmax = far_center[2] + far_a_yz

    print(f"\n[Far Ellipsoid]")
    print(f"  Base dx, dy, dz: {far_dx:.6f} x {far_dy:.6f} x {far_dz:.6f} m")
    print(f"  Semi-axes: a_x={far_a_x:.6f}, a_yz={far_a_yz:.6f}")
    print(f"  Center: ({far_center[0]:.6f}, {far_center[1]:.6f}, {far_center[2]:.6f})")
    print(f"  X extent: [{far_xmin:.6f}, {far_xmax:.6f}]")
    print(f"  Y/Z radius: {far_a_yz:.6f}")

    # ------------------------------------------------------------------
    # Base mesh size.
    # max_size is based on the largest far ellipsoid extent.
    # ------------------------------------------------------------------
    far_max_extent = max(far_dx, 2.0 * far_a_yz)
    max_size = far_max_extent / 50.0

    target_surf_size = xl * 0.005
    best_level = 0
    best_diff = abs(max_size - target_surf_size)
    for level in range(0, 25):
        cell_at_level = max_size * (0.5 ** level)
        diff = abs(cell_at_level - target_surf_size)
        if diff < best_diff:
            best_diff = diff
            best_level = level

    surf_size_level = best_level
    surf_size = max_size * (0.5 ** surf_size_level)
    min_size_level = surf_size_level + 2
    min_size = surf_size * 0.25
    max_level = min_size_level
    feature_level = min_size_level
    refine_size_level = 2

    print(f"\n[Mesh Sizes]")
    print(f"  max_size = {max_size:.10f} m  (far_max_extent/50)")
    print(f"  target_surf_size = {target_surf_size:.10f} m  (xl * 0.005)")
    print(f"  surf_size_level = {surf_size_level}")
    print(f"  surf_size = {surf_size:.10f} m")
    print(f"  min_size_level = {min_size_level}")
    print(f"  min_size = {min_size:.10f} m")
    print(f"  refine_size_level = {refine_size_level}")

    # ------------------------------------------------------------------
    # blockMesh box: circumscribes far ellipsoid with margin.
    # ------------------------------------------------------------------
    far_block_margin_fraction = 0.05
    margin = max(
        far_block_margin_fraction * far_max_extent,
        max_size,
    )

    block_dx = far_dx + 2.0 * margin
    block_dy = 2.0 * far_a_yz + 2.0 * margin
    block_dz = 2.0 * far_a_yz + 2.0 * margin

    block_min = [
        far_center[0] - far_a_x - margin,
        far_center[1] - far_a_yz - margin,
        far_center[2] - far_a_yz - margin,
    ]
    block_max = [
        far_center[0] + far_a_x + margin,
        far_center[1] + far_a_yz + margin,
        far_center[2] + far_a_yz + margin,
    ]

    print(f"\n[blockMesh Box]")
    print(f"  margin = {margin:.8f} m")
    print(f"  size   = {block_dx:.8f} x {block_dy:.8f} x {block_dz:.8f} m")
    print(f"  min    = ({block_min[0]:.8f}, {block_min[1]:.8f}, {block_min[2]:.8f})")
    print(f"  max    = ({block_max[0]:.8f}, {block_max[1]:.8f}, {block_max[2]:.8f})")

    # ------------------------------------------------------------------
    # Refine ellipsoid: same axisymmetric convention.
    # Base refine box:
    #   refine_dx = 0.5 * far_dx = 5 xl
    #   refine_dy = 2 yl
    #   refine_dz = 2 zl
    # Semi-axes:
    #   a_x  = refine_dx / 2
    #   a_yz = max(refine_dy, refine_dz) / 2
    # ------------------------------------------------------------------
    refine_dx = 0.5 * far_dx
    refine_dy = 2.0 * yl
    refine_dz = 2.0 * zl

    refine_a_x = refine_dx / 2.0
    refine_a_yz = max(refine_dy, refine_dz) / 2.0

    refine_center = [
        cx + 0.25 * refine_dx,
        cy,
        cz,
    ]

    refine_xmin = refine_center[0] - refine_a_x
    refine_xmax = refine_center[0] + refine_a_x

    print(f"\n[Refine Ellipsoid]")
    print(f"  Base refine_dx, refine_dy, refine_dz: {refine_dx:.6f} x {refine_dy:.6f} x {refine_dz:.6f} m")
    print(f"  Semi-axes: a_x={refine_a_x:.6f}, a_yz={refine_a_yz:.6f}")
    print(f"  Center: ({refine_center[0]:.6f}, {refine_center[1]:.6f}, {refine_center[2]:.6f})")
    print(f"  X extent: [{refine_xmin:.6f}, {refine_xmax:.6f}]")
    print(f"  Refine level: {refine_size_level}")

    # ------------------------------------------------------------------
    # Boundary layer defaults.
    # ------------------------------------------------------------------
    h1 = 0.0001
    growth = 1.3
    layers = 10

    print(f"\n[Boundary Layer Defaults]")
    print(f"  firstLayerThickness h1 = {h1:.8f} m")
    print(f"  expansionRatio growth  = {growth}")
    print(f"  nSurfaceLayers layers  = {layers}")

    # ------------------------------------------------------------------
    # locationInMesh: inside far ellipsoid, outside model.
    # ------------------------------------------------------------------
    location_in_mesh_x = (xmax + far_xmax) / 2.0
    locationinmesh = [location_in_mesh_x, cy, cz]

    # ------------------------------------------------------------------
    # Generate ellipsoid STLs.
    # ------------------------------------------------------------------
    far_stl_name = f"{base_name}_far_ellipsoid.stl"
    far_stl_path = os.path.join(base_dir, far_stl_name)
    far_res_u = 160
    far_res_v = 80

    refine_stl_name = f"{base_name}_refine_ellipsoid.stl"
    refine_stl_path = os.path.join(base_dir, refine_stl_name)
    refine_res_u = 96
    refine_res_v = 48

    print(f"\n[Generating Ellipsoid STLs]")
    far_tri = generate_axisymmetric_ellipsoid_stl(
        center=far_center,
        a_x=far_a_x,
        a_yz=far_a_yz,
        out_path=far_stl_path,
        res_u=far_res_u,
        res_v=far_res_v,
        binary=True,
    )
    print(f"  far    STL: {os.path.basename(far_stl_path)} ({far_tri} triangles)")

    refine_tri = generate_axisymmetric_ellipsoid_stl(
        center=refine_center,
        a_x=refine_a_x,
        a_yz=refine_a_yz,
        out_path=refine_stl_path,
        res_u=refine_res_u,
        res_v=refine_res_v,
        binary=True,
    )
    print(f"  refine STL: {os.path.basename(refine_stl_path)} ({refine_tri} triangles)")

    # ------------------------------------------------------------------
    # Tip wake line discovery.
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print("TIP WAKE LINE DISCOVERY")
    print("=" * 60)

    tip_csv_path, tip_points = discover_tip_points(base_dir, base_name)
    tip_wake_lines = []
    tip_wake_refine_size = None

    if tip_csv_path and tip_points:
        tip_wake_refine_size = surf_size
        wake_refine_level = surf_size_level
        wake_half_y = surf_size * 5.0
        wake_half_z = surf_size * 10.0
        wake_max_x = refine_center[0] + refine_a_x

        for tip in tip_points:
            tip_wake_lines.append({
                "origin": [tip["x"], tip["y"], tip["z"]],
                "end": [wake_max_x, tip["y"], tip["z"]],
                "min": [tip["x"], tip["y"] - wake_half_y, tip["z"] - wake_half_z],
                "max": [wake_max_x, tip["y"] + wake_half_y, tip["z"] + wake_half_z],
            })

        print(f"\n  Tip CSV: {os.path.basename(tip_csv_path)}")
        print(f"  Tip points: {len(tip_points)}")
        print(f"  wake_refine_level = {wake_refine_level}")
        print(f"  tip_wake_refine_size = {tip_wake_refine_size:.8f} m")
        print(f"  wake Y half-width = {wake_half_y:.8f} m")
        print(f"  wake Z half-width = {wake_half_z:.8f} m")
        print(f"  wake downstream end = {wake_max_x:.8f} m")
    else:
        print(f"\n  No {base_name}_tip_points.csv found — refine-ellipsoid-only mode")

    # ------------------------------------------------------------------
    # Summary.
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print("MESH VARIABLES SUMMARY")
    print("=" * 60)

    summary_rows = [
        ["xl", f"{xl:.6f} m", "object X length"],
        ["yl", f"{yl:.6f} m", "object Y size"],
        ["zl", f"{zl:.6f} m", "object Z size"],
        ["max_size", f"{max_size:.8f} m", "level 0 cell size"],
        ["surf_size", f"{surf_size:.8f} m", f"level {surf_size_level}"],
        ["min_size", f"{min_size:.8f} m", f"level {min_size_level}"],
        ["h1", f"{h1:.8f} m", "first layer thickness"],
        ["growth", growth, "layer expansion ratio"],
        ["layers", layers, "surface layer count"],
        ["far_dx", f"{far_dx:.6f} m", "far base dx"],
        ["far_dy", f"{far_dy:.6f} m", "far base dy"],
        ["far_dz", f"{far_dz:.6f} m", "far base dz"],
        ["far_a_x", f"{far_a_x:.6f} m", "far semi-axis X"],
        ["far_a_yz", f"{far_a_yz:.6f} m", "far semi-axis Y/Z"],
        ["far_center", f"{far_center[0]:.6f},{far_center[1]:.6f},{far_center[2]:.6f}", "far ellipsoid center"],
        ["far_stl", far_stl_name, "far boundary STL"],
        ["block_dx", f"{block_dx:.6f} m", "blockMesh X size"],
        ["block_dy", f"{block_dy:.6f} m", "blockMesh Y size"],
        ["block_dz", f"{block_dz:.6f} m", "blockMesh Z size"],
        ["block_margin", f"{margin:.6f} m", "blockMesh margin around far ellipsoid"],
        ["refine_dx", f"{refine_dx:.6f} m", "refine base dx"],
        ["refine_dy", f"{refine_dy:.6f} m", "refine base dy"],
        ["refine_dz", f"{refine_dz:.6f} m", "refine base dz"],
        ["refine_a_x", f"{refine_a_x:.6f} m", "refine semi-axis X"],
        ["refine_a_yz", f"{refine_a_yz:.6f} m", "refine semi-axis Y/Z"],
        ["refine_center", f"{refine_center[0]:.6f},{refine_center[1]:.6f},{refine_center[2]:.6f}", "refine ellipsoid center"],
        ["refine_stl", refine_stl_name, "refine region STL"],
        ["refine_size_level", refine_size_level, "refine ellipsoid level"],
        ["locationinmesh", f"({locationinmesh[0]:.6f}, {locationinmesh[1]:.6f}, {locationinmesh[2]:.6f})", "inside far, outside model"],
    ]
    print(format_table(["Parameter", "Value", "Description"], summary_rows))

    args = {
        "stl_path": stl_path,
        "base_dir": base_dir,
        "base_name": base_name,
        "num_procs": num_procs,

        "xl": xl,
        "yl": yl,
        "zl": zl,
        "cx": cx,
        "cy": cy,
        "cz": cz,

        "max_size": max_size,
        "surf_size": surf_size,
        "min_size": min_size,
        "surf_size_level": surf_size_level,
        "min_size_level": min_size_level,
        "max_level": max_level,
        "feature_level": feature_level,
        "refine_size_level": refine_size_level,

        "h1": h1,
        "growth": growth,
        "layers": layers,

        "model_surface_name": model_surface_name,
        "locationinmesh": locationinmesh,

        "far_ellipsoid": {
            "enabled": True,
            "shape": "axisymmetric_x",
            "dx": far_dx,
            "dy": far_dy,
            "dz": far_dz,
            "a_x": far_a_x,
            "a_yz": far_a_yz,
            "center": far_center,
            "stl": far_stl_name,
            "stl_path": far_stl_path,
            "res_u": far_res_u,
            "res_v": far_res_v,
            "triangles": far_tri,
            "patch_name": "far",
            "patch_type": "patch",
            "boundary_level": [0, 1],
        },

        "refine_ellipsoid": {
            "enabled": True,
            "shape": "axisymmetric_x",
            "refine_dx": refine_dx,
            "refine_dy": refine_dy,
            "refine_dz": refine_dz,
            "a_x": refine_a_x,
            "a_yz": refine_a_yz,
            "center": refine_center,
            "stl": refine_stl_name,
            "stl_path": refine_stl_path,
            "res_u": refine_res_u,
            "res_v": refine_res_v,
            "triangles": refine_tri,
            "region_name": "refine_ellipsoid",
            "mode": "inside",
            "refine_level": refine_size_level,
        },

        "block_box": {
            "dx": block_dx,
            "dy": block_dy,
            "dz": block_dz,
            "margin": margin,
            "min": block_min,
            "max": block_max,
        },

        # Compatibility fields for older snappy scripts/templates.
        "box_dx": block_dx,
        "box_dy": block_dy,
        "box_dz": block_dz,
        "tx": block_min[0],
        "ty": block_min[1],
        "tz": block_min[2],
        "far_box_center": far_center,
        "stl_surface_name": model_surface_name,

        "refine_dx": refine_dx,
        "refine_dy": refine_dy,
        "refine_dz": refine_dz,
        "refine_cx": refine_center[0],
        "refine_cy": refine_center[1],
        "refine_cz": refine_center[2],
        "refine_tx": refine_center[0] - refine_a_x,
        "refine_ty": refine_center[1] - refine_a_yz,
        "refine_tz": refine_center[2] - refine_a_yz,
        "refine_mode": "inside",

        "tip_csv_path": tip_csv_path,
        "tip_points_count": len(tip_points),
        "tip_points": tip_points,
        "tip_wake_lines": tip_wake_lines,
        "tip_wake_refine_size": tip_wake_refine_size,
        "wake_refine_level": (surf_size_level if tip_wake_lines else None),
    }

    with open(args_file, "w") as f:
        json.dump(args, f, indent=2)

    print(f"\n{'=' * 60}")
    print("PARAMETERS CALCULATED")
    print("=" * 60)
    print(f"\n  Args saved to: {os.path.basename(args_file)}")
    print(f"  Far STL: {os.path.basename(far_stl_path)}")
    print(f"  Refine STL: {os.path.basename(refine_stl_path)}")
    print(f"\n  Workflow PAUSED — review JSON and confirm before blockMesh/snappyHexMesh.")
    print("=" * 60)


if __name__ == "__main__":
    main()
