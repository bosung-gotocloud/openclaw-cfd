#!/usr/bin/env python3
"""
Rotate an STL file around a point by a given angle.

Usage:
    python rotate.py <stlfile.stl> <x> <y> <z> <i> <j> <k> <degree>

Example:
    python rotate.py model.stl 0.0 0.0 0.0 1.0 0.0 0.0 45
    -> model_45.stl

Rotates <stlfile.stl> around the center point (x, y, z)
by <degree> degrees around the axis (i, j, k),
and saves as <stlfile>_degree.stl.
"""

import sys
import numpy as np
import trimesh


def rotation_matrix(axis, angle_deg):
    """Create a 3x3 rotation matrix for rotation around axis by angle (degrees)."""
    axis = np.array(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    c = np.cos(np.radians(angle_deg))
    s = np.sin(np.radians(angle_deg))
    t = 1 - c
    x, y, z = axis

    return np.array([
        [t*x*x + c,     t*x*y - z*s,  t*x*z + y*s],
        [t*x*y + z*s,   t*y*y + c,    t*y*z - x*s],
        [t*x*z - y*s,   t*y*z + x*s,  t*z*z + c]
    ])


def main():
    if len(sys.argv) != 9:
        print("Usage: python rotate.py <stlfile.stl> <x> <y> <z> <i> <j> <k> <degree>")
        print("  (x,y,z) = rotation center, (i,j,k) = rotation axis, degree = rotation angle")
        sys.exit(1)

    stl_file = sys.argv[1]
    cx, cy, cz = map(float, sys.argv[2:5])
    ix, iy, iz = map(float, sys.argv[5:8])
    angle = float(sys.argv[8])

    # Read STL
    mesh = trimesh.load(stl_file, process=False)

    # Rotation matrix around (i, j, k)
    R = rotation_matrix((ix, iy, iz), angle)

    # Rotate vertices around center point
    vertices = mesh.vertices.copy()
    vertices_centered = vertices - np.array([cx, cy, cz])
    vertices_rotated = vertices_centered @ R.T
    mesh.vertices = vertices_rotated + np.array([cx, cy, cz])

    # Output filename
    base, ext = stl_file.rsplit('.', 1)
    out_file = f"{base}_{angle}.{ext}"

    # Export as ASCII STL
    with open(out_file, 'w') as f:
        f.write(f'solid rotated\n')
        for i in range(len(mesh.faces)):
            f0, f1, f2 = mesh.faces[i]
            v0, v1, v2 = mesh.vertices[f0], mesh.vertices[f1], mesh.vertices[f2]
            # Compute face normal
            e1 = v1 - v0
            e2 = v2 - v0
            n = np.cross(e1, e2)
            nl = np.linalg.norm(n)
            if nl > 0:
                n /= nl
            f.write(f'  facet normal {n[0]:.10e} {n[1]:.10e} {n[2]:.10e}\n')
            f.write(f'    outer loop\n')
            f.write(f'      vertex {v0[0]:.10e} {v0[1]:.10e} {v0[2]:.10e}\n')
            f.write(f'      vertex {v1[0]:.10e} {v1[1]:.10e} {v1[2]:.10e}\n')
            f.write(f'      vertex {v2[0]:.10e} {v2[1]:.10e} {v2[2]:.10e}\n')
            f.write(f'    endloop\n')
            f.write(f'  endfacet\n')
        f.write(f'endsolid rotated\n')
    print(f"Saved: {out_file}")
    print(f"  Center: ({cx}, {cy}, {cz})")
    print(f"  Axis:   ({ix}, {iy}, {iz})")
    print(f"  Angle:  {angle}°")


if __name__ == "__main__":
    main()
