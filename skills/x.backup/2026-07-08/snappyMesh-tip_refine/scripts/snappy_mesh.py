#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
snappyMesh preprocessing script with tip wake line refinement support (post blockMesh).
Supports auto-discovered tip CSV for wake line refinement via searchableBoxes.

Workflow:
  1. Copy STL to constant/triSurface/
  2. Convert STL to OBJ using surfaceConvert (for feature extraction)
  3. Modify snappyHexMeshDict
     - Refine box (always present)
     - Wake line searchableBoxes (if tip CSV found)
  4. Get actual boundary patches
  5. Update decomposeParDict
  6. Run decomposePar
  7. Run snappyHexMesh in parallel via mpirun
  8. Run reconstructPar
  9. Run checkMesh

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

    patches = re.findall(r'^\s+(\S+)\s*\{$', content, re.MULTILINE)
    patches = [p for p in patches if p not in ('FoamFile', '{', '(')]
    return patches


def build_wake_line_section(tip_wake_lines, wake_level=3):
    """Build geometry + refinementRegions entries for wake line searchableBoxes."""
    if not tip_wake_lines:
        return "", ""

    geo_entries = []
    ref_entries = []

    for i, wline in enumerate(tip_wake_lines):
        name = f"wake_line_{i}"
        mn = wline['min']
        mx = wline['max']
        geo_entries.append(f"""    {name}
    {{
        type searchableBox;
        min ({mn[0]:.6f} {mn[1]:.6f} {mn[2]:.6f});
        max ({mx[0]:.6f} {mx[1]:.6f} {mx[2]:.6f});
    }}""")
        ref_entries.append(f"""    {name}
    {{
        mode inside;
        levels ((1 {wake_level}));
    }}""")

    geo_text = "    // wake line searchableBoxes\n" + "\n".join(geo_entries)
    ref_text = "    " + "\n    ".join(ref_entries)
    return geo_text, ref_text, wake_level


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

    basename = p.get('base_name', os.path.splitext(os.path.basename(args_file))[0])
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

    # === 1. Copy STL to case/constant/triSurface ===
    stl_surface_name = f"{basename}_surface.stl"
    stl_case = os.path.join(case_dir, "constant", "triSurface", stl_surface_name)
    os.makedirs(os.path.dirname(stl_case), exist_ok=True)
    shutil.copy2(stl_file, stl_case)
    print(f"  > STL copied to: constant/triSurface/{stl_surface_name}")

    # === 2. Convert STL to OBJ using surfaceConvert ===
    obj_surface_name = f"{basename}_surface.obj"
    obj_case = os.path.join(case_dir, "constant", "triSurface", obj_surface_name)
    obj_log = os.path.join(case_dir, "constant", "triSurface", f"{basename}_surfaceConvert.log")

    if os.path.exists(obj_case):
        os.remove(obj_case)
    if os.path.exists(obj_log):
        os.remove(obj_log)

    cmd = ("bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && "
           "surfaceConvert " + stl_case + " " + obj_case + " -writeFormat ascii 2>&1' 2>&1 | tee " + obj_log)
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

    # === 3. Parameters from JSON ===
    num_procs = p.get('num_procs', 16)
    h1 = p.get('h1', 0.0001)
    layers = p.get('layers', 10)
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
    max_level = p.get('max_level', max_size_level)
    level_castellation = p.get('level_castellation', max_size_level)
    snap_tolerance = p.get('snap_tolerance', 0.01)
    snap_iter = p.get('snap_iter', 100)
    snap_patch_min = p.get('snap_patch_min', 3)
    feature_angle = p.get('featureAngle', 30)
    loc = p.get('locationinmesh', p.get('far_box_center'))
    if isinstance(loc, list):
        locationinmesh = ' '.join(str(x) for x in loc)
    else:
        locationinmesh = str(loc)

    # === 4. Modify snappyHexMeshDict ===
    dict_path = os.path.join(case_dir, "system", "snappyHexMeshDict")
    with open(dict_path, 'r') as f:
        content = f.read()

    # Replace STL surface name
    content = content.replace('STL_SURFACE.stl', f'{stl_surface_name}')
    content = content.replace('STL_SURFACE', f'{basename}_surface')
    content = content.replace('REFINEBOX_NAME', 'refine_box_surface')
    content = content.replace('REFINEBOX_MODE', 'inside')

    # Replace surface refinement
    content = content.replace('SURFACE_LEVEL', f'({surf_size_level} {min_size_level})')

    # Replace OBJ filename
    content = content.replace('FEATURE_OBJFILE.obj', f'{obj_surface_name}')

    # Replace feature and size parameters
    content = content.replace('REF_FEATURE_LEVEL', f'{feature_level}')
    content = content.replace('BASE_MINSIZE', f'{min_size:.8f}')
    content = content.replace('BASE_SURFSIZE', f'{surf_size:.8f}')
    content = content.replace('BASE_MAXLOCAL', f'{max_local}')
    content = content.replace('BASE_MAXGLOBAL', f'{max_global}')
    content = content.replace('LOCATION_IN_MESH', f'({locationinmesh})')
    content = content.replace('BASE_NSPATCH', f'{snap_patch_min}')
    content = content.replace('BASE_SNAPTOL', f'{snap_tolerance:.4f}')
    content = content.replace('BASE_SNAPITER', f'{snap_iter}')
    content = content.replace('BASE_LAYERS', f'{layers}')
    content = content.replace('BASE_FIRSTLAYER', f'{h1:.8f}')
    content = content.replace('BASE_TOTALTHICKNESS', f'{totalThickness:.8f}')
    content = content.replace('BASE_MINTHICKNESS', f"{p.get('BASE_MINTHICKNESS', totalThickness / 2):.8f}")

    # Replace refine box
    refine_dx = p.get('refine_dx', 0)
    refine_dy = p.get('refine_dy', 0)
    refine_dz = p.get('refine_dz', 0)
    refine_tx = p.get('refine_tx', p.get('cx', 0) - 1.25 * p.get('xl', 0))
    refine_ty = p.get('refine_ty', p.get('cy', 0) - p.get('yl', 0))
    refine_tz = p.get('refine_tz', p.get('cz', 0) - p.get('zl', 0))
    refine_size_level = p.get('refine_size_level', min_size_level - 1)

    if refine_dx > 0 and refine_dy > 0 and refine_dz > 0:
        refine_max_x = refine_tx + refine_dx
        refine_max_y = refine_ty + refine_dy
        refine_max_z = refine_tz + refine_dz
        content = content.replace('REFINEBOX_MIN',
            "(%.6f %.6f %.6f)" % (refine_tx, refine_ty, refine_tz))
        content = content.replace('REFINEBOX_MAX',
            "(%.6f %.6f %.6f)" % (refine_max_x, refine_max_y, refine_max_z))
        content = content.replace('LEVEL', str(refine_size_level))
        cell_size_at_level = min_size * (2 ** refine_size_level)
        print(f"  > Refine box: refine_box_surface (inside, level {refine_size_level}, cell_size={cell_size_at_level:.6f} m)")
        print(f"    min ({refine_tx:.6f}, {refine_ty:.6f}, {refine_tz:.6f})")
        print(f"    max ({refine_max_x:.6f}, {refine_max_y:.6f}, {refine_max_z:.6f})")
    else:
        content = content.replace('    refine_box_surface\n', '    // refine_box_surface (disabled)\n')
        content = content.replace('    {\n        type searchableBox;', '    // {\n        // type searchableBox;')
        content = content.replace('    }\n}', '    // }\n}')

    # === TIP WAKE LINE SECTION ===
    tip_wake_lines = p.get('tip_wake_lines', [])
    tip_wake_refine_size = p.get('tip_wake_refine_size', None)
    tip_points_count = p.get('tip_points_count', 0)

    if tip_wake_lines and len(tip_wake_lines) > 0:
        wake_level = p.get('wake_refine_level', surf_size_level)
        # Replace wake line placeholders
        wake_geo_text, wake_ref_text, wake_level = build_wake_line_section(tip_wake_lines, wake_level)

        # Replace geometry section placeholder
        content = content.replace(
            '    // TIP_WAKE_LINE_PLACEHOLDER\n',
            f'    {wake_geo_text}\n'
        )

        # Replace refinementRegions placeholder
        content = content.replace(
            '        // TIP_WAKE_LINE_REF_PLACEHOLDER\n',
            wake_ref_text
        )

        print(f"\n  > Tip wake lines ({len(tip_wake_lines)}):")
        for i, wline in enumerate(tip_wake_lines):
            print(f"    wake_line_{i}: ({wline['origin'][0]:.4f}, {wline['origin'][1]:.4f}, {wline['origin'][2]:.4f})")
            print(f"             → level {wake_level} (cell_size={min_size * (2**wake_level):.8f} m = 2×surf_size)")

    with open(dict_path, 'w') as f:
        f.write(content)
    print(f"  > snappyHexMeshDict modified from template")

    # === 5. Generate snappyHexMeshDict_addLayers ===
    addlayers_dict = os.path.join(case_dir, "system", "snappyHexMeshDict_addLayers")
    addlayers_content = content
    addlayers_content = addlayers_content.replace('castellatedMesh yes;', 'castellatedMesh no;')
    addlayers_content = addlayers_content.replace('snap            yes;', 'snap            no;')
    addlayers_content = addlayers_content.replace('explicitFeatureSnap true;', 'explicitFeatureSnap false;')
    with open(addlayers_dict, 'w') as f:
        f.write(addlayers_content)
    print(f"  > addLayers snappyHexMeshDict generated")

    # === 6. Get actual boundary patches ===
    actual_patches = get_actual_patches(case_dir)
    if not actual_patches:
        print("  ERROR: Could not find any patches in polyMesh/boundary")
        sys.exit(1)
    print(f"  > Found patches: {actual_patches}")

    # === 7. Update decomposeParDict ===
    decompose_path = os.path.join(case_dir, "system", "decomposeParDict")
    if os.path.exists(decompose_path):
        with open(decompose_path, 'r') as f:
            dc_content = f.read()
        dc_content = dc_content.replace('numberOfSubdomains 1;', f'numberOfSubdomains {num_procs};')
        with open(decompose_path, 'w') as f:
            f.write(dc_content)
        print(f"  > decomposeParDict updated: {num_procs} subdomains")

    # === 8. Run decomposePar ===
    print(f"\n{'='*60}")
    print(f"  Running decomposePar...")
    decomp_cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && decomposePar -force 2>&1 | tee {os.path.join(case_dir, 'log.decomposePar')}'"
    ret = os.system(decomp_cmd)
    if ret != 0:
        print(f"  ERROR: decomposePar failed (exit {ret})")
        sys.exit(1)
    print(f"  > decomposePar completed")

    # === 9. Run snappyHexMesh in parallel ===
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

    # === 10. Run reconstructParMesh ===
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

    # === 11. Clean up processor directories ===
    print(f"  Cleaning up processor directories...")
    import glob
    proc_dirs = glob.glob(os.path.join(case_dir, "processor*"))
    for pd in proc_dirs:
        shutil.rmtree(pd)
    print(f"  > Removed {len(proc_dirs)} processor directories")

    print(f"  case_dir: {case_dir}")
    print(f"  >>> WORKFLOW COMPLETE")
    print(f"{'='*60}")

    # === 12. Run checkMesh ===
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

        # Create case.foam file (OpenFOAM case marker)
        case_foam = os.path.join(case_dir, "case.foam")
        with open(case_foam, 'w') as f:
            pass
        print(f"  > case.foam created at: {case_foam}")
    print(f"  case_dir: {case_dir}")
    print(f"  >>> WORKFLOW COMPLETE")
    print(f"{'='*60}")
