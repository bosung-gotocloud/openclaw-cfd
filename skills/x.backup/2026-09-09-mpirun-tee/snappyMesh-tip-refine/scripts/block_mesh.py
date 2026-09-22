#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Block mesh script for snappyMesh (pre-processing).
Copies template case → modifies blockMeshDict → runs blockMesh.

Usage: block_mesh.py args:<dir>:<args_json>
"""
import sys
import os
import json
import shutil
import glob


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
    # Try JSON-specified template_dir first, then fall back to skill location
    template_dir = p.get('template_dir')
    if not template_dir:
        template_dir = "/home/bosung/.openclaw/workspace/skills/snappyMesh-tip_refine/assets/snappyHexMesh-case-template"

    # === 0. Copy template to case directory ===
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
    shutil.copytree(template_dir, case_dir)
    print(f"  > Template copied to: {case_dir}")

    # === 1. Modify blockMeshDict ===
    block_mesh_dict_path = os.path.join(case_dir, "system", "blockMeshDict")
    with open(block_mesh_dict_path, 'r') as f:
        content = f.read()

    xl = p.get('xl', 1.0)
    yl = p.get('yl', 1.0)
    zl = p.get('zl', 1.0)
    box_dx = p.get('box_dx', 10.0)
    box_dy = p.get('box_dy', 5.0)
    box_dz = p.get('box_dz', 10.0)
    tx = p.get('tx', -5.0)
    ty = p.get('ty', -1.25)
    tz = p.get('tz', -2.5)
    far_xmax = p.get('far_box_center')[0] + box_dx / 2
    far_ymax = p.get('far_box_center')[1] + box_dy / 2
    far_zmax = p.get('far_box_center')[2] + box_dz / 2

    # Compute edge divisions
    max_size = p.get('max_size', xl * 10 / 50.0)
    n_x = max(2, round(box_dx / max_size))
    n_y = max(2, round(box_dy / max_size))
    n_z = max(2, round(box_dz / max_size))

    # Far box corner (xmin, ymin, zmin)
    far_xmin = tx
    far_ymin = ty
    far_zmin = tz

    # Replace vertices
    content = content.replace('    (0 0 0) // 0', f'    ({far_xmin:.6f} {far_ymin:.6f} {far_zmin:.6f}) // 0')
    content = content.replace('    (1 0 0) // 1', f'    ({far_xmax:.6f} {far_ymin:.6f} {far_zmin:.6f}) // 1')
    content = content.replace('    (1 1 0) // 2', f'    ({far_xmax:.6f} {far_ymax:.6f} {far_zmin:.6f}) // 2')
    content = content.replace('    (0 1 0) // 3', f'    ({far_xmin:.6f} {far_ymax:.6f} {far_zmin:.6f}) // 3')
    content = content.replace('    (0 0 1) // 4', f'    ({far_xmin:.6f} {far_ymin:.6f} {far_zmax:.6f}) // 4')
    content = content.replace('    (1 0 1) // 5', f'    ({far_xmax:.6f} {far_ymin:.6f} {far_zmax:.6f}) // 5')
    content = content.replace('    (1 1 1) // 6', f'    ({far_xmax:.6f} {far_ymax:.6f} {far_zmax:.6f}) // 6')
    content = content.replace('    (0 1 1) // 7', f'    ({far_xmin:.6f} {far_ymax:.6f} {far_zmax:.6f}) // 7')

    # Replace block grading
    content = content.replace('hex (0 1 2 3 4 5 6 7) (20 20 20) simpleGrading (1 1 1)',
        f'hex (0 1 2 3 4 5 6 7) ({n_x} {n_y} {n_z}) simpleGrading (1 1 1)')

    # Replace face definitions
    content = content.replace('    (0 1 5 4) // ymin', f'    (0 1 5 4) // {far_ymin:.6f}')
    content = content.replace('    (1 2 6 5) // xmax', f'    (1 2 6 5) // {far_xmax:.6f}')
    content = content.replace('    (2 3 7 6) // ymax', f'    (2 3 7 6) // {far_ymax:.6f}')
    content = content.replace('    (3 0 4 7) // xmin', f'    (3 0 4 7) // {far_xmin:.6f}')
    content = content.replace('    (0 3 2 1) // zmin', f'    (0 3 2 1) // {far_zmin:.6f}')
    content = content.replace('    (4 5 6 7) // zmax', f'    (4 5 6 7) // {far_zmax:.6f}')

    with open(block_mesh_dict_path, 'w') as f:
        f.write(content)
    print(f"  > blockMeshDict modified")

    # === 2. Fix controlDict ===
    control_dict_path = os.path.join(case_dir, "system", "controlDict")
    with open(control_dict_path, 'r') as f:
        cd = f.read()
    cd = cd.replace('writeControl     none;', 'writeControl     none;')
    cd = cd.replace('writeFrequency    0;', 'writeFrequency    0;')
    with open(control_dict_path, 'w') as f:
        f.write(cd)

    # === 3. Run blockMesh ===
    print(f"\n{'='*60}")
    print("  Running blockMesh...")
    log_blockmesh = os.path.join(case_dir, "log.blockMesh")
    cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && blockMesh 2>&1 | tee {log_blockmesh}'"
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: blockMesh failed (exit {ret})")
        sys.exit(1)
    print(f"  > blockMesh completed successfully")
    print(f"  > Log: {log_blockmesh}")

    # === 4. Verify mesh was created ===
    mesh_dir = os.path.join(case_dir, "constant", "polyMesh")
    # OpenFOAM v2512 uses separate mesh files, not a single polyMesh file
    # Check for points file as the key mesh file indicator
    mesh_file = os.path.join(mesh_dir, "points")
    if not os.path.exists(mesh_file):
        print(f"  ERROR: Mesh file not found at {mesh_file}")
        sys.exit(1)
    mesh_size = os.path.getsize(mesh_file)
    print(f"  > Mesh created: {mesh_size} bytes")

    # === 5. Print mesh info ===
    print(f"\n  {'='*60}")
    print("  MESH INFO")
    print("  " + "=" * 60)
    print(f"  Domain size: ({box_dx:.3f}, {box_dy:.3f}, {box_dz:.3f}) m")
    print(f"  Cell count: {n_x} × {n_y} × {n_z} = {n_x*n_y*n_z}")
    print(f"  Far box center: {p.get('far_box_center', [0,0,0])}")
    print(f"  {'='*60}")
    print(f"  case_dir: {case_dir}")
    print(f"  >>> blockMesh COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
