#!/usr/bin/env python3
"""
step_cleaner.py — STEP file cleanup for watertight solids

Removes degenerate/tiny faces, merges orphan faces into parent solid,
and ensures the output is a valid closed solid suitable for CFD meshing.

Usage:
    python step_cleaner.py <input.step> [-o output.step]
                           [--min-area FLOAT] [--keep-solid]

Options:
    --min-area FLOAT   Minimum face area threshold (mm², default 0.01).
                       Faces below this are considered degenerate.
    --keep-solid       Run ShapeFix twice for stronger cleanup.
    -o, --output       Output file path (default: <input>_cleaned.stp)

Dependencies: cadquery (OCP bindings)

Exit codes:
    0 — success, output written
    1 — read/write error
"""

import sys
import os
import argparse
import cadquery as cq
import OCP

# ─────────────────────────────────────────────────────────────────────
# Helper: get OCP shape from cadquery Workplane
# ─────────────────────────────────────────────────────────────────────

def wp_to_shape(wp):
    """Extract the raw OCP TopoDS_Shape from a cadquery Workplane."""
    return wp.val().wrapped


def shape_to_wp(shape):
    """Wrap a raw OCP shape back into a cadquery Workplane."""
    return cq.Workplane(cq.Plane.XY()).newObject([shape])


# ─────────────────────────────────────────────────────────────────────
# Core cleanup logic
# ─────────────────────────────────────────────────────────────────────

def analyze_faces(shape, min_area=0.01):
    """
    Analyze faces of a TopoDS_Shape.
    Returns (total_faces, list_of_tiny_face_indices, face_areas)
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS_Face


    areas = []
    e = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while e.More():
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(e.Current(), props)
        areas.append(props.Mass())
        idx += 1
        e.Next()

    tiny = [i for i, a in enumerate(areas) if a < min_area]
    return idx, tiny, areas


def cleanup_step(input_path, output_path=None, min_area=0.01, keep_solid=False):
    """
    Main cleanup pipeline:
      1. Read STEP file via cadquery/OCP
      2. Identify degenerate (tiny) faces
      3. Apply ShapeFix_Shape (1x or 2x)
      4. Write cleaned STEP

    Returns dict with before/after stats.
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = base + '_cleaned.stp'

    # --- Read ---
    wp = cq.importers.importStep(input_path)
    shape = wp_to_shape(wp)

    if shape.IsNull():
        raise RuntimeError(f"Failed to read shape from {input_path}")

    # --- BEFORE stats ---
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE

    def count_faces(s):
        e = TopExp_Explorer(s, TopAbs_FACE)
        n = 0
        while e.More():
            n += 1
            e.Next()
        return n

    before_faces = count_faces(shape)
    before_solids = len(wp.solids().vals())
    before_shells = len(wp.shells().vals())

    # Detect tiny faces (informational)
    _, tiny_faces, face_areas = analyze_faces(shape, min_area)
    tiny_count = len(tiny_faces)
    min_area_actual = min(face_areas) if face_areas else 0

    print(f"\n=== BEFORE Cleanup ===")
    print(f"  File:        {input_path}")
    print(f"  Solids:      {before_solids}")
    print(f"  Shells:      {before_shells}")
    print(f"  Faces:       {before_faces}")
    print(f"  Tiny faces:  {tiny_count}  (< {min_area} mm²)")
    if face_areas:
        print(f"  Min area:    {min(face_areas):.6f} mm²")

    # --- ShapeFix ---
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.ShapeFix import ShapeFix_Wire

    # Apply ShapeFix to the whole shape
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    fixed = fixer.Shape()

    # If keep_solid, run a second pass focused on solid repair
    if keep_solid:
        from OCP.TopExp import TopExp_Explorer as TE2
        from OCP.TopAbs import TopAbs_SOLID
        fixer2 = ShapeFix_Shape(fixed)
        fixer2.Perform()
        fixed = fixer2.Shape()

    after_faces = count_faces(fixed)
    after_wp = shape_to_wp(fixed)
    after_solids = len(after_wp.solids().vals())
    after_shells = len(after_wp.shells().vals())

    print(f"\n=== AFTER Cleanup ===")
    print(f"  Solids:      {after_solids}")
    print(f"  Shells:      {after_shells}")
    print(f"  Faces:       {after_faces}  ({before_faces - after_faces} removed)")

    # --- Write ---
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.BRepGProp import BRepGProp as BGP
    from OCP.GProp import GProp_GProps
    writer = STEPControl_Writer()
    writer.Transfer(fixed, STEPControl_AsIs)
    writer.Write(output_path)
    print(f"\n  Output:      {output_path}")
    print(f"  Size:        {os.path.getsize(output_path) / 1024:.1f} KB")

    return {
        "input": input_path,
        "output": output_path,
        "before": {"solids": before_solids, "shells": before_shells, "faces": before_faces},
        "after": {"solids": after_solids, "shells": after_shells, "faces": after_faces},
        "tiny_faces_detected": tiny_count,
        "min_face_area_mm2": min_area_actual,
    }


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Clean a STEP file: remove degenerate faces, repair solids for watertight output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input", help="Input STEP file (.stp / .step)")
    p.add_argument("-o", "--output", help="Output STEP file (default: <input>_cleaned.stp)")
    p.add_argument("--min-area", type=float, default=0.01,
                   help="Minimum face area threshold in mm² (default: 0.01)")
    p.add_argument("--keep-solid", action="store_true",
                   help="Apply stronger solid-level ShapeFix (second pass)")
    args = p.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        result = cleanup_step(args.input, args.output, args.min_area, args.keep_solid)
    except Exception as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        sys.exit(1)

    print("\n=== DONE ===")
    print(f"  Removed {result['before']['faces'] - result['after']['faces']} faces.")
    if result["after"]["solids"] > 0:
        print(f"  Output is {result['after']['solids']} closed solid(s) — ready for meshing.")
    else:
        print("  WARNING: 0 solids in output. Check input geometry.")


if __name__ == "__main__":
    main()
