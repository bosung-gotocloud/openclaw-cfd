#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 3 for snappyMesh-elliptic-tip-refine.

Copies model/far/refine STLs into the case, modifies snappyHexMeshDict,
runs decomposePar + snappyHexMesh + reconstructParMesh, fixes patch types,
and runs checkMesh.

Usage:
    python3 snappy_mesh.py args:<dir>:<basename>_mesh_args.json
    python3 snappy_mesh.py <basename>_mesh_args.json
"""

import re
import sys
import os
import json
import time
import subprocess
import shutil
import glob

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from ellipsoid_stl import generate_axisymmetric_ellipsoid_stl


def get_actual_patches(case_dir):
    boundary_file = os.path.join(case_dir, "constant", "polyMesh", "boundary")
    if not os.path.exists(boundary_file):
        return []
    with open(boundary_file, "r") as f:
        content = f.read()
    patches = re.findall(r"^\s+(\S+)\s*\{$", content, re.MULTILINE)
    return [p for p in patches if p not in ("FoamFile", "{", "(")]


def set_boundary_patch_type(case_dir, patch_name, desired_type):
    boundary_file = os.path.join(case_dir, "constant", "polyMesh", "boundary")
    if not os.path.exists(boundary_file):
        return False

    with open(boundary_file, "r") as f:
        content = f.read()

    lines = content.split("\n")
    new_lines = []
    in_patch = False
    changed = False

    for line in lines:
        stripped = line.strip()

        if stripped.endswith("{") and stripped[:-1].rstrip() == patch_name:
            in_patch = True
            new_lines.append(line)
            continue

        if in_patch:
            if stripped.startswith("type"):
                new_lines.append(re.sub(r"type\s+\S+;", f"type {desired_type};", line))
                changed = True
                in_patch = False
                continue
            if stripped == "}":
                in_patch = False

        new_lines.append(line)

    if changed:
        with open(boundary_file, "w") as f:
            f.write("\n".join(new_lines))

    return changed


def build_wake_line_section(tip_wake_lines, wake_level=3):
    if not tip_wake_lines:
        return "", "", wake_level

    geo_entries = []
    ref_entries = []

    for i, wline in enumerate(tip_wake_lines):
        name = f"wake_line_{i}"
        mn = wline["min"]
        mx = wline["max"]
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


def find_model_stl(base_dir, basename):
    candidates = [
        f"{basename}.stl",
        f"{basename}.STL",
        f"{basename}_watertight.stl",
    ]
    for name in candidates:
        path = os.path.join(base_dir, name)
        if os.path.exists(path):
            return path
    return None


def ensure_ellipsoid_stl(base_dir, spec, label):
    stl_name = spec.get("stl")
    stl_path = spec.get("stl_path") or (os.path.join(base_dir, stl_name) if stl_name else None)
    if stl_path and os.path.exists(stl_path):
        return stl_path

    if not stl_path:
        raise FileNotFoundError(f"{label} STL path missing in JSON")

    generate_axisymmetric_ellipsoid_stl(
        center=spec.get("center"),
        a_x=spec.get("a_x"),
        a_yz=spec.get("a_yz"),
        out_path=stl_path,
        res_u=int(spec.get("res_u", 128)),
        res_v=int(spec.get("res_v", 64)),
        binary=True,
    )
    return stl_path


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

    if not os.path.isdir(os.path.join(case_dir, "system")):
        print(f"ERROR: case directory not found: {case_dir}")
        print("Run block_mesh.py first.")
        sys.exit(1)

    # === 0. Locate / generate required STLs ===
    model_stl = find_model_stl(base_dir, basename)
    if not model_stl:
        print(f"ERROR: model STL not found in {base_dir}")
        sys.exit(1)

    far_spec = p.get("far_ellipsoid", {})
    refine_spec = p.get("refine_ellipsoid", {})

    if not far_spec:
        print("ERROR: far_ellipsoid section missing in JSON")
        sys.exit(1)
    if not refine_spec:
        print("ERROR: refine_ellipsoid section missing in JSON")
        sys.exit(1)

    far_stl_src = ensure_ellipsoid_stl(base_dir, far_spec, "far ellipsoid")
    refine_stl_src = ensure_ellipsoid_stl(base_dir, refine_spec, "refine ellipsoid")

    tri_surface_dir = os.path.join(case_dir, "constant", "triSurface")
    os.makedirs(tri_surface_dir, exist_ok=True)

    model_stl_name = f"{basename}_surface.stl"
    far_stl_name = far_spec.get("stl", f"{basename}_far_ellipsoid.stl")
    refine_stl_name = refine_spec.get("stl", f"{basename}_refine_ellipsoid.stl")

    model_stl_case = os.path.join(tri_surface_dir, model_stl_name)
    far_stl_case = os.path.join(tri_surface_dir, far_stl_name)
    refine_stl_case = os.path.join(tri_surface_dir, refine_stl_name)

    shutil.copy2(model_stl, model_stl_case)
    shutil.copy2(far_stl_src, far_stl_case)
    shutil.copy2(refine_stl_src, refine_stl_case)

    print(f"  > model STL  → constant/triSurface/{model_stl_name}")
    print(f"  > far STL    → constant/triSurface/{far_stl_name}")
    print(f"  > refine STL → constant/triSurface/{refine_stl_name}")

    # === 1. Parameters ===
    num_procs = int(p.get("num_procs", 4))
    h1 = float(p.get("h1", 0.0001))
    growth = float(p.get("growth", 1.2))
    nlayers = int(p.get("layers", 10))

    surf_size_level = int(p.get("surf_size_level", 5))
    min_size_level = int(p.get("min_size_level", 7))
    max_local = p.get("maxLocalCells", 10000000)
    max_global = p.get("maxGlobalCells", 100000000)

    loc = p.get("locationinmesh", [0, 0, 0])
    if isinstance(loc, list):
        locationinmesh = " ".join(str(x) for x in loc)
    else:
        locationinmesh = str(loc)

    model_surface_name = p.get("model_surface_name", f"{basename}_surface")

    far_patch_name = far_spec.get("patch_name", "far")
    far_patch_type = far_spec.get("patch_type", "patch")
    far_level = far_spec.get("boundary_level", [0, 1])
    if not isinstance(far_level, (list, tuple)) or len(far_level) != 2:
        far_level = [1, 2]

    refine_mode = refine_spec.get("mode", "inside")
    refine_level = int(refine_spec.get("refine_level", p.get("refine_size_level", 2)))

    # === 2. Modify snappyHexMeshDict ===
    dict_path = os.path.join(case_dir, "system", "snappyHexMeshDict")
    with open(dict_path, "r") as f:
        content = f.read()

    # Surface names / files
    content = content.replace('"MODEL_STL"', f'"{model_stl_name}"')
    content = content.replace('"FAR_STL"', f'"{far_stl_name}"')
    content = content.replace('"REFINE_STL"', f'"{refine_stl_name}"')

    content = content.replace("MODEL_SURFACE", model_surface_name)
    content = content.replace("FAR_SURFACE", far_patch_name)

    # Refinement levels
    content = content.replace("MODEL_LEVEL", f"({surf_size_level} {min_size_level})")
    content = content.replace("FAR_PATCH_TYPE", far_patch_type)
    content = content.replace("FAR_LEVEL", f"({int(far_level[0])} {int(far_level[1])})")

    content = content.replace("REFINE_MODE", refine_mode)
    content = content.replace("REFINE_LEVEL", str(refine_level))

    # Cell / layer parameters
    content = content.replace("BASE_MAXLOCAL", f"{max_local}")
    content = content.replace("BASE_MAXGLOBAL", f"{max_global}")
    content = content.replace("LOCATION_IN_MESH", f"({locationinmesh})")
    # addLayersControls (relativeSizes true, per-surface layers dict):
    #   firstLayerHeight = 0.5 -> 첫 셀이 local surface cell size의 50%
    #   nSurfaceLayers/nLayers = layers (JSON 값 그대로), expansionRatio = growth
    content = content.replace("nSurfaceLayers    BASE_NLAYERS;",
                              f"nSurfaceLayers    {nlayers};")
    content = content.replace("firstLayerHeight  BASE_FIRSTLAYER;",
                              "firstLayerHeight  0.5;")
    content = content.replace("BASE_EXPANSION_RATIO", f"{growth}")

    # Tip wake lines
    tip_wake_lines = p.get("tip_wake_lines", [])
    if tip_wake_lines:
        wake_level = int(p.get("wake_refine_level", surf_size_level))
        wake_geo, wake_ref, _ = build_wake_line_section(tip_wake_lines, wake_level)

        content = content.replace(
            "    // TIP_WAKE_LINE_PLACEHOLDER\n",
            f"    {wake_geo}\n",
        )
        content = content.replace(
            "        // TIP_WAKE_LINE_REF_PLACEHOLDER\n",
            wake_ref,
        )
        print(f"  > tip wake lines: {len(tip_wake_lines)} (level {wake_level})")
    else:
        content = content.replace("    // TIP_WAKE_LINE_PLACEHOLDER\n", "")
        content = content.replace("        // TIP_WAKE_LINE_REF_PLACEHOLDER\n", "")

    with open(dict_path, "w") as f:
        f.write(content)
    print("  > snappyHexMeshDict modified")

    # === 3. DecomposePar ===
    decompose_path = os.path.join(case_dir, "system", "decomposeParDict")
    if os.path.exists(decompose_path):
        with open(decompose_path, "r") as f:
            dc = f.read()
        dc = re.sub(r"numberOfSubdomains\s+\d+;", f"numberOfSubdomains {num_procs};", dc)
        with open(decompose_path, "w") as f:
            f.write(dc)
        print(f"  > decomposeParDict updated: {num_procs} subdomains")

    log_decomp = os.path.join(case_dir, "log.decomposePar")
    cmd = (
        "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
        f"cd {case_dir} && decomposePar -force > {log_decomp} 2>&1'"
    )
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: decomposePar failed (exit {ret})")
        sys.exit(1)
    print("  > decomposePar completed")

    # === 4. snappyHexMesh ===
    log_snappy = os.path.join(case_dir, "log.snappyHexMesh")
    if num_procs > 1:
        run_cmd = (
            "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
            f"cd {case_dir} && "
            f"setsid nohup mpirun --oversubscribe -np {num_procs} snappyHexMesh -parallel "
            f"> {log_snappy} 2>&1'"
        )
    else:
        run_cmd = (
            "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
            f"cd {case_dir} && "
            f"setsid nohup snappyHexMesh "
            f"> {log_snappy} 2>&1'"
        )
    proc = subprocess.Popen(run_cmd, shell=True, start_new_session=True)
    last_poll = time.time()
    while proc.poll() is None:
        time.sleep(1)
        if time.time() - last_poll >= 300:
            try:
                with open(log_snappy, "r") as f:
                    lines = f.readlines()
                print("  [snappyHexMesh] Running...\n" + "".join(lines[-5:]))
            except Exception:
                print("  [snappyHexMesh] Running...")
            last_poll = time.time()

    if proc.returncode != 0:
        print(f"  ERROR: snappyHexMesh failed (exit {proc.returncode})")
        print(f"  Log: {log_snappy}")
        sys.exit(1)
    print("  > snappyHexMesh completed")

    # === 5. reconstructParMesh ===
    log_recon = os.path.join(case_dir, "log.reconstructParMesh")
    if num_procs > 1:
        cmd = (
            "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
            f"cd {case_dir} && reconstructParMesh -constant > {log_recon} 2>&1'"
        )
    else:
        print("  > single-process run: skipping reconstructParMesh")
        ret = 0
        cmd = None
    if cmd is not None:
        ret = os.system(cmd)
        if ret != 0:
            print(f"  ERROR: reconstructParMesh failed (exit {ret})")
            sys.exit(1)
        print("  > reconstructParMesh completed")

    # === 6. Boundary patch types ===
    actual_patches = get_actual_patches(case_dir)
    print(f"  > patches: {actual_patches}")

    if set_boundary_patch_type(case_dir, model_surface_name, "wall"):
        print(f"  > boundary type fixed: {model_surface_name} → wall")
    else:
        print(f"  > WARNING: model patch not found in boundary: {model_surface_name}")

    if set_boundary_patch_type(case_dir, far_patch_name, far_patch_type):
        print(f"  > boundary type fixed: {far_patch_name} → {far_patch_type}")
    else:
        print(f"  > WARNING: far patch not found in boundary: {far_patch_name}")

    # === 7. Cleanup processor directories ===
    removed = 0
    for pd in glob.glob(os.path.join(case_dir, "processor*")):
        if os.path.isdir(pd):
            shutil.rmtree(pd)
            removed += 1
    print(f"  > removed {removed} processor directories")

    # === 8. case.foam marker ===
    with open(os.path.join(case_dir, "case.foam"), "w") as f:
        pass
    print("  > case.foam created")

    # === 9. checkMesh ===
    log_check = os.path.join(case_dir, "log.checkMesh")
    cmd = (
        "bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
        f"cd {case_dir} && checkMesh > {log_check} 2>&1'"
    )
    ret = os.system(cmd)
    if ret != 0:
        print(f"  WARNING: checkMesh failed (exit {ret})")
        print(f"  Log: {log_check}")
    else:
        print("  > checkMesh completed")
        try:
            with open(log_check, "r") as f:
                for line in f:
                    print(f"  {line.rstrip()}")
        except Exception:
            pass

    print(f"\n  case_dir: {case_dir}")
    print("  >>> WORKFLOW COMPLETE")

if __name__ == "__main__":
    main()
