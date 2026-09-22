#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 2: Compute mesh for snappyHexMesh workflow with shock point refinement.
Rebuilds geometry fresh from STEP file, computes mesh WITHOUT viscous layers.
Exports OpenFOAM case with surface STL for snappyHexMesh layer addition.

Added features vs salome-tip_refine-snappy:
  - Auto-discover {basename}-shock-wave*.csv in Stage 1 (calculate_mesh_params.py)
  - Shock point → vertex creation (wake line 처리 직후에 적용)
  - Apply local cell size to shock vertices (shock_refine_size = surf_size × 2)

Mesh sizing:
  max_size     = xl / 5
  surf_size    = xl * 0.01
  min_size     = surf_size / 2
  refine_local_size = max_size / 4
  tip_wake_refine_size = surf_size × 2
  shock_refine_size = surf_size × 2

snappyHexMesh runs in parallel via mpirun with addLayers for viscous BL.
"""

import sys
import os
import json
import math
import time
import shutil
import threading
import glob as glob_mod
import csv
import subprocess
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
    """Export SALOME mesh to OpenFOAM constant/polyMesh format."""
    if not os.path.exists(dirname):
        os.makedirs(dirname)
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
        for ni in pts:
            f.write(f"\t({ ' '.join(map(str, mesh.GetNodeXYZ(ni))) })\n")
        f.write(")\n")

    with open(os.path.join(dirname, 'faces'), 'w') as f:
        write_header(f, "faceList")
        f.write(f"{nrFaces}\n(\n")
        for nodes in faces + bcFaces:
            f.write(f"\t{len(nodes)}({' '.join(map(str, [p-1 for p in nodes]))})\n")
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

    # Write surface STL
    stl_path = os.path.join(dirname, 'surface.stl')
    mesh.ExportSTL(stl_path, 0)

# ==============================================================================
# snappyHexMesh CASE SETUP
# ==============================================================================

def setup_snappy_hex_mesh_case(base_dir, base_name, h1, growth, layers, template_dir):
    """Copy template case and modify snappyHexMeshDict."""
    case_dir = os.path.join(base_dir, f"{base_name}-case")
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)

    shutil.copytree(template_dir, case_dir)

    stl_dir = os.path.join(case_dir, "constant", "triSurface")
    if not os.path.exists(stl_dir):
        os.makedirs(stl_dir)

    dict_path = os.path.join(case_dir, "system", "snappyHexMeshDict")
    with open(dict_path, 'r') as f:
        content = f.read()

    # Replace filename in geometry
    old_geom = '"BASENAME_surface.stl"'
    new_geom = f'"{base_name}_surface.stl"'
    content = content.replace(old_geom, new_geom)

    old_surface = "BASENAME_surface"
    new_surface = f"{base_name}_surface"
    content = content.replace(old_surface, new_surface)

    # Update layers section
    content = content.replace("BASENAME", base_name)

    with open(dict_path, 'w') as f:
        f.write(content)

    return case_dir

def run_compute():
    if len(sys.argv) < 2:
        print("ERROR: Missing mesh_args.json path.")
        return

    args_path = None
    for arg in sys.argv:
        if arg.endswith('_mesh_args.json'):
            if ':' in arg:
                directory, filename = arg.split(':', 1)
                args_path = os.path.join(directory, filename)
            else:
                args_path = os.path.abspath(arg)
            break

    if not args_path or not os.path.exists(args_path):
        print("ERROR: mesh_args.json not found.")
        return

    with open(args_path, 'r') as f:
        args = json.load(f)

    base_dir = args['base_dir']
    base_name = args['base_name']
    step_path = args['step_path']
    xl = args['xl']
    surf_size = args['surf_size']
    min_size = args['min_size']
    max_size = args['max_size']
    refine_local_size = args['refine_local_size']
    h1 = args.get('h1', 0.0001)
    layers = args.get('layers', 10)
    growth = args.get('growth', 1.3)
    fineness = args.get('fineness', 2)

    print("\n" + "="*60)
    print(f"STAGE 2: MESH COMPUTATION - {base_name}")
    print("="*60)

    # ===== Geometry Rebuild =====
    print("\n[Geometry Rebuild]")
    imported_shape = geompy.ImportSTEP(step_path)
    geompy.addToStudy(imported_shape, "01_Imported_STEP")

    # Find the smallest face edge length from the STEP file
    # (used to validate min_size before meshing)
    all_shape_faces = geompy.SubShapeAll(imported_shape, geompy.ShapeType["FACE"])
    import math as _math
    smallest_edge = float('inf')
    for face in all_shape_faces:
        edges = geompy.SubShapeAll(face, geompy.ShapeType["EDGE"])
        for edge in edges:
            try:
                e_bb = geompy.BoundingBox(edge)
                e_len = _math.sqrt((e_bb[1]-e_bb[0])**2 + (e_bb[3]-e_bb[2])**2 + (e_bb[5]-e_bb[4])**2)
                if e_len < smallest_edge:
                    smallest_edge = e_len
            except RuntimeError:
                pass  # skip degenerate edge (void bounding box)
    print(f"  Smallest face edge length: {smallest_edge:.8f} m")

    tool_shape = geompy.MakeSolid([imported_shape])
    geompy.addToStudy(tool_shape, "02_Tool_Solid")

    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(imported_shape)
    cx, cy, cz = (x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2

    # ===== Refine Box =====
    refine_dx = args['refine_dx']
    refine_dy = args['refine_dy']
    refine_dz = args['refine_dz']
    refine_tx = args['refine_tx']
    refine_ty = args['refine_ty']
    refine_tz = args['refine_tz']

    refine_box = geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)
    geompy.addToStudy(refine_box, "05_Refine_Box")
    moved_refine_box = geompy.MakeTranslation(refine_box, refine_tx, refine_ty, refine_tz)
    geompy.addToStudy(moved_refine_box, "06_Refine_Box_Moved")

    # ===== Domain Box =====
    cube_dx = args['cube_dx']
    cube_dy = args['cube_dy']
    cube_dz = args['cube_dz']
    tx_domain = cx - 2.5 * xl
    ty_domain = cy - 2.5 * (args.get('yl', xl) / 2 + xl/2)
    tz_domain = cz - 5.0 * (args.get('zl', yl)/4)

    cube = geompy.MakeBoxDXDYDZ(cube_dx, cube_dy, cube_dz)
    moved_cube = geompy.MakeTranslation(cube, tx_domain, ty_domain, tz_domain)
    domain = geompy.MakeCut(moved_cube, tool_shape)
    geompy.addToStudy(domain, "07_Domain")

    print(f"  Domain: {refine_dx:.2f} x {refine_dy:.2f} x {refine_dz:.2f}")

    # ===== Tip Wake Lines (if found) =====
    wake_line_objects = []
    if args.get('tip_wake_lines'):
        print(f"\n[Creating tip-wake lines ({len(args['tip_wake_lines'])})]")
        for i, wl in enumerate(args['tip_wake_lines']):
            x1, y1, z1 = wl[0], wl[1], wl[2]
            x2 = args['refine_cx'] + args['refine_dx'] / 2 + xl * 0.5
            pt1 = geompy.MakeVertex(x1, y1, z1)
            pt2 = geompy.MakeVertex(x2, y1, z1)
            wake_line = geompy.MakeLine(pt1, pt2)
            # Clip to domain
            clipped = geompy.MakeCut(wake_line, domain)
            geompy.addToStudy(clipped, f"{i+1}_Wake_Line")
            wake_line_objects.append(clipped)

    # ===== Shock Points → Vertices (if shock CSV found) ← NEW =====
    shock_vertex_objects = []
    if args.get('shock_csv_path'):
        shock_refine_size = args['shock_refine_size']
        shock_count = args['shock_points_count']
        print(f"\n[Creating shock vertices ({shock_count} points)]")
        print(f"  Local size: {shock_refine_size:.6f}m (surf_size × 2)")

        # Find the domain shape for clipping
        # Use a slightly larger box for vertex placement to avoid clipping issues
        shock_max_x = args['refine_cx'] + args['refine_dx'] / 2 + xl * 2.0

        with open(args['shock_csv_path'], 'r') as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
            # Check if first row is header
            is_header = False
            if first_row and len(first_row) >= 4:
                try:
                    float(first_row[0])
                except ValueError:
                    is_header = True

            data_rows = []
            if not is_header and first_row:
                data_rows.append(first_row)
            for row in reader:
                if len(row) >= 4:
                    try:
                        x, y, z = float(row[1]), float(row[2]), float(row[3])
                        # Clip to domain bounds
                        c_xmin, c_xmax, c_ymin, c_ymax, c_zmin, c_zmax = geompy.BoundingBox(domain)
                        if c_xmin <= x <= c_xmax and c_ymin <= y <= c_ymax and c_zmin <= z <= c_zmax:
                            data_rows.append(row)
                    except ValueError:
                        pass

        print(f"  Vertices within domain: {len(data_rows)}")
        for i, row in enumerate(data_rows):
            x, y, z = float(row[1]), float(row[2]), float(row[3])
            sh_vtx = geompy.MakeVertex(x, y, z)
            geompy.addToStudy(sh_vtx, f"{base_name}_shock_{i}")
            shock_vertex_objects.append(sh_vtx)

        print(f"  Total shock vertices created: {len(shock_vertex_objects)}")


    # Adjust min_size if it's larger than the smallest face edge
    # (Netgen cannot mesh edges smaller than min_size)
    if smallest_edge > 0:
        if min_size > smallest_edge:
            old_min_size = min_size
            min_size = smallest_edge
            args['min_size'] = min_size
            print(f"  [min_size] Adjusted: {old_min_size:.6f} m → {min_size:.8f} m")
            print(f"    Reason: smallest face edge ({smallest_edge:.6f} m) < original min_size")
        else:
            print(f"  [min_size] OK: {min_size:.6f} m < smallest face edge ({smallest_edge:.6f} m)")
    # ===== Mesh Generation =====
    print(f"\n[Mesh Generation]")
    print(f"  max_size:     {max_size:.6f}")
    print(f"  min_size:     {min_size:.6f}")
    print(f"  surf_size:    {surf_size:.6f}")
    print(f"  refine_local_size: {refine_local_size:.6f}")

    group_model = geompy.getSubShapes(domain, 1, 2)
    group_model = [s for s in group_model if geompy.getType(s) == 'Face']
    group_model_id_list = geompy.getSubShapeIds(domain, "Face")

    mesh = smesh.Mesh(domain, f"{base_name}_mesh", False)
    netgen = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)

    params = netgen.Parameters()
    params.SetNbThreads(8)
    params.SetMaxSize(max_size)
    params.SetMinSize(min_size)
    params.SetLocalSizeOnShape(group_model, surf_size)
    params.SetUseSurfaceCurvature(1)   # ← CRITICAL
    # params.SetFineness(fineness)  # DISABLED - use custom mesh quality (from salome-tip_refine-snappy)
    params.SetOptimize(1)
    # Custom mesh quality (from salome-tip_refine-snappy update):
    params.SetGrowthRate(0.3)
    params.SetNbSegPerEdge(1)
    params.SetNbSegPerRadius(3)

    # refineBox local size (shape only)
    netgen.SetLocalSizeOnShape(moved_refine_box, refine_local_size)

    # Wake lines local size (if tip CSV found)
    if wake_line_objects:
        for wl in wake_line_objects:
            netgen.SetLocalSizeOnShape(wl, args['tip_wake_refine_size'])
        print(f"  tip_wake_refine_size applied to {len(wake_line_objects)} wake lines")

    # Shock vertices local size (if shock CSV found) ← NEW
    if shock_vertex_objects:
        for sh_vtx in shock_vertex_objects:
            netgen.SetLocalSizeOnShape(sh_vtx, args['shock_refine_size'])
        print(f"  shock_refine_size ({args['shock_refine_size']:.6f}m) applied to {len(shock_vertex_objects)} shock vertices")

    # ===== Compute Mesh =====
    print("\n[Computing mesh...] (this may take a while)")
    t0 = time.time()
    status = mesh.Compute()
    elapsed = time.time() - t0

    if status == 0:
        print(f"  ERROR: mesh.Compute() failed!")
        return

    print(f"  Completed in {elapsed:.1f}s")

    # Print cell count
    cells = mesh.GetNbElements()
    nodes = mesh.GetNbNodes()
    faces = mesh.GetNbFaces()
    print(f"  Cells: {cells}, Nodes: {nodes}, Faces: {faces}")

    # ===== Save Mesh =====
    mesh_hdf = os.path.join(base_dir, f"{base_name}_mesh.hdf")
    setup_hdf = os.path.join(base_dir, f"{base_name}_mesh_setup.hdf")
    salome_notebook.notebook.Export(mesh_hdf, 0)
    salome_notebook.notebook.Export(setup_hdf, 0)

    # ===== Export OpenFOAM =====
    foaming_base = base_name + "-case"
    foaming_dir = os.path.join(base_dir, foaming_base, "constant", "polyMesh")
    if not os.path.exists(foaming_dir):
        os.makedirs(foaming_dir)

    exportToFoam(mesh, foaming_dir, base_name)

    # ===== Setup snappyHexMesh Case =====
    template_dir = os.path.expanduser("~/.openclaw/workspace/skills/salome-tip-shock-refine-snappy/assets/snappyHexMesh-case-template")

    case_dir = setup_snappy_hex_mesh_case(
        base_dir, base_name,
        h1, growth, layers,
        template_dir
    )

    print(f"\n[snappyHexMesh Setup Complete]")
    print(f"  Case: {case_dir}")

    # ===== Copy surface STL =====
    stl_src = os.path.join(foaming_dir, "surface.stl")
    stl_dst = os.path.join(case_dir, "constant", "triSurface", f"{base_name}_surface.stl")
    if os.path.exists(stl_src):
        shutil.copy2(stl_src, stl_dst)
        print(f"  Surface STL: {stl_dst}")

    # ===== Run snappyHexMesh =====
    print("\n[Running snappyHexMesh (parallel)...]")
    case_path = os.path.join(base_dir, f"{base_name}-case")
    env = os.environ.copy()
    env['PATH'] += ':/opt/OpenFOAM/OpenFOAM-v2512/platforms/linux64GccDPInt32Opt/bin'

    # decomposePar
    dec_cmd = ['decomposePar', '-case', case_path]
    r = subprocess.run(dec_cmd, capture_output=True, text=True, timeout=600, env=env)
    print(f"  decomposePar: {'OK' if r.returncode == 0 else 'FAIL'}")

    # snappyHexMesh parallel — 2026-09-10: setsid+nohup detach, poll loop 대기
    log_sh = os.path.join(case_path, "log.snappyHexMesh")
    case_path_abs = os.path.abspath(case_path)
    mpirun_cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null; "
                  f"cd {case_path_abs} && "
                  f"setsid nohup mpirun --oversubscribe -np 8 snappyHexMesh -case {case_path_abs} "
                  f"> {log_sh} 2>&1'")
    print(f"  Running: mpirun --oversubscribe -np 8 snappyHexMesh (detached)")
    proc = subprocess.Popen(mpirun_cmd, shell=True, start_new_session=True, env=env)
    last_poll = time.time()
    while proc.poll() is None:
        time.sleep(1)
        if time.time() - last_poll >= 300:
            try:
                with open(log_sh, 'r') as f:
                    lines = f.readlines()
                print(f"  [snappyHexMesh] Running... (last 3 lines)\n" + '\n'.join(lines[-3:]))
            except (FileNotFoundError, IOError):
                print(f"  [snappyHexMesh] Running...")
            last_poll = time.time()
    if proc.returncode == 0:
        print("  snappyHexMesh: OK")
    else:
        print(f"  snappyHexMesh: FAIL (rc={proc.returncode})")
        # Try serial fallback
        print("  -> Retrying serial...")
        sh_cmd = ['snappyHexMesh', '-case', case_path]
        r3 = subprocess.run(sh_cmd, capture_output=True, text=True, timeout=3600, env=env)

    # reconstructParMesh
    recon_cmd = ['reconstructParMesh', '-case', case_path]
    r4 = subprocess.run(recon_cmd, capture_output=True, text=True, timeout=600, env=env)
    print(f"  reconstructParMesh: {'OK' if r4.returncode == 0 else 'FAIL'}")

    # checkMesh
    cm_cmd = ['checkMesh', '-case', case_path]
    r5 = subprocess.run(cm_cmd, capture_output=True, text=True, timeout=300, env=env)
    log_path = os.path.join(case_path, "checkMesh.log")
    with open(log_path, 'w') as f:
        f.write(r5.stdout + "\n" + r5.stderr)

    print(f"\n[Done] checkMesh.log -> {log_path}")
    print(f"Final case structure:")
    for item in sorted(os.listdir(case_dir)):
        item_path = os.path.join(case_dir, item)
        if os.path.isdir(item_path):
            sub_count = len(os.listdir(item_path))
            print(f"  {item}/ ({sub_count} files)")
        else:
            print(f"  {item}")

run_compute()
