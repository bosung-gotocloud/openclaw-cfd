#!/usr/bin/env python3
"""run_hisa.py - HiSA (High Speed Aerodynamic) solver workflow

Workflow:
  1. JSON 파라미터 읽기 (solve_params.json 자동 검색)
  2. 템플릿 복사 + mesh 복사
  3. Placeholder 치환 (@Uvec@, @pInf@, @surfaceName@, 등 25개)
  4. parallel hisa 실행 (decomposePar + mpirun + reconstructPar → processor* cleanup)

Usage:
  python3 run_hisa.py [solve_params.json]

output_dir: 스크립트가 복사되어 실행되는 디렉토리 (calculate_solve_params.py와 동일).
"""

import json
import sys
import os
import shutil
import re
import math
import subprocess
from pathlib import Path

TEMPLATE_DIR = Path("/home/bosung/.openclaw/workspace/skills/hisa/templates")


def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def get_surface_name_from_mesh(case_dir):
    """메쉬 boundary 파일에서 far/ internal 제외하고 surface patch 이름 추출."""
    boundary_file = os.path.join(case_dir, "constant", "polyMesh", "boundary")
    if not os.path.isfile(boundary_file):
        return 'surface'
    with open(boundary_file, 'r') as f:
        content = f.read()
    matches = re.findall(r'^\s+(\S+)\s*\n\s*\{', content, re.MULTILINE)
    for name in matches:
        if name not in ('far', 'internal', 'defaultFaces', 'FoamFile', 'object'):
            return name
    return 'surface'


def create_output_dir(script_dir):
    """output_dir 생성 (스크립트 실행 디렉토리) + case/ 서브디렉토리 + case.foam 파일."""
    case_dir = os.path.join(script_dir, "case")
    os.makedirs(case_dir, exist_ok=True)
    # case.foam 파일 생성 (OpenFOAM case 식별용)
    foam_file = os.path.join(case_dir, "case.foam")
    with open(foam_file, 'w') as f:
        f.write("")
    return case_dir


def copy_template_and_mesh(case_dir, mesh_path):
    """template 복사 + mesh 복사."""
    if not TEMPLATE_DIR.exists():
        raise FileNotFoundError(f"Template directory not found: {TEMPLATE_DIR}")
    
    os.makedirs(case_dir, exist_ok=True)

    for item in TEMPLATE_DIR.iterdir():
        if item.is_dir():
            dst = os.path.join(case_dir, item.name)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
    
    if mesh_path and os.path.isdir(mesh_path):
        poly_dst = os.path.join(case_dir, "constant", "polyMesh")
        if os.path.exists(poly_dst):
            shutil.rmtree(poly_dst)
        shutil.copytree(mesh_path, poly_dst)
    return case_dir


def create_decomposePar_dict(case_dir, n_procs):
    """decomposeParDict 생성 (parallel 실행용)."""
    system_dir = os.path.join(case_dir, "system")
    decompose_path = os.path.join(system_dir, "decomposeParDict")
    
    # 기존 decomposeParDict에 numberOfSubdomains만 업데이트
    with open(decompose_path, 'r') as f:
        content = f.read()
    content = content.replace('@nSubdomains@', str(n_procs))
    
    with open(decompose_path, 'w') as f:
        f.write(content)


def replace_placeholders(case_dir, params):
    """모든 placeholder 치환 (25개)."""
    surface_name = get_surface_name_from_mesh(case_dir)
    params['surfaceName'] = surface_name
    
    placeholders = {
        '@Uvec@': f"({params['Ux']} {params['Uy']} {params['Uz']})",
        '@Uinf@': str(params['Uinf']),
        '@Ux@': str(params['Ux']),
        '@Uy@': str(params['Uy']),
        '@Uz@': str(params['Uz']),
        '@surfaceName@': str(surface_name),
        '@pInf@': str(params['pInf']),
        '@T@': str(params['T']),
        '@kIni@': str(params['k_ini']),
        '@omegaIni@': str(params['omega_ini']),
        '@intensity@': str(params.get('intensity', params.get('turbulence', {}).get('intensity', 0.01))),
        '@mixingLength@': str(params.get('mixingLength', params.get('turbulence', {}).get('lengthScale', 0.1))),
        '@endTime@': str(params['endTime']),
        '@writeInterval@': str(params['writeInterval']),
        '@CofRx@': str(params['CofR_x']),
        '@CofRy@': str(params['CofR_y']),
        '@CofRz@': str(params['CofR_z']),
        '@Aref@': str(params.get('Aref', params.get('A_ref', 1.0))),
        '@lRef@': str(params.get('lRef', params.get('L_ref', 1.0))),
        '@magUInf@': str(params.get('magUInf', params.get('Uinf', 0))),
        '@rhoInf@': str(params['rho']),
        '@rho@': str(params['rho']),
        '@nSubdomains@': str(params.get('num_procs', 1)),
        '@nu@': str(params['nu']),
        '@pseudoCoNum@': str(params.get('pseudoCoNum', 1)),
        '@pseudoCoNumMax@': str(params.get('pseudoCoNumMax', 10000)),
        '@timeScheme@': str(params.get('timeScheme', 'steadyState')),
        '@surface_BC@': str(params['surfaceBC']),
    }

    for root, dirs, files in os.walk(case_dir):
        if 'polyMesh' in root:
            continue
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r') as f:
                    text = f.read()
                changed = False
                for ph, val in placeholders.items():
                    if ph in text:
                        text = text.replace(ph, val)
                        changed = True
                if changed:
                    with open(fpath, 'w') as f:
                        f.write(text)
            except Exception:
                continue


def run_parallel_hisa(case_dir, n_procs):
    """HiSA parallel 실행: decomposePar → mpirun hisa -parallel → reconstructPar → processor* 삭제."""
    print(f"\n  === Parallel HiSA ({n_procs} procs) ===")
    
    # 1. decomposePar
    print(f"  [1/4] decomposePar...")
    cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && decomposePar -force 2>&1 | tee log.decomposePar'"
    ret = os.system(cmd)
    if ret != 0:
        print("  ERROR: decomposePar failed.")
        return ret
    
    # 2. parallel hisa — bash -c + 파일 리다이렉트 (SIGPIPE 방지 + env 전파)
    print(f"  [2/4] mpirun hisa -parallel ({n_procs} procs)...")

    log_path = os.path.join(case_dir, 'log.hisa')
    cmd = (
        f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
        f"cd {case_dir} && "
        f"mpirun -np {n_procs} --oversubscribe hisa -parallel "
        f"> log.hisa 2>&1'"
    )
    ret = os.system(cmd)
    
    # 3. reconstructPar
    if ret == 0:
        print(f"  [3/4] reconstructPar...")
        cmd = f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd {case_dir} && reconstructPar 2>&1 | tee log.reconstructPar'"
        ret = os.system(cmd)
    
    # 4. processor directories 제거
    print(f"  [4/4] Cleanup processor* directories...")
    for item in os.listdir(case_dir):
        if item.startswith('processor'):
            path = os.path.join(case_dir, item)
            if os.path.isdir(path):
                shutil.rmtree(path)
    
    return ret


def main():
    # 실행 디렉토리 (스크립트가 복사되어 실행되는 곳)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    args = sys.argv[1:]
    
    # JSON 경로 자동 검색 (실행 디렉토리 기준)
    json_path = None
    search_paths = ["solve_params.json"]
    if len(args) >= 1:
        json_path = args[0]
    else:
        candidate = os.path.join(script_dir, "solve_params.json")
        if os.path.isfile(candidate):
            json_path = candidate
    
    if not json_path or not os.path.isfile(json_path):
        print(f"ERROR: solve_params.json not found in {script_dir}")
        print(f"  Run: python3 calculate_solve_params.py")
        sys.exit(1)
    
    print(f"\n=== HiSA Workflow Start ===")
    print(f"  Script dir: {script_dir}")
    print(f"  JSON: {json_path}")
    params = read_json(json_path)
    
    # --- AoA & AoS Velocity Calculation (Corrected) ---
    u_inf = params['Uinf']
    aoa_rad = math.radians(params.get('AoA', 0))
    aos_rad = math.radians(params.get('AoS', 0))
    
    params['Ux'] = u_inf * math.cos(aoa_rad) * math.cos(aos_rad)
    params['Uy'] = u_inf * math.sin(aoa_rad)
    params['Uz'] = u_inf * math.cos(aoa_rad) * math.sin(aos_rad)
    
    # output_dir: JSON에서 읽은 값 (script_dir과 동일)
    output_dir = params.get('output_dir', script_dir)
    if output_dir is None or not os.path.isdir(output_dir):
        output_dir = script_dir
    
    # case_dir 생성 (create_output_dir가 case/ + case.foam 생성)
    case_dir = create_output_dir(output_dir)
    mesh_path = params.get('meshPath', '')
    
    # 1. copy template
    print(f"\n  Copying templates to {case_dir}...")
    copy_template_and_mesh(case_dir, mesh_path)
    
    # 2. replace placeholders
    print(f"  Replacing placeholders...")
    replace_placeholders(case_dir, params)
    
    # Display
    print(f"\n  Calculated Velocity: Ux={params['Ux']:.6f}, Uy={params['Uy']:.6f}, Uz={params['Uz']:.6f}")
    print(f"  AoA: {params.get('AoA', 0)}, AoS: {params.get('AoS', 0)}")
    print(f"  Surface: {params['surfaceName']}")
    print(f"  T: {params.get('T', 293.15)}, pInf: {params.get('pInf', 101325)}")
    
    # 3. JSON에서 num_procs 읽어와 parallel 실행
    n_procs = params.get('num_procs', 1)
    if n_procs < 1:
        n_procs = 1
    
    create_decomposePar_dict(case_dir, n_procs)
    ret = run_parallel_hisa(case_dir, n_procs)
    
    if ret == 0:
        print(f"\n=== PARALLEL SUCCESS ===")
    else:
        print(f"\n=== PARALLEL FAILED (exit {ret}) ===")
        sys.exit(ret)
    
    print(f"\n=== DONE ===")


if __name__ == '__main__':
    main()
