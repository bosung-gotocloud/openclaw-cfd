#!/usr/bin/env python3
"""
scale_step.py - Scale a STEP file relative to its geometric center

Usage:
    # Uniform scale (n times in all directions)
    python scale_step.py <input.step> --uniform n [--output output.step]

    # Non-uniform scale (a, b, c times in X, Y, Z respectively)
    python scale_step.py <input.step> --scale a b c [--output output.step]

Arguments:
    input.step       STEP file path
    --uniform n      Scale factor for all directions (e.g., 2.0 = double size)
    --scale a b c    Scale factors for X, Y, Z directions respectively
    --output         Output filename
                     Uniform:   default <stepname>_n.stp
                     Non-uniform: default <stepname>_a_b_c.step

Scale is applied relative to the STEP's geometric center (centroid).
"""

import sys
import os
import argparse
import cadquery as cq


def scale_step(step_path, sx, sy, sz, output_path=None):
    """Scale a STEP file relative to its centroid and save."""

    # Import STEP
    print(f"Importing: {step_path}")
    shape = cq.importers.importStep(step_path)

    # Handle Workplane wrapper
    if hasattr(shape, 'val'):
        shape = shape.val()
    elif isinstance(shape, list) and len(shape) == 1:
        shape = shape[0]

    # Geometric center (centroid) as scale origin
    centroid = shape.Center()
    print(f"Geometric center: ({centroid.x:.6f}, {centroid.y:.6f}, {centroid.z:.6f})")
    print(f"Scale factors:    X={sx}, Y={sy}, Z={sz}")

    # cadquery's scale(): scale around the shape's centroid by default
    # But to be explicit, translate to origin → scale → translate back
    center_vec = cq.Vector(centroid.x, centroid.y, centroid.z)

    scaled = (shape
              .translate(-center_vec)       # move centroid to origin
              .scale(sx, sy, sz)           # scale relative to origin
              .translate(center_vec))      # move back

    # Determine output filename
    if output_path is None:
        stepname = os.path.splitext(os.path.basename(step_path))[0]
        if abs(sx - sy) < 1e-9 and abs(sy - sz) < 1e-9:
            # Uniform scale
            output_path = f"{stepname}_{sx}.stp"
        else:
            output_path = f"{stepname}_{sx}_{sy}_{sz}.step"

    # Export
    cq.exporters.export(scaled, output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Scale a STEP file relative to its centroid")
    parser.add_argument("input", help="Input STEP file")
    parser.add_argument("--uniform", type=float, default=None,
                        help="Uniform scale factor (all directions)")
    parser.add_argument("--scale", type=float, nargs=3, default=None,
                        help="Scale factors for X, Y, Z")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename")

    args = parser.parse_args()

    if args.uniform is None and args.scale is None:
        print("Error: Must specify --uniform or --scale")
        sys.exit(1)

    if args.uniform is not None and args.scale is not None:
        print("Error: Cannot use both --uniform and --scale")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found")
        sys.exit(1)

    if args.uniform is not None:
        scale_step(args.input, args.uniform, args.uniform, args.uniform, args.output)
    else:
        scale_step(args.input, args.scale[0], args.scale[1], args.scale[2], args.output)


if __name__ == "__main__":
    main()
