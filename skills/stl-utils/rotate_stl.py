#!/usr/bin/env python3
"""
rotate_stl.py — STL 파일 회전 (축-각 방식)

Usage:
    python rotate_stl.py <input.stl> --center 0 0 0 --axis 0 0 1 --angle 45

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


def rotate_mesh(mesh, center, axis, angle_deg):
    """Rotate mesh around arbitrary axis through center point."""
    # Normalize axis
    axis = np.array(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)

    # Convert to trimesh Rotation
    rot = trimesh.transformations.rotation_matrix(
        np.radians(angle_deg), axis, point=center
    )

    # Apply transformation
    mesh.apply_transform(rot)
    return mesh


def main():
    parser = argparse.ArgumentParser(description='STL rotation')
    parser.add_argument('input', help='Input STL file')
    parser.add_argument('--center', type=float, nargs=3, default=[0, 0, 0],
                        metavar=('X', 'Y', 'Z'), help='Rotation center (m)')
    parser.add_argument('--axis', type=float, nargs=3, default=[0, 0, 1],
                        metavar=('I', 'J', 'K'), help='Rotation axis (auto-normalized)')
    parser.add_argument('--angle', type=float, required=True, help='Rotation angle (degrees)')
    parser.add_argument('--output', default=None, help='Output file (auto-generated if omitted)')
    parser.add_argument('--unit', choices=['mm', 'm'], default='mm', help='Input unit (default: mm)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    mesh = load_stl(args.input, unit=args.unit)
    center = np.array(args.center)
    axis = np.array(args.axis)

    mesh = rotate_mesh(mesh, center, axis, args.angle)

    if args.output is None:
        base = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"{base}_{args.angle:.1f}.stl"

    print(f"{'='*60}")
    print(f"STL Rotation")
    print(f"{'='*60}")
    print(f"Input:    {args.input}")
    print(f"Output:   {args.output}")
    print(f"Center:   ({center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f}) m")
    print(f"Axis:     ({axis[0]:.6f}, {axis[1]:.6f}, {axis[2]:.6f})")
    print(f"Angle:    {args.angle:.1f}°")
    print(f"{'='*60}")

    mesh.export(args.output)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
