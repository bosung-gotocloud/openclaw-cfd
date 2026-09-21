#!/usr/bin/env python3
"""
analyze_stl.py — STL 파일의 기하 분석 (BBox, 표면적, 투영면적, 무게중심)

Dependencies:
    pip install trimesh numpy shapely
"""

import sys
import os
import json
import numpy as np
import argparse

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh가 설치되어 있지 않습니다.")
    print("pip install trimesh")
    sys.exit(1)

try:
    import shapely.geometry as sg
except ImportError:
    print("WARNING: shapely가 없습니다. 투영면적이 계산되지 않습니다.")


def analyze_stl(path, unit='mm'):
    """STL 파일 분석."""
    # Load
    mesh = trimesh.load(path)
    if not isinstance(mesh, trimesh.Trimesh):
        # Try to extract first mesh from scene
        if isinstance(mesh, trimesh.Scene):
            meshes = list(mesh.dump())
            if meshes:
                mesh = trimesh.util.concatenate(meshes)
            else:
                print("Error: No mesh data found.")
                sys.exit(1)
        else:
            print(f"Error: Cannot load {path}")
            sys.exit(1)

    # Unit conversion
    if unit == 'mm':
        scale_factor = 0.001
    else:
        scale_factor = 1.0

    # Vertices in meters
    verts_m = mesh.vertices * scale_factor

    # BBox (SI: m)
    mins = verts_m.min(axis=0)
    maxs = verts_m.max(axis=0)
    extents = maxs - mins

    # Total surface area (SI: m²)
    total_area = mesh.area * (scale_factor ** 2)

    # Projection areas (SI: m²)
    proj_areas = compute_projection_areas(mesh, scale_factor)

    # Center of gravity (SI: m)
    cg = verts_m.mean(axis=0)

    result = {
        'file': os.path.basename(path),
        'bounding_box': {
            'xmin': round(float(mins[0]), 6),
            'xmax': round(float(maxs[0]), 6),
            'ymin': round(float(mins[1]), 6),
            'ymax': round(float(maxs[1]), 6),
            'zmin': round(float(mins[2]), 6),
            'zmax': round(float(maxs[2]), 6),
            'xl': round(float(extents[0]), 6),
            'yl': round(float(extents[1]), 6),
            'zl': round(float(extents[2]), 6),
        },
        'mesh_stats': {
            'vertex_count': len(mesh.vertices),
            'face_count': len(mesh.faces),
        },
        'areas': {
            'total_surface': round(float(total_area), 6),
            'Axz': round(float(proj_areas.get('xz', 0.0)), 6),
            'Axy': round(float(proj_areas.get('xy', 0.0)), 6),
            'Ayz': round(float(proj_areas.get('yz', 0.0)), 6),
        },
        'center_of_gravity': {
            'cgx': round(float(cg[0]), 6),
            'cgy': round(float(cg[1]), 6),
            'cgz': round(float(cg[2]), 6),
        }
    }

    return result


def compute_projection_areas(mesh, scale_factor):
    """XY/XZ/YZ 투영면적 계산 (true mesh projection)."""
    areas = {}

    # Face normals and areas for efficient projection
    face_normals = mesh.face_normals  # (n, 3)
    face_areas = mesh.face_area  # (n,)

    projections = {
        'xy': (0, 1),  # project along Z
        'xz': (0, 2),  # project along Y
        'yz': (1, 2),  # project along X
    }

    for name, (ax1, ax2) in projections.items():
        # Projected area = sum of |normal_k| * area for each face
        # where k is the axis we're projecting along (the one NOT in ax1, ax2)
        if name == 'xy':
            k = 2  # Z axis
        elif name == 'xz':
            k = 1  # Y axis
        else:
            k = 0  # X axis

        # Projected area = sum(|n_k| * face_area / |n_k| * |n_k|) = sum(|n_k| * area)
        # when normal is normalized, |n_k| = abs(normal component on k axis)
        projected = np.sum(np.abs(face_normals[:, k]) * face_areas) * (scale_factor ** 2)
        areas[name] = projected

    return areas


def main():
    parser = argparse.ArgumentParser(description='STL geometry analysis')
    parser.add_argument('input', help='Input STL file')
    parser.add_argument('output', nargs='?', default=None, help='Output JSON path')
    parser.add_argument('--unit', choices=['mm', 'm'], default='mm', help='Input unit (default: mm)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"STL Geometry Analysis")
    print(f"{'='*60}")
    print(f"File: {args.input}")
    print(f"Unit: {args.unit}")
    print(f"{'='*60}")

    result = analyze_stl(args.input, unit=args.unit)

    # Print results
    bb = result['bounding_box']
    print(f"\n[BBox (m)]")
    print(f"  X: [{bb['xmin']:.6f}, {bb['xmax']:.6f}]  span: {bb['xl']:.6f}")
    print(f"  Y: [{bb['ymin']:.6f}, {bb['ymax']:.6f}]  span: {bb['yl']:.6f}")
    print(f"  Z: [{bb['zmin']:.6f}, {bb['zmax']:.6f}]  span: {bb['zl']:.6f}")

    ms = result['mesh_stats']
    print(f"\n[Mesh Stats]")
    print(f"  Vertices: {ms['vertex_count']}, Faces: {ms['face_count']}")

    areas = result['areas']
    print(f"\n[Areas (m²)]")
    print(f"  Total: {areas['total_surface']:.6f}")
    print(f"  Axz: {areas['Axz']:.6f}, Axy: {areas['Axy']:.6f}, Ayz: {areas['Ayz']:.6f}")

    cg = result['center_of_gravity']
    print(f"\n[Center of Gravity (m)]")
    print(f"  ({cg['cgx']:.6f}, {cg['cgy']:.6f}, {cg['cgz']:.6f})")

    # Output JSON
    csv_path = args.output or f"{os.path.splitext(args.input)[0]}_analysis.json"
    with open(csv_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n[Output] JSON: {csv_path}")

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
