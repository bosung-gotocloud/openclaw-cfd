#!/usr/bin/env python3
"""
full_pipeline.py - Shock Refinement Pipeline (SKILL.md compliant v3)

Step 1: VTK 메쉬 로드
Step 2: SI 계산  
Step 3: P95 cellID 추출
Step 4: case 복사 (0/, system/, constant/)
Step 5a: cellSet 생성 (FoamFile header 포함)
Step 5b: topoSetDict 생성 + topoSet 실행
Step 6: refineMeshDict 생성 + refineMesh 실행

OpenFOAM native utilities 사용. Python으로 template 기반 파일 생성.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def get_of_env():
    """OpenFOAM 환경변수 로딩."""
    env = os.environ.copy()
    bashrc_path = "/opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc"

    if os.path.exists(bashrc_path):
        result = subprocess.run(
            ["/bin/bash", "-c", "source {} 2>/dev/null && env".format(bashrc_path)],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                if any(key.startswith(kw) for kw in ['WM_', 'FOAM_', 'LD_LIBRARY', 'PATH']):
                    env[key] = val
    else:
        env["PATH"] = "/opt/OpenFOAM/OpenFOAM-v2512/bin" + os.pathsep + env.get("PATH", "")

    return env


def read_template(template_name):
    """템플릿 파일 읽기."""
    template_file = Path(__file__).resolve().parent.parent / "templates" / template_name
    if not template_file.exists():
        raise FileNotFoundError("Template not found: {}".format(template_file))
    return template_file.read_text()


def parse_args():
    parser = argparse.ArgumentParser(description="Shock-refine: SI to refineMesh pipeline")
    parser.add_argument("-case", required=True, type=str)
    parser.add_argument("--h_min", type=float, default=1e-3)
    parser.add_argument("--p99", action="store_true", help="Use P99 threshold for refinement")
    parser.add_argument("--refineLevel", type=int, default=1)
    parser.add_argument("-n", "--dry-run", action="store_true")
    return parser.parse_args()


def load_mesh(case_dir):
    """Step 1: VTK로 OpenFOAM 메쉬 로드."""
    import numpy as np
    from vtkmodules.vtkIOGeometry import vtkOpenFOAMReader
    from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline
    import pyvista as pv

    foam_file = case_dir / "case.foam"
    if not foam_file.exists():
        foam_file.touch()

    reader = vtkOpenFOAMReader()
    reader.SetFileName(str(foam_file))
    reader.SetCacheMesh(True)
    reader.UpdateInformation()

    info = reader.GetOutputInformation(0)
    timesteps_key = vtkStreamingDemandDrivenPipeline.TIME_STEPS()
    latest_time = 0
    n_ts = 0

    if info.Has(timesteps_key):
        n_ts = info.Length(timesteps_key)
        tv = [info.Get(timesteps_key, i) for i in range(n_ts)]
        latest_time = int(float(tv[-1]))

    print("[Step 1] Loaded {} timesteps. Using time={}".format(n_ts, latest_time))
    reader.EnableAllCellArrays()
    reader.UpdateTimeStep(latest_time)

    grid = pv.wrap(reader.GetOutput())["internalMesh"]
    n_cells = grid.n_cells
    print("[Step 1] Mesh: {} cells".format(n_cells))
    return grid, latest_time


def compute_si(grid, h_min):
    """Step 2: SI (Shock Intensity) 계산."""
    import numpy as np

    grid = grid.compute_cell_sizes(length=False, area=False, volume=True)
    vol = np.array(grid.cell_data["Volume"])
    h = np.power(vol, 1.0 / 3.0)

    grad_p_field = grid.compute_derivative(scalars="p", gradient="grad_p", preference="cell")
    grad_p = np.array(grad_p_field.cell_data["grad_p"])
    mag_grad_p = np.linalg.norm(grad_p, axis=1)

    valid_mask = h >= h_min
    n_filtered = (~valid_mask).sum()
    if n_filtered > 0:
        print("[h_min] Excluded {} cells with h < {}".format(n_filtered, h_min))

    p = np.array(grad_p_field.cell_data["p"])
    p_safe = np.where(np.abs(p) < 1e-12, 1e-12, p)
    SI = h * (mag_grad_p / np.abs(p_safe))

    return grid, SI


def extract_refine_cell_ids(SI, percentile=95):
    """Step 3: P95 percentile로 refine 대상 cellID 추출."""
    import numpy as np

    valid = SI > 0.0
    if valid.sum() == 0:
        print("[ERROR] No valid cells for SI calculation!")
        return [], 0.0

    threshold = float(np.percentile(SI[valid], percentile))
    refine_ids = [i for i, si in enumerate(SI) if si >= threshold]

    print("[Step 3] P{} threshold = {:.6e}".format(percentile, threshold))
    print("[Step 3] Refine cells: {} cells selected".format(len(refine_ids)))
    return refine_ids, threshold


def copy_case_dirs(src_dir, dst_dir):
    """Step 4: case 디렉토리 복사 (0/, system/, constant/만)."""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    for subdir in ["0", "system", "constant"]:
        src_sub = src_dir / subdir
        dst_sub = dst_dir / subdir
        if src_sub.exists():
            shutil.copytree(src_sub, dst_sub)
            print("[Step 4] Copied {}/".format(subdir))


def write_cell_set_file(refine_ids, sets_dir):
    """Step 5a: constant/polyMesh/sets/shockRefineZone (cellSet 파일)."""
    template = read_template("cellSet.template")

    count = len(refine_ids)
    ids_str = " ".join(str(cid) for cid in refine_ids)

    content = template.replace("<labelCount>", str(count))
    content = content.replace("<CELL_IDS>", ids_str)

    cell_set_file = sets_dir / "shockRefineZone"
    cell_set_file.write_text(content)
    print("[Step 5a] Created: constant/polyMesh/sets/shockRefineZone ({} cells)".format(count))


def write_topo_set_dict(refine_ids, topo_dir):
    """Step 5b: system/topoSetDict 생성 (template 기반)."""
    template = read_template("topoSetDict.template")

    ids_str = " ".join(str(cid) for cid in refine_ids)
    content = template.replace("<CELL_IDS>", ids_str)

    topo_set_file = topo_dir / "topoSetDict"
    topo_set_file.write_text(content)
    print("[Step 5b] Created: system/topoSetDict (from template)")


def write_refine_mesh_dict(refine_level, topo_dir):
    """Step 6: system/refineMeshDict 생성 (template 기반)."""
    template = read_template("refineMeshDict.template")
    content = template.replace("<REFINE_LEVEL>", str(refine_level))

    rmd_file = topo_dir / "refineMeshDict"
    rmd_file.write_text(content)
    print("[Step 6] Created: system/refineMeshDict (from template, level={})".format(refine_level))


def run_topo_set(refined_case):
    """topoSet 실행."""
    env = get_of_env()
    topo_dict = refined_case / "system" / "topoSetDict"

    print("[Step 5c] Running: topoSet -dict system/topoSetDict")
    result = subprocess.run(
        ["topoSet", "-dict", str(topo_dict)],
        cwd=str(refined_case),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] topoSet failed:")
        print(result.stderr)
        return False

    print("[Step 5c] topoSet completed successfully")
    return True


def run_refine_mesh(refined_case):
    """refineMesh 실행."""
    env = get_of_env()
    rmd_file = refined_case / "system" / "refineMeshDict"

    print("[Step 7] Running: refineMesh -dict system/refineMeshDict")
    result = subprocess.run(
        ["refineMesh", "-dict", str(rmd_file)],
        cwd=str(refined_case),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] refineMesh failed:")
        print(result.stderr)
        return False

    print("[Step 7] refineMesh completed successfully")
    return True


def main():
    args = parse_args()
    case_dir = Path(args.case).resolve()

    if not case_dir.exists():
        print("[ERROR] Case directory does not exist: {}".format(case_dir))
        return

    refined_case = case_dir.parent / "refined-case"

    print("=" * 60)
    print("SHOCK-REFINE PIPELINE (SKILL.md compliant)")
    print("case={}".format(case_dir))
    print("refined-case={}".format(refined_case))
    pct_label = "P99" if args.p99 else "P95"
    print("Refinement threshold: {}".format(pct_label))
    print("h_min={}  refineLevel={}".format(args.h_min, args.refineLevel))
    print("=" * 60)

    # Step 1: 메쉬 로드
    grid, latest_time = load_mesh(case_dir)

    # Step 2: SI 계산
    _, SI = compute_si(grid, args.h_min)

    # Step 3: refine cellID 추출
    percentile = 99 if args.p99 else 95
    refine_ids, threshold = extract_refine_cell_ids(SI, percentile=percentile)

    if not refine_ids:
        print("[ERROR] No cells to refine!")
        return

    # Step 4: case 디렉토리 복사
    copy_case_dirs(case_dir, refined_case)

    # Step 5a: cellSet 파일 생성 (FoamFile header 포함)
    sets_dir = refined_case / "constant" / "polyMesh" / "sets"
    sets_dir.mkdir(parents=True, exist_ok=True)
    write_cell_set_file(refine_ids, sets_dir)

    # Step 5b: topoSetDict 생성 (template 기반)
    topo_dir = refined_case / "system"
    topo_dir.mkdir(parents=True, exist_ok=True)
    write_topo_set_dict(refine_ids, topo_dir)

    if args.dry_run:
        print("\n[Dry-run mode] All files generated. Skipping native utilities.")
        return

    # Step 5c: topoSet 실행 (cellSet → cellZone 변환)
    if not run_topo_set(refined_case):
        return

    # Step 6: refineMeshDict 생성 + 실행
    write_refine_mesh_dict(args.refineLevel, topo_dir)

    if not run_refine_mesh(refined_case):
        return

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE!")
    print("Refined case: {}".format(refined_case))
    print("Cells refined: {} -> P95 threshold={:.6e}".format(len(refine_ids), threshold))
    print("=" * 60)


if __name__ == "__main__":
    main()
