#!/usr/bin/env python3
"""run_simpleFoam_adm.py - simpleFoam ADM (Actuator Disk Model) solver workflow

Workflow (per SKILL.md):
  1. JSON 파라미터 읽기 (adm_params.json 자동 검색)
  2. 템플릿 복사 + mesh 복사
  3. Placeholder 치환 (adm_params 기반)
  4. topoSet 실행 → cellZone 생성
  5. decomposePar → mpirun simpleFoam -parallel → reconstructPar → cleanup

diskDir is user input (normalize). upstreamPoint = diskCenter + diskDir×0.01×radius
"""

import json
import sys
import os
import shutil
import re
import math
from pathlib import Path

TEMPLATE_DIR = Path("/home/bosung/.openclaw/workspace/skills/simpleFoam-adm/assets/simpleFoam-adm-case-template")


def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def get_surface_name_from_mesh(case_dir):
    """메쉬 boundary 파일에서 surface patch 이름 추출."""
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
    """case/ 서브디렉토리 + case.foam 파일 생성."""
    case_dir = os.path.join(script_dir, "case")
    os.makedirs(case_dir, exist_ok=True)
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
    """decomposeParDict numberOfSubdomains 업데이트."""
    decompose_path = os.path.join(case_dir, "system", "decomposeParDict")
    with open(decompose_path, 'r') as f:
        content = f.read()
    content = content.replace('@nSubdomains@', str(n_procs))
    with open(decompose_path, 'w') as f:
        f.write(content)


def replace_placeholders(case_dir, params):
    """모든 placeholder 치환 (adm_params.json 기반)."""
    surface_name = get_surface_name_from_mesh(case_dir)

    adm = params['ADM']
    flow = params['flow']
    turb = params['turbulence']
    ref = params['reference']
    cofr = params['CofR']

    # diskDir: user 입력, 자동 normalize
    diskDir_x = adm.get('diskDirX', 1.0)
    diskDir_y = adm.get('diskDirY', 0.0)
    diskDir_z = adm.get('diskDirZ', 0.0)
    mag = math.sqrt(diskDir_x**2 + diskDir_y**2 + diskDir_z**2)
    diskDir_x /= mag
    diskDir_y /= mag
    diskDir_z /= mag

    # upstreamPoint = diskCenter + diskDir × epsilon (upstream: diskDir direction, incoming velocity 측정)
    epsilon = adm['radius'] * 0.01
    upstream_x = adm['centerX'] + diskDir_x * epsilon
    upstream_y = adm['centerY'] + diskDir_y * epsilon
    upstream_z = adm['centerZ'] + diskDir_z * epsilon

    placeholders = {
        # ADM
        '@ADM_centerX@': f"{adm['centerX']}",
        '@ADM_centerY@': f"{adm['centerY']}",
        '@ADM_centerZ@': f"{adm['centerZ']}",
        '@ADM_diskDirX@': f"{diskDir_x}",
        '@ADM_diskDirY@': f"{diskDir_y}",
        '@ADM_diskDirZ@': f"{diskDir_z}",
        '@ADM_radius@': f"{adm['radius']}",
        '@ADM_diskArea@': f"{math.pi * adm['radius']**2}",
        '@ADM_Ct@': f"{adm['Ct']}",
        '@ADM_Cp@': f"{adm['Cp']}",
        '@ADM_upstreamPointX@': f"{upstream_x:.8f}",
        '@ADM_upstreamPointY@': f"{upstream_y:.8f}",
        '@ADM_upstreamPointZ@': f"{upstream_z:.8f}",
        '@ADM_centre2X@': f"{adm['centerX'] + diskDir_x * 0.005}",
        '@ADM_centre2Y@': f"{adm['centerY'] + diskDir_y * 0.005}",
        '@ADM_centre2Z@': f"{adm['centerZ'] + diskDir_z * 0.005}",
        '@ADM_cylinderRadius@': f"{adm['radius'] * 1.05}",

        # Flow
        '@Uvec@': f"({flow['Ux']} {flow['Uy']} {flow['Uz']})",
        '@Uinf@': f"{flow['Uinf']}",

        # Turbulence
        '@kIni@': f"{turb['k_ini']}",
        '@omegaIni@': f"{turb['omega_ini']}",

        # Fluid
        '@nu@': f"{params['fluid']['nu']}",
        '@rhoInf@': f"{params['fluid']['rho']}",
        '@rho@': f"{params['fluid']['rho']}",

        # Run
        '@endTime@': f"{params['run']['endTime']}",
        '@deltaT@': f"{params['run']['deltaT']}",
        '@writeInterval@': f"{params['run']['writeInterval']}",

        # Reference
        '@CofRx@': f"{cofr['x']}",
        '@CofRy@': f"{cofr['y']}",
        '@CofRz@': f"{cofr['z']}",
        '@lRef@': f"{ref['L_ref']}",
        '@Aref@': f"{ref['A_ref']}",
        '@magUInf@': f"{flow['Uinf']}",

        # Surface
        '@surfaceName@': surface_name,

        # Parallel
        '@nSubdomains@': f"{params['num_procs']}",
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


def run_parallel_simpleFoam(case_dir, n_procs, params):
    """simpleFoam parallel 실행."""
    print(f"\n  === Parallel simpleFoam ({n_procs} procs) ===")

    # 0. topoSet 실행 (cellZone 생성)
    topo_config = params.get('topoSet', {})
    topo_enabled = topo_config.get('enabled', True)
    if topo_enabled:
        topoDict_path = os.path.join(case_dir, "system", "topoSetDict")
        if os.path.isfile(topoDict_path):
            print(f"  [0/5] topoSet (cellZone 생성)...")
            cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
                   f"cd {case_dir} && topoSet 2>&1 | tee log.topoSet'")
            ret = os.system(cmd)
            if ret != 0:
                print("  ERROR: topoSet failed.")
                return ret
        else:
            print(f"  WARNING: topoSetDict not found at {topoDict_path}, skipping topoSet")
    
    # 1. decomposePar
    print(f"  [1/5] decomposePar...")
    cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
           f"cd {case_dir} && decomposePar -force 2>&1 | tee log.decomposePar'")
    ret = os.system(cmd)
    if ret != 0:
        print("  ERROR: decomposePar failed.")
        return ret

    # 2. parallel simpleFoam
    print(f"  [2/5] mpirun simpleFoam -parallel ({n_procs} procs)...")
    cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
           f"cd {case_dir} && mpirun --oversubscribe -np {n_procs} simpleFoam -parallel > log.simpleFoam 2>&1'")
    ret = os.system(cmd)

    # 3. reconstructPar
    if ret == 0:
        print(f"  [3/5] reconstructPar...")
        cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
               f"cd {case_dir} && reconstructPar 2>&1 | tee log.reconstructPar'")
        ret = os.system(cmd)

    # 4. processor directories 제거
    print(f"  [4/5] Cleanup processor* directories...")
    for item in os.listdir(case_dir):
        if item.startswith('processor'):
            path = os.path.join(case_dir, item)
            if os.path.isdir(path):
                shutil.rmtree(path)

    return ret


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    args = sys.argv[1:]

    # JSON 자동 검색
    json_path = None
    search_paths = ["adm_params.json"]
    if len(args) >= 1:
        json_path = args[0]
    else:
        candidate = os.path.join(script_dir, "adm_params.json")
        if os.path.isfile(candidate):
            json_path = candidate

    if not json_path or not os.path.isfile(json_path):
        print(f"ERROR: adm_params.json not found in {script_dir}")
        print(f"  Run: python3 calculate_adm_params.py")
        sys.exit(1)

    print(f"\n=== simpleFoam ADM Workflow Start ===")
    print(f"  Script dir: {script_dir}")
    print(f"  JSON: {json_path}")
    params = read_json(json_path)

    adm = params['ADM']
    output_dir = params.get('output_dir', script_dir)
    if output_dir is None or not os.path.isdir(output_dir):
        output_dir = script_dir

    case_dir = create_output_dir(output_dir)
    mesh_path = params.get('meshPath', '')

    # 1. copy template
    print(f"\n  Copying templates to {case_dir}...")
    copy_template_and_mesh(case_dir, mesh_path)

    # 2. replace placeholders (all: ADM, flow, turbulence, upstreamPoint, topoSet, etc.)
    print(f"  Replacing placeholders...")
    replace_placeholders(case_dir, params)

    # Display summary
    diskDir_x = adm.get('diskDirX', 1.0)
    diskDir_y = adm.get('diskDirY', 0.0)
    diskDir_z = adm.get('diskDirZ', 0.0)
    mag = math.sqrt(diskDir_x**2 + diskDir_y**2 + diskDir_z**2)
    diskDir_x /= mag
    diskDir_y /= mag
    diskDir_z /= mag
    epsilon = adm['radius'] * 0.01
    upstream_x = adm['centerX'] + diskDir_x * epsilon
    upstream_y = adm['centerY'] + diskDir_y * epsilon
    upstream_z = adm['centerZ'] + diskDir_z * epsilon

    print(f"\n  === ADM Parameters ===")
    print(f"  Disk center: ({adm['centerX']}, {adm['centerY']}, {adm['centerZ']}) m")
    print(f"  diskDir (thrust direction): ({diskDir_x:.6f}, {diskDir_y:.6f}, {diskDir_z:.6f}) [user input, auto-normalized]")
    print(f"  upstreamPoint: ({upstream_x:.8f}, {upstream_y:.8f}, {upstream_z:.8f}) m  [upstream: diskDir direction, incoming velocity 측정]")
    print(f"  Disk radius: {adm['radius']:.4f} m")
    print(f"  Ct: {adm['Ct']:.4f}, Cp: {adm['Cp']:.4f}")

    flow = params['flow']
    print(f"\n  Flow: Uinf={flow['Uinf']:.4f} m/s, AoA={flow['AoA']:.2f} deg, AoS={flow['AoS']:.2f} deg")
    print(f"  U = ({flow['Ux']:.6f}, {flow['Uy']:.6f}, {flow['Uz']:.6f})")
    print(f"  k={params['turbulence']['k_ini']:.8e}, omega={params['turbulence']['omega_ini']:.4f}")

    # 3. parallel execution
    n_procs = params.get('num_procs', 1)
    if n_procs < 1:
        n_procs = 1

    create_decomposePar_dict(case_dir, n_procs)
    ret = run_parallel_simpleFoam(case_dir, n_procs, params)

    if ret == 0:
        print(f"\n=== PARALLEL SUCCESS ===")
    else:
        print(f"\n=== PARALLEL FAILED (exit {ret}) ===")
        sys.exit(ret)

    print(f"\n=== DONE ===")


if __name__ == '__main__':
    main()
