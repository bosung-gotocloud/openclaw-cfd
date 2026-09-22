#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 2: Copy template case -> modify blockMeshDict -> run blockMesh
-> copy mesh to 0/ and constant/ -> generate snappyHexMeshDict_addLayers
"""
import sys
import os
import json
import shutil
import re

_log_file = None  # Will be set to case_dir/log.blockMesh after case_dir is known

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
    base_dir = p.get('base_dir', os.path.dirname(os.path.abspath(args_file)))
    case_dir = os.path.join(base_dir, f"{basename}-case")
    template_dir = "/home/bosung/.openclaw/workspace/skills/snappyMesh/assets/snappyHexMesh-case-template"

    # === 1. Copy template case ===
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
    shutil.copytree(template_dir, case_dir)
    print(f"  > Template case copied to: {case_dir}")

    # === 2. Calculate domain from mesh args ===
    xl = p.get('xl', 1.0)
    yl = p.get('yl', 1.0)
    zl = p.get('zl', 1.0)

    box_dx = p.get('box_dx', 10 * xl)
    box_dy = p.get('box_dy', 5 * yl)
    box_dz = p.get('box_dz', 10 * zl)
    tx = p.get('tx', (xl + xl)/2 - box_dx / 2)
    ty = p.get('ty', (yl + yl)/2 - box_dy / 2)
    tz = p.get('tz', (zl + zl)/2 - box_dz / 2)

    max_size = p.get('max_size', xl * 10 / 50.0)
    n_x = max(2, round(box_dx / max_size))
    n_y = max(2, round(box_dy / max_size))
    n_z = max(2, round(box_dz / max_size))

    # === 3. Generate blockMeshDict (template based) ===
    dict_path = os.path.join(case_dir, "system", "blockMeshDict")

    v0 = (tx, ty, tz)
    v1 = (tx+box_dx, ty, tz)
    v2 = (tx+box_dx, ty+box_dy, tz)
    v3 = (tx, ty+box_dy, tz)
    v4 = (tx, ty, tz+box_dz)
    v5 = (tx+box_dx, ty, tz+box_dz)
    v6 = (tx+box_dx, ty+box_dy, tz+box_dz)
    v7 = (tx, ty+box_dy, tz+box_dz)

    template_dict = os.path.join(template_dir, "system", "blockMeshDict")
    with open(template_dict, 'r') as f:
        content = f.read()

    # Replace cell divisions (20 20 20 -> n_x n_y n_z)
    content = re.sub(r'\(\s*20\s+20\s+20\s*\)', '(%d %d %d)' % (n_x, n_y, n_z), content)

    # Remove mergePatchPairs section
    content = content.replace('mergePatchPairs\n(\n);\n', '')

    # Replace vertex coordinates - use unique comments to avoid affecting simpleGrading
    content = content.replace('(0 0 0) // 0', '(%.6f %.6f %.6f) // 0' % v0)
    content = content.replace('(1 0 0) // 1', '(%.6f %.6f %.6f) // 1' % v1)
    content = content.replace('(1 1 0) // 2', '(%.6f %.6f %.6f) // 2' % v2)
    content = content.replace('(0 1 0) // 3', '(%.6f %.6f %.6f) // 3' % v3)
    content = content.replace('(0 0 1) // 4', '(%.6f %.6f %.6f) // 4' % v4)
    content = content.replace('(1 0 1) // 5', '(%.6f %.6f %.6f) // 5' % v5)
    content = content.replace('(1 1 1) // 6', '(%.6f %.6f %.6f) // 6' % v6)
    content = content.replace('(0 1 1) // 7', '(%.6f %.6f %.6f) // 7' % v7)

    with open(dict_path, 'w') as f:
        f.write(content)
    print(f"  > blockMeshDict generated: {dict_path}")

    # === 4. Run blockMesh ===
    log_path = os.path.join(case_dir, "log.blockMesh")
    with open(log_path, 'w') as log_fh:
        print(f"\n{'='*60}")
        print(f"STAGE: blockMeshDict generated")
        print(f"{'='*60}")
        print(f"  Domain: {box_dx:.4f} x {box_dy:.6f} x {box_dz:.6f} m")
        print(f"  Corner: ({tx:.4f}, {ty:.6f}, {tz:.6f})")
        print(f"  Divisions: {n_x} x {n_y} x {n_z}")
        print(f"  Total cells: {n_x * n_y * n_z}")
        print(f"{'='*60}")

        print(f"  Running blockMesh...")
        block_mesh_cmd = (
            f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && blockMesh 2>&1 | tee {log_path}'"
        )
        ret = os.system(block_mesh_cmd)
        log_fh.flush()
        if ret != 0:
            print(f"  ERROR: blockMesh failed (exit {ret})")
            sys.exit(1)
        print(f"  > blockMesh completed successfully")

    # === 5. Copy mesh to 0/ for snappyHexMesh ===
    mesh_src = os.path.join(case_dir, "constant", "polyMesh", "polyMesh")
    mesh_dst = os.path.join(case_dir, "0", "polyMesh")
    if os.path.exists(mesh_src):
        shutil.copy2(mesh_src, mesh_dst)
        print(f"  > Mesh copied to 0/polyMesh")

    # Copy 0/p (initial condition) if exists
    p_src = os.path.join(case_dir, "0", "p")
    p_dst = os.path.join(case_dir, "constant", "p")
    if os.path.exists(p_src):
        shutil.copy2(p_src, p_dst)
        print(f"  > 0/p copied to constant/p")

    # === 6. Generate snappyHexMeshDict_addLayers ===
    sh_template = os.path.join(case_dir, "system", "snappyHexMeshDict")
    addlayers_dict = os.path.join(case_dir, "system", "snappyHexMeshDict_addLayers")
    if os.path.exists(sh_template):
        with open(sh_template, 'r') as f:
            sh_content = f.read()
        addlayers_content = sh_content
        addlayers_content = addlayers_content.replace('castellatedMesh yes;', 'castellatedMesh no;')
        addlayers_content = addlayers_content.replace('snap            yes;', 'snap            no;')
        addlayers_content = addlayers_content.replace('explicitFeatureSnap true;', 'explicitFeatureSnap false;')
        with open(addlayers_dict, 'w') as f:
            f.write(addlayers_content)
        print(f"  > addLayers snappyHexMeshDict generated")

    print(f"  case_dir: {case_dir}")
    print(f"\n  >>> NEXT: Run snappy_mesh.py to proceed")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
