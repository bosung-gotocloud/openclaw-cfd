#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import salome
import GEOM
from salome.geom import geomBuilder

# Initialize GEOM
salome.salome_init()
geompy = geomBuilder.New()

def run_cleaner():
    # 1. Parse Arguments to get STEP path
    step_path = None
    for arg in sys.argv:
        # Handle args:<dir>:<file> or args:<full_path> format
        clean_arg = arg
        if clean_arg.startswith('args:'):
            clean_arg = clean_arg[5:]
        
        if clean_arg.lower().endswith(('.stp', '.step')):
            if ':' in clean_arg:
                directory, filename = clean_arg.split(':', 1)
                step_path = os.path.join(os.path.abspath(directory), filename)
            else:
                step_path = os.path.abspath(clean_arg)
            break

    if not step_path or not os.path.exists(step_path):
        print(f"ERROR: STEP file not found: {step_path}")
        print(f"Usage: aircraft-step-cleaner.py args:<directory>:<file.step>")
        return

    base_dir = os.path.dirname(step_path)
    base_name = os.path.splitext(os.path.basename(step_path))[0]
    output_step = os.path.join(base_dir, f"{base_name}-cleaned.step")
    output_hdf = os.path.join(base_dir, f"{base_name}_debug.hdf")

    # [1] Import STEP
    print("[1] Importing STEP...")
    a01_Original_Aircraft = geompy.ImportSTEP(step_path)

    # [2] Create Cut Box for Left-Half (Y < 0)
    print("[2] Creating Symmetry Cut Box...")
    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(a01_Original_Aircraft)
    dx, dy, dz = (x_max-x_min)*2.0, abs(y_min)*2.0 + 2.0, (z_max-z_min)*2.0

    # Position box to cover the entire Y < 0 space
    box_raw = geompy.MakeBoxDXDYDZ(dx, dy, dz)
    a02_Left_Half_Cut_Box = geompy.MakeTranslation(box_raw, x_min-0.2*dx, -dy, z_min-0.2*dz)

    # [3] Generate the Two Halves
    print("[3] Generating Right and Left halves...")
    a03_Right_Half_Solid = geompy.MakeCut(a01_Original_Aircraft, a02_Left_Half_Cut_Box)

    y_dir = geompy.MakeVectorDXDYDZ(0, 1, 0)
    xz_plane = geompy.MakePlane(geompy.MakeVertex(0, 0, 0), y_dir, 1000)
    a04_Left_Half_Solid = geompy.MakeMirrorByPlane(a03_Right_Half_Solid, xz_plane)

    # [4] Joining halves into a Solid (The GUI Equivalent Logic)
    print("[4] Joining halves into a Manifold Solid...")
    try:
        # Step A: Extract ALL faces
        faces_r = geompy.SubShapeAll(a03_Right_Half_Solid, geompy.ShapeType["FACE"])
        faces_l = geompy.SubShapeAll(a04_Left_Half_Solid, geompy.ShapeType["FACE"])
        all_faces = faces_r + faces_l

        # Step B: Build Solid from Connected Faces (Intersect/Sew = True)
        Cleaned_Symmetrical_Solid = geompy.MakeSolidFromConnectedFaces(all_faces, True)

        # Step C: Volume Validation
        props = geompy.BasicProperties(Cleaned_Symmetrical_Solid)
        volume = props[2]
        if volume > 1e-7:
            print(f" > SUCCESS: Cleaned Solid created. Volume: {volume:.6f}")
        else:
            print(" > WARNING: Result is still a Shell icon (Volume is zero).")

    except Exception as e:
        print(f" > MakeSolidFromConnectedFaces failed: {e}")
        # Final Fallback to Boolean Fuse
        Cleaned_Symmetrical_Solid = geompy.MakeFuse(a03_Right_Half_Solid, a04_Left_Half_Solid)

    # [5] Add to Study and Export
    print("[5] Saving and Exporting...")
    geompy.addToStudy(a01_Original_Aircraft, '01_Original_Aircraft')
    geompy.addToStudy(a02_Left_Half_Cut_Box, '02_Left_Half_Cut_Box')
    geompy.addToStudy(a03_Right_Half_Solid, '03_Right_Half_Solid')
    geompy.addToStudy(a04_Left_Half_Solid, '04_Left_Half_Solid')
    geompy.addToStudy(Cleaned_Symmetrical_Solid, 'Cleaned_Symmetrical_Solid')

    geompy.ExportSTEP(Cleaned_Symmetrical_Solid, output_step, GEOM.LU_METER)

    if salome.myStudy:
        salome.myStudy.SaveAs(output_hdf, False, False)

    print("\n" + "="*60)
    print(f"PROCESS COMPLETE")
    print(f"Cleaned STEP: {output_step}")
    print(f"Debug HDF: {output_hdf}")
    print("="*60)

if __name__ == "__main__":
    run_cleaner()
