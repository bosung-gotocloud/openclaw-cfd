#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 2 for snappyMesh-elliptic-tip-refine.

Copies the OpenFOAM template, writes blockMeshDict from the elliptic
block-box parameters, and runs blockMesh.

Usage:
    python3 block_mesh.py args:<dir>:<basename>_mesh_args.json
    python3 block_mesh.py <basename>_mesh_args.json
"""

import sys
import os
import json
import shutil


SKILL_TEMPLATE_DIR = (
    "/home/bosung/.openclaw/workspace/skills/snappyMesh-elliptic-tip-refine/"
    "assets/snappyHexMesh-case-template"
)


def main():
    args_file = None
    for arg in sys.argv:
        if arg.endswith(".json"):
            if ":" in arg:
                args_file = arg.split(":", 1)[1]
            else:
                args_file = os.path.abspath(arg)
            break

    if not args_file or not os.path.exists(args_file):
        print("ERROR: JSON args file not found")
        sys.exit(1)

    with open(args_file) as f:
        p = json.load(f)

    basename = p.get("base_name", os.path.splitext(os.path.basename(args_file))[0])
    base_dir = os.path.dirname(os.path.abspath(args_file))
    case_dir = os.path.join(base_dir, f"{basename}-case")

    template_dir = p.get("template_dir") or SKILL_TEMPLATE_DIR
    if not os.path.isdir(template_dir):
        print(f"ERROR: template directory not found: {template_dir}")
        sys.exit(1)

    # === 0. Copy template to case directory ===
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
    shutil.copytree(template_dir, case_dir)
    print(f"  > Template copied to: {case_dir}")

    # === 1. Modify blockMeshDict ===
    block_mesh_dict_path = os.path.join(case_dir, "system", "blockMeshDict")
    with open(block_mesh_dict_path, "r") as f:
        content = f.read()

    max_size = float(p.get("max_size", 1.0))
    block_box = p.get("block_box")
    if not block_box or "min" not in block_box or "max" not in block_box:
        print("ERROR: JSON must contain block_box.min and block_box.max")
        sys.exit(1)

    bxmin, bymin, bzmin = [float(v) for v in block_box["min"]]
    bxmax, bymax, bzmax = [float(v) for v in block_box["max"]]
    block_dx = float(block_box.get("dx", bxmax - bxmin))
    block_dy = float(block_box.get("dy", bymax - bymin))
    block_dz = float(block_box.get("dz", bzmax - bzmin))

    n_x = max(2, int(round(block_dx / max_size)))
    n_y = max(2, int(round(block_dy / max_size)))
    n_z = max(2, int(round(block_dz / max_size)))

    content = content.replace(
        "    (0 0 0) // 0",
        f"    ({bxmin:.8f} {bymin:.8f} {bzmin:.8f}) // 0",
    )
    content = content.replace(
        "    (1 0 0) // 1",
        f"    ({bxmax:.8f} {bymin:.8f} {bzmin:.8f}) // 1",
    )
    content = content.replace(
        "    (1 1 0) // 2",
        f"    ({bxmax:.8f} {bymax:.8f} {bzmin:.8f}) // 2",
    )
    content = content.replace(
        "    (0 1 0) // 3",
        f"    ({bxmin:.8f} {bymax:.8f} {bzmin:.8f}) // 3",
    )
    content = content.replace(
        "    (0 0 1) // 4",
        f"    ({bxmin:.8f} {bymin:.8f} {bzmax:.8f}) // 4",
    )
    content = content.replace(
        "    (1 0 1) // 5",
        f"    ({bxmax:.8f} {bymin:.8f} {bzmax:.8f}) // 5",
    )
    content = content.replace(
        "    (1 1 1) // 6",
        f"    ({bxmax:.8f} {bymax:.8f} {bzmax:.8f}) // 6",
    )
    content = content.replace(
        "    (0 1 1) // 7",
        f"    ({bxmin:.8f} {bymax:.8f} {bzmax:.8f}) // 7",
    )

    content = content.replace(
        "hex (0 1 2 3 4 5 6 7) (20 20 20) simpleGrading (1 1 1)",
        f"hex (0 1 2 3 4 5 6 7) ({n_x} {n_y} {n_z}) simpleGrading (1 1 1)",
    )

    content = content.replace(
        "    (0 1 5 4) // ymin",
        f"    (0 1 5 4) // {bymin:.8f}",
    )
    content = content.replace(
        "    (1 2 6 5) // xmax",
        f"    (1 2 6 5) // {bxmax:.8f}",
    )
    content = content.replace(
        "    (2 3 7 6) // ymax",
        f"    (2 3 7 6) // {bymax:.8f}",
    )
    content = content.replace(
        "    (3 0 4 7) // xmin",
        f"    (3 0 4 7) // {bxmin:.8f}",
    )
    content = content.replace(
        "    (0 3 2 1) // zmin",
        f"    (0 3 2 1) // {bzmin:.8f}",
    )
    content = content.replace(
        "    (4 5 6 7) // zmax",
        f"    (4 5 6 7) // {bzmax:.8f}",
    )

    with open(block_mesh_dict_path, "w") as f:
        f.write(content)
    print("  > blockMeshDict modified")

    # === 2. controlDict is already fixed in template ===
    # === 3. Run blockMesh ===
    log_blockmesh = os.path.join(case_dir, "log.blockMesh")
    cmd = (
        "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
        f"cd {case_dir} && blockMesh > {log_blockmesh} 2>&1'"
    )
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: blockMesh failed (exit {ret})")
        print(f"  Log: {log_blockmesh}")
        sys.exit(1)
    print("  > blockMesh completed successfully")

    # === 4. Verify mesh files ===
    mesh_file = os.path.join(case_dir, "constant", "polyMesh", "points")
    if not os.path.exists(mesh_file):
        print(f"  ERROR: Mesh file not found at {mesh_file}")
        sys.exit(1)
    print(f"  > Mesh created: {os.path.getsize(mesh_file)} bytes")

    print(f"\n  {'=' * 60}")
    print("  MESH INFO")
    print("  " + "=" * 60)
    print(f"  blockMesh domain: {block_dx:.6f} x {block_dy:.6f} x {block_dz:.6f} m")
    print(f"  base cells: {n_x} x {n_y} x {n_z} = {n_x * n_y * n_z}")
    print(f"  case_dir: {case_dir}")
    print("  >>> blockMesh COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
