#!/usr/bin/env python3
"""
step_analyzer.py - Analyze geometric properties of STEP files

Usage:
    python step_analyzer.py <input.step> [output.json]

All outputs are in SI units (m, m²).
If the STEP file uses mm, values are automatically converted to m.

Output JSON contains:
- bounding_box: {xmin, xmax, ymin, ymax, zmin, zmax, xl, yl, zl}  [m]
- areas: {total_surface, Axz, Axy, Ayz}  [m²]
- center_of_gravity: {cgx, cgy, cgz}  [m]
"""

import sys
import os
import re
import json
import numpy as np
import cadquery as cq
from shapely.geometry import Polygon
from shapely.ops import unary_union


def detect_step_unit(step_path):
    """Detect the length unit of a STEP file by parsing its header.

    Returns scale factor to convert to metres.
    - '.METRE.' → 1.0
    - '.MILLI.*METRE.' or '.MM.' → 0.001
    - Default (no unit found) → 0.001 (ASSUME mm per STEP convention)
    """
    try:
        with open(step_path, 'r', encoding='utf-8', errors='ignore') as f:
            header = f.read(8192).upper()
    except Exception:
        return 0.001

    if '.METRE.' in header:
        return 1.0
    if '.MILLI' in header or '.MM.' in header:
        return 0.001

    # No explicit unit found — STEP default convention is mm
    return 0.001


def compute_projection_area(shape):
    """Compute true projected area by tessellating the shape,
    projecting each triangle onto the target plane,
    and merging overlapping projections via unary_union.

    Returns dict with keys XY, XZ, YZ (projected areas in m²)."""
    # Tessellate to get triangular faces
    vertices, face_indices = shape.tessellate(tolerance=1e-4, angularTolerance=2)
    verts_arr = np.array([[v.x, v.y, v.z] for v in vertices], dtype=float)

    # Projection planes: (label, view_direction_normal)
    normals = {"XY": [0, 0, 1], "XZ": [0, 1, 0], "YZ": [1, 0, 0]}
    areas = {}

    for label, normal in normals.items():
        n = np.array(normal, dtype=float)
        # Build orthonormal basis (u, v) perpendicular to n
        if abs(n[0]) < 0.9:
            u = np.cross(n, [1, 0, 0])
        else:
            u = np.cross(n, [0, 1, 0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        v /= np.linalg.norm(v)

        polys = []
        for fi in face_indices:
            tri = verts_arr[list(fi)]
            # Project 3D vertices to 2D (u,v) coordinates
            pts2d = [(tri[0] @ u, tri[0] @ v),
                     (tri[1] @ u, tri[1] @ v),
                     (tri[2] @ u, tri[2] @ v)]
            try:
                poly = Polygon(pts2d)
                if poly.is_valid and poly.area > 1e-15:
                    polys.append(poly)
            except Exception:
                continue

        if polys:
            merged = unary_union(polys)
            areas[label] = merged.area if hasattr(merged, "area") else 0.0
        else:
            areas[label] = 0.0

    return areas

def analyze_step(step_path, output_path=None):
    """Analyze STEP file and extract geometric properties."""
    
    # Import STEP file
    print(f"Importing STEP file: {step_path}")
    shape = cq.importers.importStep(step_path)

    # Handle Workplane wrapper (cadquery may return Workplane instead of raw Shape)
    if hasattr(shape, 'val'):
        shape = shape.val()
    elif isinstance(shape, list) and len(shape) == 1:
        shape = shape[0]
    
    # Detect STEP unit and convert to metres
    scale = detect_step_unit(step_path)
    unit_label = 'm' if scale == 1.0 else 'mm → m'
    print(f"Detected unit: {unit_label} (scale={scale})")

    # Get bounding box
    bbox = shape.BoundingBox()
    xmin, ymin, zmin = bbox.xmin * scale, bbox.ymin * scale, bbox.zmin * scale
    xmax, ymax, zmax = bbox.xmax * scale, bbox.ymax * scale, bbox.zmax * scale
    xl = xmax - xmin
    yl = ymax - ymin
    zl = zmax - zmin
    
    print(f"Bounding box [m]:")
    print(f"  X: [{xmin:.6f}, {xmax:.6f}] (length: {xl:.6f})")
    print(f"  Y: [{ymin:.6f}, {ymax:.6f}] (length: {yl:.6f})")
    print(f"  Z: [{zmin:.6f}, {zmax:.6f}] (length: {zl:.6f})")
    
    # Calculate areas
    total_surface = shape.Area() * (scale ** 2)  # m²

    # True projection areas: tessellate → project triangles → unary_union merge
    proj = compute_projection_area(shape)
    Axz = proj["XZ"] * (scale ** 2)  # XZ plane projection (viewed from Y-axis) [m²]
    Axy = proj["XY"] * (scale ** 2)  # XY plane projection (viewed from Z-axis) [m²]
    Ayz = proj["YZ"] * (scale ** 2)  # YZ plane projection (viewed from X-axis) [m²]

    print(f"\nSurface areas [m²]:")
    print(f"  Total surface area: {total_surface:.6f}")
    print(f"  Axz (XZ projection): {Axz:.6f}")
    print(f"  Axy (XY projection): {Axy:.6f}")
    print(f"  Ayz (YZ projection): {Ayz:.6f}")
    
    # Calculate center of gravity (assuming uniform density)
    centroid = shape.Center()
    cgx, cgy, cgz = centroid.x * scale, centroid.y * scale, centroid.z * scale

    print(f"\nCenter of gravity [m]:")
    print(f"  CG: ({cgx:.6f}, {cgy:.6f}, {cgz:.6f})")
    
    # Create output dictionary
    result = {
        "file": os.path.basename(step_path),
        "bounding_box": {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "zmin": zmin,
            "zmax": zmax,
            "xl": xl,
            "yl": yl,
            "zl": zl
        },
        "areas": {
            "total_surface": total_surface,
            "Axz": Axz,
            "Axy": Axy,
            "Ayz": Ayz
        },
        "center_of_gravity": {
            "cgx": cgx,
            "cgy": cgy,
            "cgz": cgz
        }
    }
    
    # Save to JSON file
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(step_path))[0]
        output_path = f"{base_name}.json"
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python step_analyzer.py <input.step> [output.json]")
        sys.exit(1)
    
    step_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(step_path):
        print(f"Error: File '{step_path}' not found")
        sys.exit(1)
    
    analyze_step(step_path, output_path)

if __name__ == "__main__":
    main()
