#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 2: Compute mesh for snappyHexMesh workflow.
Rebuilds geometry fresh from STEP file, computes mesh WITHOUT viscous layers.
Exports OpenFOAM case with surface STL for snappyHexMesh layer addition.
Adds refineBox volumetric refinement in SALOME using Netgen local size.
Uses parallel snappyHexMesh via mpirun (decomposePar + reconstructParMesh).
"""

import sys
import os
import json
import math
import time
import shutil
import threading
import glob as glob_mod
import salome
import GEOM
import SMESH
from salome.geom import geomBuilder
from salome.smesh import smeshBuilder

# Write to both console and log file
class TeeOutput:
    def __init__(self, log_path):
        self.log_file = open(log_path, 'w')
        self.log_name = os.path.basename(log_path)
    def write(self, data):
        try:
            sys.__stdout__.write(data)
        except:
            pass
        try:
            self.log_file.write(data)
            self.log_file.flush()
        except:
            pass
    def flush(self):
        try:
            self.log_file.flush()
        except:
            pass

_script_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
_log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), f"{_script_name}.log")
sys.stdout = TeeOutput(_log_file)

# Initialize
salome.salome_init()
geompy = geomBuilder.New()
smesh = smeshBuilder.New()

def format_table(headers, rows):
    """Format data as ASCII table"""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    lines = []
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(f" {h:^{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
    lines.append(separator)
    lines.append(header_line)
    lines.append(separator)
    for row in rows:
        row_line = "|" + "|".join(f" {str(cell):<{col_widths[i]}} " for i, cell in enumerate(row)) + "|"
        lines.append(row_line)
    lines.append(separator)
    return "\n".join(lines)

# ==============================================================================
# MESH EXPORT HELPER FUNCTIONS
# ==============================================================================

class MeshBuffer(object):
    def __init__(self, mesh, v):
        i = 0
        faces, keys = list(), list()
        fnodes = mesh.GetElemFaceNodes(v, i)
        while fnodes:
            faces.append(fnodes)
            keys.append(tuple(sorted(fnodes)))
            i += 1
            fnodes = mesh.GetElemFaceNodes(v, i)
        self.v, self.faces, self.keys, self.fL = v, faces, keys, i
    @staticmethod
    def Key(fnodes): return tuple(sorted(fnodes))

def exportToFoam(mesh, dirname, base_name):
    if not os.path.exists(dirname): os.makedirs(dirname)
    volumes = mesh.GetElementsByType(SMESH.VOLUME)
    smesh_int = smeshBuilder.New()
    filter_free = smesh_int.GetFilter(SMESH.EDGE, SMESH.FT_FreeFaces)
    extFaces = set(mesh.GetIdsFromFilter(filter_free))
    buffers = [MeshBuffer(mesh, v) for v in volumes]
    nrExtFaces = len(extFaces)
    nrFaces = int((sum(b.fL for b in buffers) + nrExtFaces) / 2)
    nrIntFaces = nrFaces - nrExtFaces

    faces, facesSorted = [], {}
    bcFaces, bcFacesSorted = [], {}
    grpStartFace, grpNrFaces, grpNames = [], [], []
    volumeGroups = []
    ofbcfid = 0

    for gr in mesh.GetGroups():
        g_type = gr.GetType()
        if g_type == SMESH.FACE:
            grpNames.append(gr.GetName())
            grIds = gr.GetIDs()
            grpStartFace.append(nrIntFaces + ofbcfid)
            grpNrFaces.append(len(grIds))
            for sfid in grIds:
                fnodes = mesh.GetElemNodes(sfid)
                key = MeshBuffer.Key(fnodes)
                bcFaces.append(fnodes)
                bcFacesSorted[key] = ofbcfid
                ofbcfid += 1
        elif g_type == SMESH.VOLUME:
            volumeGroups.append(gr)

    owner, neighbour = [-1] * nrFaces, [-1] * nrIntFaces
    offid, ofvid = 0, 0
    for b in buffers:
        for fi in range(b.fL):
            fnodes, key = b.faces[fi], b.keys[fi]
            if key in facesSorted:
                neighbour[facesSorted[key]] = ofvid
            elif key in bcFacesSorted:
                bcind = bcFacesSorted[key]
                owner[nrIntFaces + bcind] = ofvid
                bcFaces[bcind] = fnodes
            else:
                faces.append(fnodes)
                facesSorted[key] = offid
                owner[offid] = ofvid
                offid += 1
        ofvid += 1

    def write_header(f, ftype):
        f.write("FoamFile\n{\n\tversion 2.0;\n\tformat ascii;\n")
        f.write(f"\tclass {ftype};\n\tlocation \"{base_name}-constant/polyMesh\";\n\tobject {os.path.basename(f.name)};\n}}\n\n")

    with open(os.path.join(dirname, 'points'), 'w') as f:
        write_header(f, "vectorField")
        pts = mesh.GetElementsByType(SMESH.NODE)
        f.write(f"{len(pts)}\n(\n")
        for ni in pts: f.write(f"\t({ ' '.join(map(str, mesh.GetNodeXYZ(ni))) })\n")
        f.write(")\n")

    with open(os.path.join(dirname, 'faces'), 'w') as f:
        write_header(f, "faceList")
        f.write(f"{nrFaces}\n(\n")
        for nodes in faces + bcFaces: f.write(f"\t{len(nodes)}({' '.join(map(str, [p-1 for p in nodes]))})\n")
        f.write(")\n")

    with open(os.path.join(dirname, 'owner'), 'w') as f:
        write_header(f, "labelList")
        f.write(f"{len(owner)}\n(\n" + "\n".join(map(str, owner)) + "\n)\n")

    with open(os.path.join(dirname, 'neighbour'), 'w') as f:
        write_header(f, "labelList")
        f.write(f"{len(neighbour)}\n(\n" + "\n".join(map(str, neighbour)) + "\n)\n")

    with open(os.path.join(dirname, 'boundary'), 'w') as f:
        write_header(f, "polyBoundaryMesh")
        f.write(f"{len(grpNames)}\n(\n")
        for i, name in enumerate(grpNames):
            ptype = "wall" if "surface" in name.lower() else "patch"
            f.write(f"\t{name}\n\t{{\n\t\ttype {ptype};\n\t\tnFaces {grpNrFaces[i]};\n\t\tstartFace {grpStartFace[i]};\n\t}}\n")
        f.write(")\n")

    if volumeGroups:
        s2f = {sa_id: of_id for of_id, sa_id in enumerate(volumes)}
        with open(os.path.join(dirname, 'cellZones'), 'w') as f:
            write_header(f, "regIOobject")
            f.write(f"{len(volumeGroups)}\n(\n")
            for gr in volumeGroups:
                f.write(f"\t{gr.GetName()}\n\t{{\n\t\ttype cellZone;\n\t\tcellLabels List<label>\n")
                ids = gr.GetIDs()
                f.write(f"\t\t{len(ids)}\n\t\t(\n\t\t\t" + "\n\t\t\t".join(map(str, [s2f[i] for i in ids])) + "\n\t\t);\n\t}\n")
            f.write(")\n")



# ==============================================================================
# snappyHexMesh CASE SETUP
# ==============================================================================

def setup_snappy_hex_mesh_case(base_dir, base_name, h1, growth, layers, base_minthickness, template_dir):
    """Copy template case and modify snappyHexMeshDict."""
    case_dir = os.path.join(base_dir, f"{base_name}-case")
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)

    shutil.copytree(template_dir, case_dir)

    # Create triSurface directory
    stl_dir = os.path.join(case_dir, "constant", "triSurface")
    if not os.path.exists(stl_dir):
        os.makedirs(stl_dir)

    # Modify snappyHexMeshDict
    dict_path = os.path.join(case_dir, "system", "snappyHexMeshDict")
    with open(dict_path, 'r') as f:
        content = f.read()

    # Replace filename in geometry
    old_geom = '"BASENAME_surface.stl"'
    new_geom = f'"{base_name}_surface.stl"'
    content = content.replace(old_geom, new_geom)

    # Replace surface name in layers section
    old_surface = "BASENAME_surface"
    new_surface = f"{base_name}_surface"
    content = content.replace(old_surface, new_surface)

    # Update layer parameters (all placeholders from template)
    content = content.replace("BASENAME_surface", f"{new_surface}")
    content = content.replace("BASE_LAYERS", str(layers))
    content = content.replace("BASE_GROWTH", f"{growth}")
    content = content.replace("BASE_FIRSTLAYER", f"{h1}")
    content = content.replace("BASE_MINTHICKNESS", f"{base_minthickness}")

    with open(dict_path, 'w') as f:
        f.write(content)

    # Fix controlDict: writeInterval must be >= 1
    control_dict_path = os.path.join(case_dir, "system", "controlDict")
    with open(control_dict_path, 'r') as f:
        cd_content = f.read()
    cd_content = cd_content.replace("writeControl    timeStep;", "writeControl    adjustableRunTime;")
    cd_content = cd_content.replace("writeInterval   0;", "writeInterval   1;")
    with open(control_dict_path, 'w') as f:
        f.write(cd_content)

    return case_dir, stl_dir

def export_surface_stl(mesh, group_name, stl_path):
    """Export surface mesh group faces as STL for snappyHexMesh."""
    if os.path.exists(stl_path):
        os.remove(stl_path)

    # Find the group in the mesh
    smesh_group = None
    for gr in mesh.GetGroups():
        if gr.GetName() == group_name:
            smesh_group = gr
            break

    if not smesh_group:
        raise Exception(f"Group '{group_name}' not found in mesh")

    face_ids = smesh_group.GetIDs()


    with open(stl_path, 'w') as f:
        f.write(f"solid {group_name}\n")
        for fid in face_ids:
            fnodes = mesh.GetElemNodes(fid)
            if len(fnodes) >= 3:
                # Get node coordinates
                pts = [mesh.GetNodeXYZ(ni) for ni in fnodes[:3]]
                # Calculate normal
                v1 = (pts[1][0]-pts[0][0], pts[1][1]-pts[0][1], pts[1][2]-pts[0][2])
                v2 = (pts[2][0]-pts[0][0], pts[2][1]-pts[0][1], pts[2][2]-pts[0][2])
                normal = (
                    v1[1]*v2[2] - v1[2]*v2[1],
                    v1[2]*v2[0] - v1[0]*v2[2],
                    v1[0]*v2[1] - v1[1]*v2[0]
                )
                length = math.sqrt(normal[0]**2 + normal[1]**2 + normal[2]**2)
                if length > 0:
                    normal = (normal[0]/length, normal[1]/length, normal[2]/length)
                else:
                    normal = (0, 0, 1)
                f.write(f"  facet normal {normal[0]} {normal[1]} {normal[2]}\n")
                f.write("    outer loop\n")
                for ni in fnodes[:3]:
                    coord = mesh.GetNodeXYZ(ni)
                    f.write(f"      vertex {coord[0]} {coord[1]} {coord[2]}\n")
                f.write("    endloop\n")
                f.write("  endfacet\n")
        f.write(f"endsolid {group_name}\n")

    return True

# ==============================================================================
# WORKFLOW
# ==============================================================================

def run_compute_mesh():
    # -------------------------------------------------
    # 1. Parse Arguments (JSON file)
    # -------------------------------------------------
    args_file = None
    for arg in sys.argv:
        if arg.endswith('.json'):
            if ':' in arg:
                directory, filename = arg.split(':', 1)
                args_file = os.path.join(directory, filename)
            else:
                args_file = os.path.abspath(arg)
            break

    if not args_file or not os.path.exists(args_file):
        print("ERROR: Args file not found.")
        print("Usage: compute_mesh.py <directory>:<args_file.json>")
        return

    with open(args_file, 'r') as f:
        args = json.load(f)

    step_path = args['step_path']
    base_dir = args['base_dir']
    base_name = args['base_name']
    xl = args['xl']
    yl = args['yl']
    zl = args['zl']
    h1 = args['h1']
    layers = args['layers']
    growth = args['growth']
    fineness = args['fineness']
    T = args['T']
    base_minthickness = args.get('BASE_MINTHICKNESS', T * 0.5)
    min_size = args['min_size']
    surf_size = args['surf_size']
    max_size = args['max_size']
    cube_dx = args['cube_dx']
    cube_dy = args['cube_dy']
    cube_dz = args['cube_dz']
    
    # Refine Box params
    refine_dx = args.get('refine_dx', 0.5 * cube_dx)
    refine_dy = args.get('refine_dy', 2 * yl)
    refine_dz = args.get('refine_dz', 2 * zl)
    refine_cx = args.get('refine_cx', 0)
    refine_cy = args.get('refine_cy', 0)
    refine_cz = args.get('refine_cz', 0)
    refine_tx = args.get('refine_tx', 0)
    refine_ty = args.get('refine_ty', 0)
    refine_tz = args.get('refine_tz', 0)
    # refine_local_size: set below in Show Parameters section

    # Template directory for snappyHexMesh case
    # Hardcoded path to skill assets - works regardless of where script is copied
    template_dir = "/home/bosung/.openclaw/workspace/skills/salome-snappy/assets/snappyHexMesh-case-template"

    setup_hdf = os.path.join(base_dir, f"{base_name}_mesh_setup.hdf")
    mesh_hdf = os.path.join(base_dir, f"{base_name}_mesh.hdf")

    # -------------------------------------------------
    # 2. Show Parameters
    # -------------------------------------------------
    print("\n" + "="*60)
    print(f"STAGE 2: MESH COMPUTATION (snappyHexMesh) - {base_name}")
    print("="*60)

    print(f"\n[Mesh Parameters - User Input]")
    user_headers = ["Parameter", "Value", "Description"]
    user_rows = [
        ["h1", f"{h1:.6f} m", "First cell height (for snappyHexMesh)"],
        ["layers", layers, "Boundary layer count (for snappyHexMesh)"],
        ["growth", f"{growth:.4f}", "BL growth rate (for snappyHexMesh)"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"]
    ]
    print(format_table(user_headers, user_rows))

    # Refine local size (read from JSON, no calculation)
    refine_local_size = args.get('refine_local_size', surf_size * 2)

    print(f"\n[Mesh Parameters - Derived]")
    derived_headers = ["Parameter", "Value", "Description"]
    derived_rows = [
        ["BL (T)", f"{T:.6f} m", "Total BL thickness (NOT USED in meshing)"],
        ["min_size", f"{min_size:.6f} m", "Minimum mesh size"],
        ["surf_size", f"{surf_size:.6f} m", "Surface mesh size (=10xT)"],
        ["max_size", f"{max_size:.6f} m", "Max size (=10xl/50)"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "= surf_size x 2 = {surf_size * 2:.6f} m"],
        ["refineBox_dim", f"{refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f}", "RefineBox dimensions (m)"],
        ["refineBox_center", f"({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})", "RefineBox center (m)"]
    ]
    print(format_table(derived_headers, derived_rows))
    
    # Refine Box info
    print(f"\n[Refine Box (wake capture)]")
    print(f"  Size: {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f} m")
    print(f"  Center: ({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})")
    print(f"  Min corner: ({refine_tx:.2f}, {refine_ty:.2f}, {refine_tz:.2f})")
    print(f"  Netgen local size: {refine_local_size:.6f} m (= surf_size x 2 = {surf_size * 2:.6f} m)")

    # -------------------------------------------------
    # 3. Rebuild Geometry (fresh from STEP)
    # -------------------------------------------------
    print("\n" + "-"*60)
    print("REBUILDING GEOMETRY FROM STEP FILE...")
    print("-"*60)

    imported_shape = geompy.ImportSTEP(step_path)
    geompy.addToStudy(imported_shape, "01_Imported_STEP")

    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(imported_shape)
    cx, cy, cz = (x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2

    try:
        tool_shape = geompy.MakeSolid([imported_shape])
        geompy.addToStudy(tool_shape, "02_Tool_Solid")
    except:
        tool_shape = imported_shape

    cube = geompy.MakeBoxDXDYDZ(cube_dx, cube_dy, cube_dz)
    geompy.addToStudy(cube, "03_Raw_Cube")

    tx, ty, tz = cx - 2.5 * xl, cy - 2.5 * yl, cz - 5.0 * zl
    moved_cube = geompy.MakeTranslation(cube, tx, ty, tz)
    geompy.addToStudy(moved_cube, "04_Farfield_Box")

    c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax = geompy.BoundingBox(moved_cube)

    try:
        domain = geompy.MakeCut(moved_cube, tool_shape)
        op_type = "Cut"
    except:
        domain = geompy.MakePartition([moved_cube], [tool_shape])
        op_type = "Partition"

    geompy.addToStudy(domain, f"05_{base_name}_domain")

    # Identify far and model faces
    all_faces = geompy.SubShapeAll(domain, geompy.ShapeType["FACE"])
    tol = 1e-4
    far_faces, model_faces = [], []

    for face in all_faces:
        fb = geompy.BoundingBox(face)
        is_far = any(abs(fb[i] - [c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax][i]) < tol for i in range(6))
        if is_far: far_faces.append(face)
        else: model_faces.append(face)

    group_far = geompy.CreateGroup(domain, geompy.ShapeType["FACE"])
    geompy.UnionList(group_far, far_faces)
    geompy.addToStudyInFather(domain, group_far, "far")

    group_model = geompy.CreateGroup(domain, geompy.ShapeType["FACE"])
    geompy.UnionList(group_model, model_faces)
    geompy.addToStudyInFather(domain, group_model, f"{base_name}_surface")

    print(f"  > Boolean Operation: {op_type} Completed")
    print(f"  > Far faces: {len(far_faces)}, Model faces: {len(model_faces)}")

    # -------------------------------------------------
    # 3b. Create Refine Box in SALOME (cube + translate + volume group)
    # -------------------------------------------------
    print("\n" + "-"*60)
    print("CREATING REFINE BOX IN SALOME...")
    print("-"*60)

    # SALOME cube is always created at (0,0,0) as min corner
    raw_refine_box = geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)
    geompy.addToStudy(raw_refine_box, "RefineBox_Raw")

    # Translate to position using calculate_mesh_params.py tx/ty/tz
    # Translate amounts: (cx - 1.25*xl), (cy - yl), (cz - zl)
    refined_refine_box = geompy.MakeTranslation(raw_refine_box, refine_tx, refine_ty, refine_tz)
    geompy.addToStudy(refined_refine_box, "RefineBox")
    
    # Get bounding box for group identification
    rb_xmin, rb_xmax, rb_ymin, rb_ymax, rb_zmin, rb_zmax = geompy.BoundingBox(refined_refine_box)
    rb_cx = (rb_xmin + rb_xmax) / 2
    rb_cy = (rb_ymin + rb_ymax) / 2
    rb_cz = (rb_zmin + rb_zmax) / 2
    print(f"  > RefineBox size: {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f}")
    print(f"  > RefineBox center: ({rb_cx:.2f}, {rb_cy:.2f}, {rb_cz:.2f})")
    print(f"  > Translate: ({refine_tx:.2f}, {refine_ty:.2f}, {refine_tz:.2f})")

    # -------------------------------------------------
    # 4. Setup snappyHexMesh Case
    # -------------------------------------------------
    print("\n" + "="*60)
    print("STAGE 3: SETUP snappyHexMesh CASE")
    print("="*60)

    case_dir, stl_dir = setup_snappy_hex_mesh_case(base_dir, base_name, h1, growth, layers, base_minthickness, template_dir)
    print(f"  > Copied template case to: {case_dir}")

    # -------------------------------------------------
    # 5. Mesh Setup & Computation (NO VISCOUS LAYERS)
    # -------------------------------------------------
    print("\n" + "="*60)
    print("STAGE 4: MESH SETUP & COMPUTATION (no viscous layers)")
    print("="*60)

    print("\n  Setting up mesh parameters...")
    mesh = smesh.Mesh(domain, f"{base_name}_mesh")
    netgen = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)

    params = netgen.Parameters()
    params.SetNbThreads(8)
    params.SetMaxSize(max_size)
    params.SetMinSize(min_size)
    params.SetLocalSizeOnShape(group_model, surf_size)
    params.SetUseSurfaceCurvature(1)
    params.SetFineness(fineness)

    # Add refineBox as Volume group for Netgen local size
    print("  Creating refineBox volume group...")
    refine_box_volume_group = geompy.CreateGroup(refined_refine_box, geompy.ShapeType["SOLID"])
    # Get all solids inside the refine box and add to group
    refine_box_solids = geompy.SubShapeAll(refined_refine_box, geompy.ShapeType["SOLID"])
    if refine_box_solids:
        geompy.UnionList(refine_box_volume_group, refine_box_solids)
    geompy.addToStudyInFather(refined_refine_box, refine_box_volume_group, "refineBox_volume")
    print(f"  > RefineBox volume group: 'refineBox_volume'")

    # NO viscous layers configured - this is the key difference from original
    print("  > Viscous layers: DISABLED (for snappyHexMesh)")

    print("  Defining mesh groups...")
    mesh.GroupOnGeom(group_far, 'far', SMESH.FACE)
    mesh.GroupOnGeom(group_model, f'{base_name}_surface', SMESH.FACE)
    
    # Apply local size to refineBox volume group
    print(f"  Applying Netgen local size to refineBox volume group: {refine_local_size:.6f} m")
    netgen.SetLocalSizeOnShape(refine_box_volume_group, refine_local_size)

    salome.myStudy.SaveAs(setup_hdf, False, False)
    print(f"  > Mesh Setup Saved: {os.path.basename(setup_hdf)}")

    # ---- Mesh Computation ----
    print("\n  Computing mesh. . .")
    sys.stdout.flush()

    # Temporarily disable log redirect during heavy Netgen computation
    saved_stdout = sys.stdout
    sys.stdout = sys.__stdout__

    start_time = time.time()
    success = mesh.Compute()
    duration = time.time() - start_time

    # Restore log redirect
    sys.stdout = saved_stdout

    if success:
        print(f"\n\n[Computation Statistics]")
        print(f"  Time Taken: {duration:.2f} seconds")
        print(f"  Volumes:    {mesh.NbVolumes()}")
        print(f"  Faces:      {mesh.NbFaces()}")
        print(f"  Edges:      {mesh.NbEdges()}")

        salome.myStudy.SaveAs(mesh_hdf, False, False)
        print(f"\n  > Mesh Saved: {os.path.basename(mesh_hdf)}")

        # ---- Export STL surface for snappyHexMesh ----
        stl_path = os.path.join(stl_dir, f"{base_name}_surface.stl")
        surface_group_name = f"{base_name}_surface"
        print(f"\n  > Exporting surface STL for snappyHexMesh...")
        try:
            export_surface_stl(mesh, surface_group_name, stl_path)
            print(f"  > Surface STL: {stl_path}")
        except Exception as e:
            print(f"  > STL EXPORT ERROR: {e}")

        # ---- Export to OpenFOAM case ----
        foam_out = os.path.join(case_dir, "constant", "polyMesh")
        print(f"\n  > Exporting to OpenFOAM case polyMesh...")
        try:
            exportToFoam(mesh, foam_out, base_name)
            print(f"  > Export Complete: {foam_out}")
        except Exception as e:
            print(f"  > exportToFoam ERROR: {e}")


        # ==============================================
        # PARALLEL snappyHexMesh via mpirun
        # ==============================================

        # Get num_procs from system (physical cores, no HyperThreading)
        import subprocess
        cores_result = subprocess.run(
            "lscpu | grep '^Core(s) per socket:' | awk '{{print $NF}}'" \
            " && lscpu | grep '^Socket(s):' | awk '{{print $NF}}'",
            shell=True, capture_output=True, text=True
        )
        cores_per_socket = int(cores_result.stdout.strip().split('\n')[0].strip())
        sockets = int(cores_result.stdout.strip().split('\n')[1].strip())
        num_procs = cores_per_socket * sockets
        if num_procs < 2:
            num_procs = 2

        print(f"\n{'='*60}")
        print(f"  Setting up decomposeParDict...")
        # Create decomposeParDict
        decomp_dict = os.path.join(case_dir, "system", "decomposeParDict")
        with open(decomp_dict, 'w') as df:
            df.write("""FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposePar;
}

method        scotch;
numberOfSubdomains   %d;
coeffs
{
    n (%d 1 1);
}
""" % (num_procs, num_procs))
        print(f"  > decomposeParDict created: {num_procs} subdomains")

        print(f"\n{'='*60}")
        print(f"  Running decomposePar...")

        decomp_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && cd {case_dir} && decomposePar -force'"
        ret = os.system(decomp_cmd)
        if ret != 0:
            print(f"  ERROR: decomposePar failed (exit {ret})")
            print(f"  Log saved to: {decomp_log}")
            sys.exit(1)
        print(f"  > decomposePar completed successfully")

        # ---- Run snappyHexMesh in parallel via mpirun ----
        print(f"  Running snappyHexMesh parallel ({num_procs} procs)...")
        log_file = os.path.join(case_dir, "log.snappyHexMesh")
        run_cmd = (
            f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && "
            f"cd {case_dir} && mpirun --oversubscribe -np {num_procs} snappyHexMesh -parallel 2>&1 | tee {log_file}'"
        )
        ret = os.system(run_cmd)
        if ret != 0:
            print(f"\n  ERROR: snappyHexMesh failed (exit {ret})")
            print(f"  Log saved to: {log_file}")
            sys.exit(1)
        else:
            print(f"  > snappyHexMesh completed successfully")
            print(f"  > Log: {log_file}")

        # ---- Run reconstructParMesh ----
        print(f"  Running reconstructParMesh...")
        log_file_recon = os.path.join(case_dir, "log.reconstructParMesh")
        recon_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && cd {case_dir} && reconstructParMesh -constant 2>&1 | tee {log_file_recon}'"
        ret = os.system(recon_cmd)
        if ret != 0:
            print(f"  ERROR: reconstructParMesh failed (exit {ret})")
            print(f"  Log saved to: {log_file_recon}")
            sys.exit(1)
        else:
            print(f"  > reconstructParMesh completed successfully")
            print(f"  > Log: {log_file_recon}")

        # ---- Remove processor directories ----
        print(f"  Cleaning up processor directories...")
        proc_dirs = glob_mod.glob(os.path.join(case_dir, "processor*"))
        for pd in proc_dirs:
            shutil.rmtree(pd)
        print(f"  > Removed {len(proc_dirs)} processor directories")

        # ---- Auto-run checkMesh ----
        print(f"\n  Running checkMesh...")
        checklog_path = os.path.join(case_dir, "checkMesh.log")
        with open(checklog_path, 'w') as logfile:
            proc2 = subprocess.run(
                ["checkMesh"],
                cwd=case_dir,
                env=dict(os.environ),
                stdout=logfile,
                stderr=subprocess.STDOUT
            )
            if proc2.returncode == 0:
                print(f"  > checkMesh completed (log: {checklog_path})")
            else:
                print(f"  > checkMesh exited with code {proc2.returncode}")

        # ---- Print checkMesh results ----
        print("\n" + "="*60)
        print("CHECKMESH RESULTS")
        print("="*60)
        with open(checklog_path, 'r') as f:
            content = f.read()
        # Extract key sections
        for line in content.split('\n'):
            if ('Number of cells' in line or 'Number of links' in line or
                'Number of faces' in line or 'Number of bytes' in line or
                'quality' in line or 'max' in line or 'min' in line or
                'Inside the domain' in line or 'Outside the domain' in line or
                'boundary quality' in line or 'Summation' in line or
                'General cell quality' in line or 'General face quality' in line or
                'max cell volume' in line or 'max edge length' in line or
                'max face thickness' in line or 'max face skewness' in line or
                'max non-orthogonality' in line or 'max skewness' in line or
                'max rotation angle' in line or 'max pyramid volume' in line or
                'max relative volume' in line or 'max contact ratio' in line or
                'Number of illegal faces' in line or 'Illegal face' in line or
                'Found' in line or 'Detected' in line or 'wrote' in line or
                'The mesh' in line or 'cell volumes' in line):
                print(f"  {line}")

    else:
        print("\n  > ERROR: Mesh computation failed.")

    # ---- Auto-run checkMesh ----
    checklog_path = os.path.join(case_dir, "checkMesh.log")
    if os.path.exists(checklog_path):
        os.remove(checklog_path)
    check_cmd = (
        f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && "
        f"cd {case_dir} && checkMesh 2>&1 | tee {checklog_path}'"
    )
    ret = os.system(check_cmd)
    if ret == 0:
        print(f"  > checkMesh completed (log: {checklog_path})")
    else:
        print(f"  > checkMesh exited with code {ret}")

    # ---- Create case.foam marker file for ParaView ----
    case_foam_path = os.path.join(case_dir, "case.foam")
    try:
        with open(case_foam_path, 'w') as f:
            f.write(f"# OpenFOAM case marker\n")
            f.write(f"# Created by compute_mesh.py\n")
            f.write(f"# {base_name}\n")
        print(f"  > Created case.foam marker: {case_foam_path}")
    except Exception as e:
        print(f"  > case.foam creation failed: {e}")

    print("\n" + "="*60)
    print("WORKFLOW COMPLETE")
    print("="*60)
    print(f"\n  snappyHexMesh case ready at: {case_dir}")
    print(f"  Full log: {checklog_path}")
    print("="*60)

if __name__ == "__main__":
    run_compute_mesh()

