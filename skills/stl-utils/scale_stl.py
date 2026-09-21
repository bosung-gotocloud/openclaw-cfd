#!/usr/bin/env python3
"""
scale_stl.py — STL 파일 스케일 변환 (기하 중심 기준)

Usage:
    python scale_stl.py <input.stl> --uniform 2.0
    python scale_stl.py <input.stl> --scale 1.0 2.0 1.5
    python scale_stl.py <input.stl> -s 1.0 2.0 1.5

Dependencies:
    pip install trimesh
"""

import sys
import os
import numpy as np
import argparse

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh가 설치되어 있지 않습니다.")
    print("pip install trimesh")
    sys.exit(1)


def load_stl(path, unit='mm'):
    """Load STL and convert to meters internally."""
    mesh = trimesh.load(path)
    if not isinstance(mesh, trimesh.Trimesh):
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

    if unit == 'mm':
        mesh.vertices *= 0.001
    return mesh


def scale_uniform(mesh, factor):
    """Uniform scale around centroid."""
    centroid = mesh.centroid
    mesh.vertices -= centroid
    mesh.vertices *= factor
    mesh.vertices += centroid
    return mesh


def scale_nonuniform(mesh, sx, sy, sz):
    """Non-uniform scale around centroid."""
    centroid = mesh.centroid
    mesh.vertices -= centroid
    mesh.vertices[:, 0] *= sx
    mesh.vertices[:, 1] *= sy
    mesh.vertices[:, 2] *= sz
    mesh.vertices += centroid
    return mesh


def main():
    parser = argparse.ArgumentParser(description='STL scale transformation')
    parser.add_argument('input', help='Input STL file')
    parser.add_argument('--uniform', type=float, default=None, help='Uniform scale factor')
    parser.add_argument('--scale', type=float, nargs=3, metavar=('A', 'B', 'C'), help='X Y Z scale')
    parser.add_argument('-s', type=float, nargs=3, metavar=('A', 'B', 'C'), help='X Y Z scale (alias)')
    parser.add_argument('--output', default=None, help='Output file (auto-generated if omitted)')
    parser.add_argument('--unit', choices=['mm', 'm'], default='mm', help='Input unit (default: mm)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    if args.uniform is None and args.scale is None and args.s is None:
        print("Error: --uniform or --scale is required")
        sys.exit(1)

    mesh = load_stl(args.input, unit=args.unit)
    original_area = mesh.area
    original_volume = mesh.volume

    if args.uniform is not None:
        mesh = scale_uniform(mesh, args.uniform)
        if args.output is None:
            base = os.path.splitext(os.path.basename(args.input))[0]
            args.output = f"{base}_{args.uniform}.stl"
    else:
        sx, sy, sz = args.scale if args.scale else args.s
        mesh = scale_nonuniform(mesh, sx, sy, sz)
        if args.output is None:
            base = os.path.splitext(os.path.basename(args.input))[0]
            args.output = f"{base}_{sx}_{sy}_{sz}.stl"

    new_area = mesh.area
    new_volume = mesh.volume

    print(f"{'='*60}")
    print(f"STL Scale Transformation")
    print(f"{'='*60}")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Original area: {original_area:.6f} m²")
    print(f"New area:      {new_area:.6f} m²")
    print(f"Original volume: {original_volume:.6f} m³")
    print(f"New volume:      {new_volume:.6f} m³")
    print(f"{'='*60}")

    mesh.export(args.output)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
