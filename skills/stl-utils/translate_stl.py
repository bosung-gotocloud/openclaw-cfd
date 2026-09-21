#!/usr/bin/env python3
"""
translate_stl.py — STL 파일 이동

Usage:
    python translate_stl.py <input.stl> --dx 0.01 --dy -0.05 --dz 0.0

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


def main():
    parser = argparse.ArgumentParser(description='STL translation')
    parser.add_argument('input', help='Input STL file')
    parser.add_argument('--dx', type=float, default=0.0, help='X translation (m)')
    parser.add_argument('--dy', type=float, default=0.0, help='Y translation (m)')
    parser.add_argument('--dz', type=float, default=0.0, help='Z translation (m)')
    parser.add_argument('-d', type=float, nargs=3, metavar=('DX', 'DY', 'DZ'), help='Translation (alias)')
    parser.add_argument('--output', default=None, help='Output file (auto-generated if omitted)')
    parser.add_argument('--unit', choices=['mm', 'm'], default='mm', help='Input unit (default: mm)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    mesh = load_stl(args.input, unit=args.unit)

    if args.d is not None:
        dx, dy, dz = args.d
    else:
        dx, dy, dz = args.dx, args.dy, args.dz

    mesh.vertices += np.array([dx, dy, dz])

    if args.output is None:
        base = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"{base}_{dx:.4f}_{dy:.4f}_{dz:.4f}.stl"

    print(f"{'='*60}")
    print(f"STL Translation")
    print(f"{'='*60}")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Offset: ({dx:.6f}, {dy:.6f}, {dz:.6f}) m")
    print(f"{'='*60}")

    mesh.export(args.output)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
