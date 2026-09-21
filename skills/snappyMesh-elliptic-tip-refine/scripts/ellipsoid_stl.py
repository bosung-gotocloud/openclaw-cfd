#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Watertight axisymmetric ellipsoid STL generator for snappyHexMesh elliptic far/refine regions."""

import math
import os
import struct


def _normalize(v):
    x, y, z = v
    norm = math.sqrt(x * x + y * y + z * z)
    if norm == 0.0:
        return (0.0, 0.0, 0.0)
    return (x / norm, y / norm, z / norm)


def _triangle_normal(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    return _normalize(n)


def generate_axisymmetric_ellipsoid_stl(
    center,
    a_x,
    a_yz,
    out_path,
    res_u=128,
    res_v=64,
    binary=True,
):
    """
    Generate a closed/watertight axisymmetric ellipsoid STL.

    The ellipsoid is centered at `center`, elongated along X:
        x semi-axis = a_x
        y/z semi-axis = a_yz

    The pole orientation is chosen so that the mesh is closed:
      +X pole: top fan
      -X pole: bottom fan
      middle: wrapped quadrilateral strips
    """
    if a_x <= 0:
        raise ValueError("a_x must be > 0")
    if a_yz <= 0:
        raise ValueError("a_yz must be > 0")
    if res_u < 3:
        raise ValueError("res_u must be >= 3")
    if res_v < 2:
        raise ValueError("res_v must be >= 2")

    cx, cy, cz = (float(center[0]), float(center[1]), float(center[2]))
    a_x = float(a_x)
    a_yz = float(a_yz)

    triangles = []

    top = (cx + a_x, cy, cz)
    bottom = (cx - a_x, cy, cz)

    rings = []
    for i in range(1, res_v):
        theta = math.pi * i / res_v
        x = cx + a_x * math.cos(theta)
        r = a_yz * math.sin(theta)
        ring = []
        for j in range(res_u):
            phi = 2.0 * math.pi * j / res_u
            ring.append((x, cy + r * math.cos(phi), cz + r * math.sin(phi)))
        rings.append(ring)

    # +X pole fan
    first = rings[0]
    for j in range(res_u):
        p = first[j]
        q = first[(j + 1) % res_u]
        triangles.append((top, p, q))

    # Middle band
    for i in range(len(rings) - 1):
        upper = rings[i]
        lower = rings[i + 1]
        for j in range(res_u):
            p = upper[j]
            q = upper[(j + 1) % res_u]
            r = lower[(j + 1) % res_u]
            s = lower[j]
            triangles.append((p, r, q))
            triangles.append((p, s, r))

    # -X pole fan
    last = rings[-1]
    for j in range(res_u):
        p = last[j]
        q = last[(j + 1) % res_u]
        triangles.append((bottom, q, p))

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if binary:
        with open(out_path, "wb") as f:
            f.write(b"\0" * 80)
            f.write(struct.pack("<I", len(triangles)))
            for a, b, c in triangles:
                n = _triangle_normal(a, b, c)
                f.write(struct.pack("<3f", *n))
                f.write(struct.pack("<3f", *a))
                f.write(struct.pack("<3f", *b))
                f.write(struct.pack("<3f", *c))
                f.write(struct.pack("<H", 0))
    else:
        with open(out_path, "w") as f:
            f.write("solid axisymmetric_ellipsoid\n")
            for a, b, c in triangles:
                n = _triangle_normal(a, b, c)
                f.write("  facet normal %.12e %.12e %.12e\n" % n)
                f.write("    outer loop\n")
                for v in (a, b, c):
                    f.write("      vertex %.12e %.12e %.12e\n" % v)
                f.write("    endloop\n")
                f.write("  endfacet\n")
            f.write("endsolid axisymmetric_ellipsoid\n")

    return len(triangles)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a watertight axisymmetric ellipsoid STL file."
    )
    parser.add_argument("--center", nargs=3, type=float, required=True,
                        help="center x y z")
    parser.add_argument("--a-x", type=float, required=True,
                        help="semi-axis in X direction")
    parser.add_argument("--a-yz", type=float, required=True,
                        help="semi-axis in Y and Z directions")
    parser.add_argument("--out", required=True, help="output STL path")
    parser.add_argument("--res-u", type=int, default=128,
                        help="circumferential resolution (default 128)")
    parser.add_argument("--res-v", type=int, default=64,
                        help="meridional resolution (default 64)")
    parser.add_argument("--ascii", action="store_true",
                        help="write ASCII STL instead of binary STL")
    args = parser.parse_args()

    n_tri = generate_axisymmetric_ellipsoid_stl(
        center=args.center,
        a_x=args.a_x,
        a_yz=args.a_yz,
        out_path=args.out,
        res_u=args.res_u,
        res_v=args.res_v,
        binary=not args.ascii,
    )
    print(f"Wrote {args.out}: {n_tri} triangles")


if __name__ == "__main__":
    main()
