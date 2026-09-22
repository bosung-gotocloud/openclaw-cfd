#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 2: Compute mesh using arguments from calculate_mesh_params.py
Rebuilds geometry fresh from STEP file, then computes mesh.
Adds refineBox volumetric refinement in SALOME using Netgen local size.
"""

import sys
import os
import json
import math
import time
import threading
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

salome.salome_init()
geompy = geomBuilder.New()
smesh = smeshBuilder.New()

def format_table(headers, rows):
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
    """Custom export of SALOME mesh to OpenFOAM polyMesh format (with cellZones support)."""
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
    volumeGroups = []
    ofbcfid = 0

    for gr in mesh.GetGroups():
        g_type = gr.GetType()
        if g_type == SMESH.FACE:
            grIds = gr.GetIDs()
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

    # Write boundary file
    # Collect face groups: far (all) + wall groups
    far_faces_list = []   # list of face indices (in faces+bcFaces)
    wall_groups = {}      # name -> list of face indices
    tol = 1e-4

    for gr in mesh.GetGroups():
        if gr.GetType() != SMESH.FACE:
            continue
        name = gr.GetName()
        gr_ids = gr.GetIDs()
        for sfid in gr_ids:
            fnodes = mesh.GetElemNodes(sfid)
            key = MeshBuffer.Key(fnodes)
            if key in bcFacesSorted:
                fi = bcFacesSorted[key]
                # Determine center of this face
                node_coords = [mesh.GetNodeXYZ(ni) for ni in fnodes]
                cx = sum(p[0] for p in node_coords) / len(node_coords)
                cy = sum(p[1] for p in node_coords) / len(node_coords)
                cz = sum(p[2] for p in node_coords) / len(node_coords)
                # Check if this face belongs to the far box
                if (abs(cx - c_xmin) < tol or abs(cx - c_xmax) < tol or
                    abs(cy - c_ymin) < tol or abs(cy - c_ymax) < tol or
                    abs(cz - c_zmin) < tol or abs(cz - c_zmax) < tol):
                    far_faces_list.append(fi)
                else:
                    if name not in wall_groups:
                        wall_groups[name] = []
                    wall_groups[name].append(fi)
            elif key in facesSorted:
                if name not in wall_groups:
                    wall_groups[name] = []
                wall_groups[name].append(key)

    with open(os.path.join(dirname, 'boundary'), 'w') as f:
        write_header(f, "polyBoundaryMesh")
        n_groups = 1 + len(wall_groups)  # 1 far + each wall group
        f.write(f"{n_groups}\n(\n")

        # Far patch (single)
        start = nrIntFaces
        f.write(f"\tfar\n")
        f.write(f"\t{{\n\t\ttype patch;\n\t\tnFaces {len(far_faces_list)};\n\t\tstartFace {start};\n\t}}\n")

        # Wall patches
        for name in wall_groups:
            start = nrIntFaces + 1
            f.write(f"\t{name}\n")
            f.write(f"\t{{\n\t\ttype wall;\n\t\tnFaces {len(wall_groups[name])};\n\t\tstartFace {start};\n\t}}\n")
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

def run_compute_mesh():
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
    refine_local_size = args.get('refine_local_size', surf_size * 2)
    
    setup_hdf = os.path.join(base_dir, f"{base_name}_mesh_setup.hdf")
    mesh_hdf = os.path.join(base_dir, f"{base_name}_mesh.hdf")

    print("\n" + "="*60)
    print(f"STAGE 2: MESH COMPUTATION - {base_name}")
    print("="*60)
    print(f"\n[Mesh Parameters - User Input]")
    user_headers = ["Parameter", "Value", "Description"]
    user_rows = [
        ["h1", f"{h1:.6f} m", "First cell height"],
        ["layers", layers, "Boundary layer count"],
        ["growth", f"{growth:.4f}", "BL growth rate"],
        ["fineness", fineness, "2=mod / 3=fine / 4=vfine"]
    ]
    print(format_table(user_headers, user_rows))
    print(f"\n[Mesh Parameters - Derived]")
    derived_headers = ["Parameter", "Value", "Description"]
    derived_rows = [
        ["min_size", f"{min_size:.6f} m", "Minimum mesh size"],
        ["surf_size", f"{surf_size:.6f} m", "Surface mesh size"],
        ["max_size", f"{max_size:.6f} m", "Max size"],
        ["refine_local_size", f"{refine_local_size:.6f} m", "= surf_size x 2 = {surf_size * 2:.6f} m"],
    ]
    print(format_table(derived_headers, derived_rows))
    
    # Refine Box info
    print(f"\n[Refine Box (wake capture)]")
    print(f"  Size: {refine_dx:.4f} x {refine_dy:.4f} x {refine_dz:.4f} m")
    print(f"  Center: ({refine_cx:.2f}, {refine_cy:.2f}, {refine_cz:.2f})")
    print(f"  Netgen local size: {refine_local_size:.6f} m (= surf_size x 2)")

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
        print("  > Solid creation: Success")
    except:
        tool_shape = imported_shape
        print("  > Solid creation: Failed (using shell)")

    cube = geompy.MakeBoxDXDYDZ(cube_dx, cube_dy, cube_dz)
    geompy.addToStudy(cube, "03_Raw_Cube")
    tx, ty, tz = cx - 2.5 * xl, cy - 2.5 * yl, cz - 5.0 * zl
    moved_cube = geompy.MakeTranslation(cube, tx, ty, tz)
    geompy.addToStudy(moved_cube, "04_Farfield_Box")
    c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax = geompy.BoundingBox(moved_cube)
    print(f"  > FarBox center: ({c_xmin + cube_dx/2:.4f}, {c_ymin + cube_dy/2:.4f}, {c_zmin + cube_dz/2:.4f})")

    try:
        domain = geompy.MakeCut(moved_cube, tool_shape)
        op_type = "Cut"
    except:
        domain = geompy.MakePartition([moved_cube], [tool_shape])
        op_type = "Partition"
    geompy.addToStudy(domain, f"{base_name}_domain")
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

    # ------  ------  ------  ------
    # 2b. Create Refine Box in SALOME (cube + translate + volume group)
    # ------  ------ ------  ------
    print("\n" + "-"*60)
    print("CREATING REFINE BOX IN SALOME...")
    print("-"*60)

    # SALOME cube is always created at (0,0,0) as min corner
    raw_refine_box = geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)
    geompy.addToStudy(raw_refine_box, "RefineBox_Raw")

    # Translate to position
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

    # ------  ------  ------  ------
    # 3. Setup Refine Box Volume Group & Mesh
    # ------  ------  ------  ------
    print("\n" + "="*60)
    print("STAGE 3: MESH SETUP & COMPUTATION")
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
    refine_box_solids = geompy.SubShapeAll(refined_refine_box, geompy.ShapeType["SOLID"])
    if refine_box_solids:
        geompy.UnionList(refine_box_volume_group, refine_box_solids)
    geompy.addToStudyInFather(refined_refine_box, refine_box_volume_group, "refineBox_volume")
    print(f"  > RefineBox volume group: 'refineBox_volume'")
    
    # Apply local size to refineBox volume group
    print(f"  Applying Netgen local size to refineBox volume group: {refine_local_size:.6f} m")
    netgen.SetLocalSizeOnShape(refine_box_volume_group, refine_local_size)
    
    print("  Configuring viscous layers...")
    netgen.ViscousLayers(T, layers, growth, far_faces, 1, smeshBuilder.FACE_OFFSET)
    print("  Defining mesh groups...")
    mesh.GroupOnGeom(group_far, 'far', SMESH.FACE)
    mesh.GroupOnGeom(group_model, f'{base_name}_surface', SMESH.FACE)
    salome.myStudy.SaveAs(setup_hdf, False, False)
    print(f"  > Mesh Setup Saved: {os.path.basename(setup_hdf)}")

    print("\n  Computing mesh...")
    start_time = time.time()
    success = mesh.Compute()
    duration = time.time() - start_time
    if success:
        print(f"\n\n[Computation Statistics]")
        print(f"  Time Taken: {duration:.2f} seconds")
        print(f"  Volumes:    {mesh.NbVolumes()}")
        print(f"  Faces:      {mesh.NbFaces()}")
        print(f"  Edges:      {mesh.NbEdges()}")
        salome.myStudy.SaveAs(mesh_hdf, False, False)
        print(f"\n  > Final Step Saved: {os.path.basename(mesh_hdf)}")
        foam_out = os.path.join(base_dir, f"{base_name}-constant", "polyMesh")
        print(f"\n  > Exporting to PolyMesh format (with cellZones)...")
        try:
            exportToFoam(mesh, foam_out, base_name)
            print(f"  > Export Complete: {foam_out}")
        except Exception as e:
            print(f"  > EXPORT/RENUMBER ERROR: {e}")
    else:
        print("\n  > ERROR: Mesh computation failed.")
    print("\n" + "="*60)
    print("WORKFLOW COMPLETE")
    print("="*60)

if __name__ == "__main__":
    run_compute_mesh()
