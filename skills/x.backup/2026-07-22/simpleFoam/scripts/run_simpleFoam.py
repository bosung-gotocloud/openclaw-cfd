#!/usr/bin/env python3
"""run_simpleFoam.py - simpleFoam 해석 실행

대화 기반 실행:
1. solve_params.json 읽기 (calculate_solve_params.py가 생성)
2. mesh_path 검증
3. template 복사 → placeholder 치환 → simpleFoam 실행

Usage:
  python3 run_simpleFoam.py [solve_params.json] <case_name> [num_procs]
  
  solve_params.json은 optional. 없으면 현재 디렉토리에서 자동 검색.
"""

import json
import sys
import os
import shutil
import glob
import re
from pathlib import Path

# template 절대 경로 (skills 디렉토리는 READ-ONLY — 수정 금지)
TEMPLATE_DIR = Path("/home/bosung/.openclaw/workspace/skills/simpleFoam/assets/simpleFoam-case-template")


def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def copy_template_and_mesh(case_dir, mesh_path):
    """template 복사 + mesh 복사"""
    if not TEMPLATE_DIR.exists():
        raise FileNotFoundError(f"Template directory not found: {TEMPLATE_DIR}")

    os.makedirs(case_dir, exist_ok=True)

    # template dirs 복사
    for item in TEMPLATE_DIR.iterdir():
        if item.is_dir():
            dst = os.path.join(case_dir, item.name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(item, dst)

    # mesh 복사
    if mesh_path and os.path.isdir(mesh_path):
        poly_dst = os.path.join(case_dir, "constant", "polyMesh")
        if os.path.exists(poly_dst):
            shutil.rmtree(poly_dst)
        shutil.copytree(mesh_path, poly_dst)

    # case.foam 생성
    case_foam = os.path.join(case_dir, "case.foam")
    with open(case_foam, "w") as f:
        pass  # 빈 파일

    return case_dir


def get_surface_name_from_mesh(case_dir):
    """mesh의 polyMesh/boundary에서 surface patch name 읽어오기"""
    boundary_file = os.path.join(case_dir, "constant", "polyMesh", "boundary")
    if not os.path.isfile(boundary_file):
        return 'surface'
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    # boundary 파일에서 모든 patch name 추출
    # OpenFOAM boundary 파일: 각 patch는 "    patchname\n    {" 형태
    matches = re.findall(r'^\s+(\S+)\s*\n\s+\{', content, re.MULTILINE)
    for name in matches:
        if name not in ('far', 'internal', 'defaultFaces', 'FoamFile', ' FoamFile'):
            return name
    return 'surface'


def replace_placeholders(case_dir, params):
    """template 내 모든 placeholder 치환"""
    # 1. mesh에서 실제 surface patch name 읽기
    surface_name = get_surface_name_from_mesh(case_dir)
    params['surfaceName'] = surface_name
    print(f"  > surface patch: {surface_name}")

    placeholders = {
        '@Uvec@': f"({params['Ux']} {params['Uy']} {params['Uz']})",
        '@Uinf@': str(params['Uinf']),
        '@Ux@': str(params['Ux']),
        '@Uy@': str(params['Uy']),
        '@Uz@': str(params['Uz']),
        '@surface_BC@': str(params.get('surfaceBC', 'wall')),
        '@kIni@': str(params['k_ini']),
        '@omegaIni@': str(params['omega_ini']),
        '@nu@': str(params['nu']),
        '@turbModel@': str(params['turbModel']),
        '@endTime@': str(params['endTime']),
        '@deltaT@': str(params['deltaT']),
        '@writeInterval@': str(params['writeInterval']),
        '@magUInf@': str(params['magUInf']),
        '@lRef@': '1.0',
        '@Aref@': str(params['Aref']),
        '@surfaceName@': str(surface_name),
        '@rhoInf@': str(params['rho']),
        '@nSubdomains@': str(params.get('num_procs', 1) if params.get('num_procs', 1) > 1 else 1),
        '@CofRx@': str(params.get('CofR_x', 0)),
        '@CofRy@': str(params.get('CofR_y', 0)),
        '@CofRz@': str(params.get('CofR_z', 0)),
    }

    # 2. 모든 파일 치환
    for root, dirs, files in os.walk(case_dir):
        # Skip polyMesh directory - binary files cause decode errors
        if 'polyMesh' in root:
            continue
        for fname in files:
            if fname == '.gitkeep':
                continue
            fpath = os.path.join(root, fname)
            try:
                text = open(fpath, 'r').read()
            except (UnicodeDecodeError, PermissionError):
                continue
            for ph, val in placeholders.items():
                text = text.replace(ph, val)
            open(fpath, 'w').write(text)

    print(f"  > All placeholders replaced")


def create_decomposePar_dict(case_dir, num_procs):
    """decomposeParDict 생성"""
    decomp_path = os.path.join(case_dir, "system", "decomposeParDict")
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposePar;
}}

numberOfSubdomains  {num_procs};

method          scotch;
"""
    with open(decomp_path, 'w') as f:
        f.write(content)



def run_parallel_simplefoam(case_dir, num_procs):
    """simpleFoam 병렬 실행"""
    print("  Running decomposePar...")
    cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && decomposePar -force 2>&1 | tee log.decomposePar'"
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: decomposePar failed (exit {ret})")
        return False

    print(f"  Running simpleFoam parallel ({num_procs} procs)...")
    cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && mpirun -np {num_procs} --oversubscribe simpleFoam -parallel 2>&1 | tee log.simpleFoam'"
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: simpleFoam failed (exit {ret})")
        return False

    print("  Running reconstructPar...")
    ret = os.system(f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && reconstructPar 2>&1 | tee log.reconstructPar'")
    if ret != 0:
        print(f"  WARNING: reconstructPar failed (exit {ret})")

    proc_dirs = glob.glob(os.path.join(case_dir, "processor*"))
    for pd in proc_dirs:
        shutil.rmtree(pd)

    return True


def run_single_simplefoam(case_dir):
    """simpleFoam 단일 프로세스 실행"""
    print("  Running simpleFoam (serial)...")
    cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && simpleFoam 2>&1 | tee log.simpleFoam'"
    ret = os.system(cmd)
    if ret != 0:
        print(f"  ERROR: simpleFoam failed (exit {ret})")
        return False
    return True


def main():
    # Resolve solve_params.json
    solve_params_path = None
    if len(sys.argv) >= 2:
        candidate = sys.argv[1]
        if os.path.isfile(candidate):
            solve_params_path = candidate
        elif candidate.endswith('_solve_params.json'):
            if os.path.isfile(candidate):
                solve_params_path = candidate

    if solve_params_path is None:
        for c in ["solve_params.json", "input_solve_params.json", "input.json"]:
            if os.path.isfile(c):
                solve_params_path = c
                break

    if solve_params_path is None:
        print("ERROR: No solve_params.json found.")
        print("Run calculate_solve_params.py first.")
        print("\nUsage: python3 run_simpleFoam.py [solve_params.json] <case_name> [num_procs]")
        sys.exit(1)

    params = read_json(solve_params_path)

    case_name = sys.argv[2] if len(sys.argv) >= 3 else "simpleFoam_case"
    num_procs = int(sys.argv[3]) if len(sys.argv) >= 4 else 0

    # Mesh validation
    mesh_path = params.get('meshPath', '')
    if not mesh_path or not os.path.isdir(mesh_path):
        print(f"\nERROR: mesh not found: {mesh_path}")
        sys.exit(1)

    # OUTPUT_BASE — 사용자가 명시한 디렉토리 (solve_params.json output_dir)
    # None → 현재 디렉토리 (cwd)
    output_dir = params.get('output_dir')
    if output_dir is None or not os.path.isdir(output_dir):
        output_dir = os.getcwd()

    # Prepare case
    print("\n=== Preparing case ===")
    case_dir = os.path.join(output_dir, "case")
    case_dir = copy_template_and_mesh(case_dir, mesh_path)
    print(f"  > polyMesh copied from: {mesh_path}")

    # Replace placeholders (reads actual patch name from mesh)
    replace_placeholders(case_dir, params)

    # Determine procs
    if num_procs == 0:
        num_procs = params.get('num_procs', 1)
        if num_procs <= 1:
            num_procs = 1

    # Run
    print("=== Running solver ===")
    if num_procs > 1:
        create_decomposePar_dict(case_dir, num_procs)
        success = run_parallel_simplefoam(case_dir, num_procs)
    else:
        success = run_single_simplefoam(case_dir)

    if success:
        print(f"\n=== COMPLETE ===")
        print(f"Case: {case_dir}")
    else:
        print(f"\n=== FAILED ===")
        print(f"Check logs: {os.path.join(case_dir, 'log.simpleFoam')}")

if __name__ == '__main__':
    main()
