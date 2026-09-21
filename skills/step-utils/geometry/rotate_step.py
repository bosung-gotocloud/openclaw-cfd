#!/usr/bin/env python3
"""
rotate_step.py - Rotate a STEP file around a given axis

Usage:
    python rotate_step.py <input.step> --center cx cy cz --axis ix iy iz --angle theta [--output output.step]

Arguments:
    input.step       STEP file path
    --center         Rotation center (x, y, z) in the STEP's native units
    --axis           Rotation axis vector (i, j, k) — will be normalized
    --angle          Rotation angle in degrees
    --output         Output filename (default: <stepname>_theta.stp)

All coordinates are in the STEP file's native units.
"""

import sys
import os
import argparse
import cadquery as cq


def rotate_step(step_path, center, axis, angle, output_path=None):
    """Rotate a STEP file and save the result."""

    # Import STEP
    print(f"Importing: {step_path}")
    shape = cq.importers.importStep(step_path)

    # Handle Workplane wrapper
    if hasattr(shape, 'val'):
        shape = shape.val()
    elif isinstance(shape, list) and len(shape) == 1:
        shape = shape[0]

    # Rotation center as Vector
    center_vec = cq.Vector(center[0], center[1], center[2])
    # Axis as Vector
    axis_vec = cq.Vector(axis[0], axis[1], axis[2])

    print(f"Rotation center: ({center[0]}, {center[1]}, {center[2]})")
    print(f"Rotation axis:   ({axis[0]}, {axis[1]}, {axis[2]})")
    print(f"Rotation angle:  {angle} deg")

    # Rotate
    rotated = shape.rotate(center_vec, axis_vec, angle)

    # Output path
    if output_path is None:
        output_path = f"{os.path.splitext(os.path.basename(step_path))[0]}_{angle}.stp"

    # Export
    cq.exporters.export(rotated, output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Rotate a STEP file")
    parser.add_argument("input", help="Input STEP file")
    parser.add_argument("--center", type=float, nargs=3, required=True,
                        help="Rotation center (x y z)")
    parser.add_argument("--axis", type=float, nargs=3, required=True,
                        help="Rotation axis vector (i j k)")
    parser.add_argument("--angle", type=float, required=True,
                        help="Rotation angle in degrees")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (default: <stem>_theta.stp)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found")
        sys.exit(1)

    rotate_step(args.input, args.center, args.axis, args.angle, args.output)


if __name__ == "__main__":
    main()
