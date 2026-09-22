#!/usr/bin/env python
"""Geometry: STL → bounding box → far box → face groups → HDF save.
Usage: geometry.py <stl_filename>
"""
import sys
import os
import math

def main():
    if len(sys.argv) < 2:
        print("Usage: geometry.py <stl_filename>")
        sys.exit(1)

    import salome
    import salome_notebook
    import GEOM_Gen
    from salome.geompyBuilder import geompyBuilder

    geom = geompyBuilder(salome.myStudy)
    if geom is None:
        import GEOM
        geom = GEOM.GEOM_Gen.Instantiate(salome.myStudy)

    stl_file = sys.argv[1]
    basename = os.path.splitext(os.path.basename(stl_file))[0]

    # Import STL
    shape = geom.ImportSTL(stl_file)
    geom.addToStudy(shape, f"{basename}_surface")

    # Bounding box
    bb = geom.BoundingBox(shape)
    xl = bb[1] - bb[0]
    yl = bb[3] - bb[2]
    zl = bb[5] - bb[4]
    cx = (bb[0] + bb[1]) / 2
    cy = (bb[2] + bb[3]) / 2
    cz = (bb[4] + bb[5]) / 2

    # Far box
    box_xl = 10 * xl
    box_yl = 5 * yl
    box_zl = 10 * zl

    # Translation: center at (cx - 2.5xl, cy - 2.5yl, cz - 5zl)
    tx = cx - 2.5 * xl
    ty = cy - 2.5 * yl
    tz = cz - 5 * zl

    box = geom.MakeBoxDXDYDZ(box_xl, box_yl, box_zl)
    box_translated = geom.MakeTranslation(box, tx, ty, tz)
    geom.addToStudy(box_translated, "far_box")

    # Boolean cut
    cut_obj = geom.MakeCut(shape, box_translated)
    geom.addToStudy(cut_obj, "domain")

    # Face groups
    faces = geom.CreateGroup("domain", GEOM_Gen.Face)
    geom.addToStudy(faces, "domain_faces")

    # Save
    study_file = f"{basename}_geometry.hdf"
    salome_notebook.notebook.ExportStudy(salome.myStudy, study_file, GEOM_Gen.STudyHDF)
    print(f"Geometry saved: {study_file}")

if __name__ == "__main__":
    main()
