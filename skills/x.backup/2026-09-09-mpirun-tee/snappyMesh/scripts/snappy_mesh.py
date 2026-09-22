#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
snappyMesh preprocessing script (post blockMesh).
Workflow:
  1. Copy STL to constant/triSurface/
  2. Convert STL to OBJ using surfaceConvert (for feature extraction)
  3. Modify snappyHexMeshDict
  4. Generate snappyHexMeshDict_addLayers
  5. Get actual boundary patches (from blockMesh output)
  6. Update 0/U and 0/p boundaryField
  7. Update decomposeParDict
  8. Run decomposePar
  9. Run snappyHexMesh in parallel via mpirun
 10. Run reconstructPar

All STL units are meters (m).

Usage: snappy_mesh.py args:<dir>:<args_json>
"""
import re
import sys
import os
import json
import shutil


def get_actual_patches(case_dir):
    """Read constant/polyMesh/boundary to get list of actual patches."""
    boundary_file = os.path.join(case_dir, 'constant', 'polyMesh', 'boundary')
    if not os.path.exists(boundary_file):
        return []

    with open(boundary_file, 'r') as f:
        content = f.read()

    # OpenFOAM v2512: patch name is on its own line, not 'name <patchname>'
    # Pattern: standalone word before '{' on its own line
    patches = re.findall(r'^\s+(\S+)\s*\{$', content, re.MULTILINE)
    # Filter out FoamFile metadata
    patches = [p for p in patches if p not in ('FoamFile', '{', '(')]
    return patches

def main():
    args_file = None
    for arg in sys.argv:
        if arg.endswith('.json'):
            if ':' in arg:
                args_file = arg.split(':', 1)[1]
            else:
                args_file = os.path.abspath(arg)

    if not args_file or not os.path.exists(args_file):
        print("ERROR: JSON args file not found")
        sys.exit(1)

    with open(args_file) as f:
        p = json.load(f)

    basename = p.get('base_name', p.get('basename', os.path.splitext(os.path.basename(args_file))[0]))
    base_dir = os.path.dirname(os.path.abspath(args_file))
    case_dir = os.path.join(base_dir, f"{basename}-case")

    # === 0. Get STL file path ===
    stl_file = os.path.join(base_dir, f"{basename}.stl")
    if not os.path.exists(stl_file):
        for alt in [f"{basename}.STL", f"{basename}_watertight.stl"]:
            alt_path = os.path.join(base_dir, alt)
            if os.path.exists(alt_path):
                stl_file = alt_path
                break

    if not os.path.exists(stl_file):
        print(f"ERROR: STL file not found")
        sys.exit(1)

    # === 2. Copy STL to case/constant/triSurface ===
    stl_surface_name = f"{basename}_surface.stl"
    stl_case = os.path.join(case_dir, "constant", "triSurface", stl_surface_name)
    os.makedirs(os.path.dirname(stl_case), exist_ok=True)
    shutil.copy2(stl_file, stl_case)
    print(f"  > STL copied to: constant/triSurface/{stl_surface_name}")

    # === 3. Convert STL to OBJ using surfaceConvert ===
    obj_surface_name = f"{basename}_surface.obj"
    obj_case = os.path.join(case_dir, "constant", "triSurface", obj_surface_name)
    obj_log = os.path.join(case_dir, "constant", "triSurface", f"{basename}_surfaceConvert.log")

    if os.path.exists(obj_case):
        os.remove(obj_case)
    if os.path.exists(obj_log):
        os.remove(obj_log)

    cmd = ("bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && "
           "surfaceConvert " + stl_case + " " + obj_case + " -writeFormat ascii 2>\u00261' 2>\u00261 | tee " + obj_log)
    ret = os.system(cmd)

    if ret != 0 or not os.path.exists(obj_case):
        print(f"  > WARNING: surfaceConvert failed (code={ret}), generating OBJ manually")
        with open(stl_case, 'r') as sf:
            content_sf = sf.read()
        lines_sf = content_sf.strip().split('\n')
        with open(obj_case, 'w') as of:
            of.write("# OBJ generated from " + stl_surface_name + "\n")
            vert_map = {}
            for line in lines_sf:
                line = line.strip()
                if line.startswith('vertex '):
                    parts = line.split()
                    coord = (float(parts[1]), float(parts[2]), float(parts[3]))
                    key = tuple(round(c, 8) for c in coord)
                    if key not in vert_map:
                        vert_map[key] = len(vert_map)
                        of.write("v %.8f %.8f %.8f\n" % coord)
    else:
        size = os.path.getsize(obj_case)
        print(f"  > OBJ generated via surfaceConvert: constant/triSurface/{obj_surface_name} ({size} bytes)")

    # === 4. Parameters from JSON ===
    num_procs = p.get('num_procs', 16)
    h1 = p.get('h1', 0.0001)
    layers = p.get('layers', 10)
    growth = p.get('growth', 1.3)
    totalThickness = p.get('totalThickness', 0.001)
    min_size = p.get('min_size', totalThickness)
    surf_size = p.get('surf_size', 10 * min_size)
    max_size = p.get('max_size', p.get('xl', 1.0) * 10 / 50.0)
    max_local = p.get('maxLocalCells', 1e7)
    max_global = p.get('maxGlobalCells', 1e8)
    min_size_level = p.get('min_size_level', 1)
    max_size_level = p.get('max_size_level', 3)
    surf_size_level = p.get('surf_size_level', max_size_level)
    feature_level = p.get('feature_level', max_size_level)
    max_level = p.get('max_level', max_size_level)  # default 8
    level_castellation = p.get('level_castellation', max_size_level)
    # surf_size is the surface minimal cell size at max_level
    snap_tolerance = p.get('snap_tolerance', 0.01)
    snap_iter = p.get('snap_iter', 100)
    snap_patch_min = p.get('snap_patch_min', 3)
    feature_angle = p.get('featureAngle', 30)
    loc = p.get('locationinmesh', p.get('far_box_center'))
    if isinstance(loc, list):
        locationinmesh = ' '.join(str(x) for x in loc)
    else:
        locationinmesh = str(loc)

    # === 5. Modify snappyHexMeshDict ===
    dict_path = os.path.join(case_dir, "system", "snappyHexMeshDict")
    with open(dict_path, 'r') as f:
        content = f.read()

    content = content.replace('STL_SURFACE.stl', f'{stl_surface_name}')
    content = content.replace('STL_SURFACE', f'{basename}_surface')
    content = content.replace('REF_SURFACE_LEVEL', f'({surf_size_level} {min_size_level})')
    content = content.replace('SURFACE_LEVEL', f'({surf_size_level} {min_size_level})')
    content = content.replace('FEATURE_OBJFILE.obj', f'{obj_surface_name}')
    content = content.replace('REF_FEATURE_LEVEL', f'{feature_level}')
    content = content.replace('BASE_MINSIZE', f'{min_size:.8f}')
    content = content.replace('BASE_SURFSIZE', f'{surf_size:.8f}')
    content = content.replace('BASE_MAXLOCAL', f'{max_local}')
    content = content.replace('BASE_MAXGLOBAL', f'{max_global}')
    content = content.replace('locationInMesh LOCATION_IN_MESH;', f'locationInMesh ({locationinmesh});')
    content = content.replace('BASE_NSPATCH', f'{snap_patch_min}')
    content = content.replace('BASE_SNAPTOL', f'{snap_tolerance:.4f}')
    content = content.replace('BASE_SNAPITER', f'{snap_iter}')
    content = content.replace('BASE_LAYERS', f'{layers}')
    content = content.replace('expansionRatio 1;', f'expansionRatio {growth};')
    content = content.replace('BASE_FIRSTLAYER', f'{h1:.8f}')
    content = content.replace('BASE_TOTALTHICKNESS', f'{totalThickness:.8f}')
    content = content.replace('BASE_MINTHICKNESS', f"{p.get('BASE_MINTHICKNESS', totalThickness / 2):.8f}")
    content = content.replace('thicknessModel firstAndOverall;', 'thicknessModel firstAndOverall;')

    # === Replace refinementRegions placeholders ===
    refine_dx = p.get('refine_dx', 0)
    refine_dy = p.get('refine_dy', 0)
    refine_dz = p.get('refine_dz', 0)
    # Use translate amounts directly (same as salome-snappy)
    refine_tx = p.get('refine_tx', p.get('cx', 0) - 1.25 * p.get('xl', 0))
    refine_ty = p.get('refine_ty', p.get('cy', 0) - p.get('yl', 0))
    refine_tz = p.get('refine_tz', p.get('cz', 0) - p.get('zl', 0))
    refine_cx = p.get('refine_cx', refine_tx + refine_dx / 2)
    refine_cy = p.get('refine_cy', refine_ty + refine_dy / 2)
    refine_cz = p.get('refine_cz', refine_tz + refine_dz / 2)
    refine_size_level = p.get('refine_size_level', min_size_level - 1)
    refine_name = 'refine_box_surface'
    refine_mode = p.get('refine_mode', 'inside')

    if refine_dx > 0 and refine_dy > 0 and refine_dz > 0:
        refine_max_x = refine_tx + refine_dx
        refine_max_y = refine_ty + refine_dy
        refine_max_z = refine_tz + refine_dz

        #         #         # Replace refineRegion placeholders (geometry + refinementRegions)
        content = content.replace('REFINEBOX_NAME', refine_name)
        content = content.replace('REFINEBOX_MIN',
            "(%.6f %.6f %.6f)" % (refine_tx, refine_ty, refine_tz))
        content = content.replace('REFINEBOX_MAX',
            "(%.6f %.6f %.6f)" % (refine_max_x, refine_max_y, refine_max_z))
        content = content.replace('REFINE_LEVEL', str(refine_size_level))
        content = content.replace('LEVEL', str(refine_size_level))
        content = content.replace('REFINEBOX_MODE', refine_mode)
        
        # Calculate actual cell size at this level
        cell_size_at_level = min_size * (2 ** refine_size_level)
        print(f"  > Refine box: '{refine_name}' ({refine_mode}, level {refine_size_level}, cell_size={cell_size_at_level:.6f} m)")
        print(f"    min ({refine_tx:.6f}, {refine_ty:.6f}, {refine_tz:.6f})")
        print(f"    max ({refine_max_x:.6f}, {refine_max_y:.6f}, {refine_max_z:.6f})")
        print(f"    surface level={min_size_level} (cell_size={min_size:.6f} m)")
        print(f"    refine level={refine_size_level} (cell_size={cell_size_at_level:.6f} m) = surface × 2x")

    with open(dict_path, 'w') as f:
        f.write(content)
    print(f"  > snappyHexMeshDict modified from template")

    # === 6. Generate snappyHexMeshDict_addLayers ===
    addlayers_dict = os.path.join(case_dir, "system", "snappyHexMeshDict_addLayers")
    addlayers_content = content
    addlayers_content = addlayers_content.replace('castellatedMesh yes;', 'castellatedMesh no;')
    addlayers_content = addlayers_content.replace('snap            yes;', 'snap            no;')
    addlayers_content = addlayers_content.replace('explicitFeatureSnap true;', 'explicitFeatureSnap false;')
    with open(addlayers_dict, 'w') as f:
        f.write(addlayers_content)
    print(f"  > addLayers snappyHexMeshDict generated")

    # === 7. Get actual boundary patches ===
    actual_patches = get_actual_patches(case_dir)
    if not actual_patches:
        print("  ERROR: Could not find any patches in polyMesh/boundary")
        print("  Make sure blockMesh has been run first (by block_mesh.py or manually).")
        sys.exit(1)
    print(f"  > Found patches: {actual_patches}")

    # Find the STL surface patch name
    stl_patch_name = None
    for patch in actual_patches:
        if patch == f"{stl_surface_name}":
            stl_patch_name = patch
            break
    if not stl_patch_name:
        print(f"  WARNING: Could not find STL surface patch among {actual_patches}")
        stl_patch_name = actual_patches[0] if actual_patches else "unknown"
    print(f"  > STL surface patch: {stl_patch_name}")

    # Replace PATCH_NAME in snappyHexMeshDict with actual STL surface patch name
    content = content.replace('"PATCH_NAME"', f'"{stl_patch_name}"')
    print(f"  > Replaced PATCH_NAME with {stl_patch_name}")

    # === 8. (Removed) boundaryField updates - not needed for snappyHexMesh

    # === 9. Update decomposeParDict ===
    decompose_path = os.path.join(case_dir, "system", "decomposeParDict")
    if os.path.exists(decompose_path):
        with open(decompose_path, 'r') as f:
            dc_content = f.read()
        dc_content = dc_content.replace('numberOfSubdomains 1;', f'numberOfSubdomains {num_procs};')
        with open(decompose_path, 'w') as f:
            f.write(dc_content)
        print(f"  > decomposeParDict updated: {num_procs} subdomains")

    # === 10. Run decomposePar ===
    print(f"\n{'='*60}")
    print(f"  Running decomposePar...")
    decomp_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && decomposePar -force 2>&1 | tee {os.path.join(case_dir, 'log.decomposePar')}'"
    ret = os.system(decomp_cmd)
    if ret != 0:
        print(f"  ERROR: decomposePar failed (exit {ret})")
        sys.exit(1)
    print(f"  > decomposePar completed")

    # === 11. Run snappyHexMesh in parallel ===
    print(f"  Running snappyHexMesh parallel ({num_procs} procs)...")
    log_file = os.path.join(case_dir, "log.snappyHexMesh")
    run_cmd = (
        f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && mpirun -np {num_procs} snappyHexMesh -parallel 2>&1 | tee {log_file}'"
    )
    ret = os.system(run_cmd)
    if ret != 0:
        print(f"\n  ERROR: snappyHexMesh failed (exit {ret})")
        print(f"  Log saved to: {log_file}")
        sys.exit(1)
    else:
        print(f"  > snappyHexMesh completed successfully")
        print(f"  > Log: {log_file}")

    # === 12. Run reconstructParMesh ===
    print(f"  Running reconstructParMesh...")
    log_file_recon = os.path.join(case_dir, "log.reconstructParMesh")
    recon_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && reconstructParMesh -constant 2>&1 | tee {log_file_recon}'"
    ret = os.system(recon_cmd)
    if ret != 0:
        print(f"  ERROR: reconstructParMesh failed (exit {ret})")
        print(f"  Log saved to: {log_file_recon}")
        sys.exit(1)
    else:
        print(f"  > reconstructParMesh completed successfully")
        print(f"  > Log: {log_file_recon}")

    # === 13. Remove processor directories ===
    print(f"  Cleaning up processor directories...")

    # === 13b. Fix STL surface patch type to wall ===
    boundary_file = os.path.join(case_dir, 'constant', 'polyMesh', 'boundary')
    if os.path.exists(boundary_file):
        with open(boundary_file, 'r') as f:
            boundary_content = f.read()

        # Find the STL surface patch block and change type patch -> type wall
        stl_boundary_name = stl_patch_name  # e.g. basename_surface.stl
        lines = boundary_content.split('\n')
        new_lines = []
        in_target_patch = False
        for line in lines:
            stripped = line.strip()
            # Detect patch block start: "stl_boundary_name {"
            if stripped.endswith('{') and stripped[:-1].rstrip() == stl_boundary_name:
                in_target_patch = True
                new_lines.append(line)
                continue
            if in_target_patch and stripped.startswith('type') and 'patch' in stripped:
                new_lines.append(line.replace('type patch;', 'type wall;'))
                in_target_patch = False
                continue
            if in_target_patch and stripped == '}':
                in_target_patch = False
            new_lines.append(line)

        with open(boundary_file, 'w') as f:
            f.write('\n'.join(new_lines))
        print(f"  > Fixed boundary: {stl_boundary_name} type patch → wall")

    # === 14. Remove processor directories ===
    import glob
    proc_dirs = glob.glob(os.path.join(case_dir, "processor*"))
    for pd in proc_dirs:
        shutil.rmtree(pd)
    print(f"  > Removed {len(proc_dirs)} processor directories")

    print(f"  case_dir: {case_dir}")
    print(f"  >>> WORKFLOW COMPLETE")
    print(f"{'='*60}")

    # === 15. Run checkMesh ===
    print(f"\n{'='*60}")
    print("RUNNING checkMesh...")
    print("="*60)
    checklog = os.path.join(case_dir, "log.checkMesh")
    check_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && checkMesh 2>&1 | tee {checklog}'"
    ret = os.system(check_cmd)
    if ret != 0:
        print(f"  WARNING: checkMesh failed (exit {ret})")
        print(f"  Log saved to: {checklog}")
    else:
        print(f"  > checkMesh completed successfully")
        print(f"  > Log saved to: {checklog}")
        print(f"  > Results below:")
        print(f"  {'='*60}")
        with open(checklog, 'r') as f:
            lines = f.readlines()
        for line in lines:
            print(f"  {line.rstrip()}")
        print(f"  {'='*60}")

if __name__ == "__main__":
    main()
