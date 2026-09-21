#!/usr/bin/env python3
"""
translate_step.py - Translate (move) a STEP file by a given offset

Usage:
    python translate_step.py <input.step> --dx a --dy b --dz c [--output output.step]

Arguments:
    input.step       STEP file path
    --dx             Translation in X direction (native units)
    --dy             Translation in Y direction (native units)
    --dz             Translation in Z direction (native units)
    --output         Output filename (default: <stepname>_a_b_c.step)

All coordinates are in the STEP file's native units.
"""

import sys
import os
import argparse
import cadquery as cq


def translate_step(step_path, dx, dy, dz, output_path=None):
    """Translate a STEP file and save the result."""

    # Import STEP
    print(f"Importing: {step_path}")
    shape = cq.importers.importStep(step_path)

    # Handle Workplane wrapper
    if hasattr(shape, 'val'):
        shape = shape.val()
    elif isinstance(shape, list) and len(shape) == 1:
        shape = shape[0]

    print(f"Translation: ({dx}, {dy}, {dz})")

    # Translate
    translated = shape.translate(cq.Vector(dx, dy, dz))

    # Output path
    if output_path is None:
        stepname = os.path.splitext(os.path.basename(step_path))[0]
        output_path = f"{stepname}_{dx}_{dy}_{dz}.step"

    # Export
    cq.exporters.export(translated, output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Translate a STEP file")
    parser.add_argument("input", help="Input STEP file")
    parser.add_argument("--dx", type=float, required=True, help="X translation")
    parser.add_argument("--dy", type=float, required=True, help="Y translation")
    parser.add_argument("--dz", type=float, required=True, help="Z translation")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (default: <stem>_a_b_c.step)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found")
        sys.exit(1)

    translate_step(args.input, args.dx, args.dy, args.dz, args.output)


if __name__ == "__main__":
    main()
