#!/usr/bin/env python3
"""run_hisa_adm.py - HiSA (High Speed Aerodynamic) ADM solver workflow

HiSA (compressible, kOmegaSST, AUSMPlusUp, pseudoTime) + Actuator Disk Model.

Workflow:
  1. JSON 파라미터 읽기 (adm_params.json 자동 검색)
  2. 템플릿 복사 + mesh 복사
  3. Placeholder 치환 (@Uvec@, @pInf@, @T@, @ADM_*@, @surfaceName@, etc.)
  4. topoSet 실행 → cellZone 생성 (actuatorDiskZone)
  5. decomposePar → mpirun hisa -parallel → reconstructPar → processor* cleanup

diskDir is user input (auto-normalized). upstreamPoint = diskCenter + diskDir x 0.1*radius
"""

import json
import sys
import os
import shutil
import re
import math
import subprocess
import time
from pathlib import Path

TEMPLATE_DIR = Path("/home/bosung/.openclaw/workspace/skills/hisa-adm/templates")


def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def get_surface_name_from_mesh(case_dir):
    """Mesh boundary file: extract surface patch name (exclude far/internal)."""
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
    """Create case/ subdir + case.foam file."""
    case_dir = os.path.join(script_dir, "case")
    os.makedirs(case_dir, exist_ok=True)
    foam_file = os.path.join(case_dir, "case.foam")
    with open(foam_file, 'w') as f:
        f.write("")
    return case_dir


def copy_template_and_mesh(case_dir, mesh_path):
    """Copy template + mesh to case dir."""
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
    """Update decomposeParDict numberOfSubdomains."""
    decompose_path = os.path.join(case_dir, "system", "decomposeParDict")
    with open(decompose_path, 'r') as f:
        content = f.read()
    content = content.replace('@nSubdomains@', str(n_procs))
    with open(decompose_path, 'w') as f:
        f.write(content)


def replace_placeholders(case_dir, params):
    """Replace all placeholders (ADM + HiSA compressible + flow + turbulence + run)."""
    surface_name = get_surface_name_from_mesh(case_dir)

    adm = params['ADM']
    flow = params['flow']
    turb = params['turbulence']
    ref = params['reference']
    cofr = params['CofR']
    thermo = params.get('thermodynamic', {"T": 293.15, "pInf": 101325})

    # diskDir: user input, auto-normalize
    diskDir_x = adm.get('diskDirX', 1.0)
    diskDir_y = adm.get('diskDirY', 0.0)
    diskDir_z = adm.get('diskDirZ', 0.0)
    mag = math.sqrt(diskDir_x**2 + diskDir_y**2 + diskDir_z**2)
    diskDir_x /= mag
    diskDir_y /= mag
    diskDir_z /= mag

    # upstreamPoint: 0.1R in diskDir + 0.75R perpendicular to disk
    dx, dy, dz = diskDir_x, diskDir_y, diskDir_z
    if abs(dy) < 0.99:
        px, py, pz = 0.0, 1.0, 0.0
    else:
        px, py, pz = 1.0, 0.0, 0.0
    cx = dy*pz - dz*py; cy = dz*px - dx*pz; cz = dx*py - dy*px
    cn = math.sqrt(cx*cx + cy*cy + cz*cz)
    cx, cy, cz = cx/cn, cy/cn, cz/cn
    off_disk = adm['radius'] * 0.1
    off_perp = adm['radius'] * 0.75
    upstream_x = adm['centerX'] + dx*off_disk + cx*off_perp
    upstream_y = adm['centerY'] + dy*off_disk + cy*off_perp
    upstream_z = adm['centerZ'] + dz*off_disk + cz*off_perp

    # disk thickness = 10% of radius (for topoSet cylinder)
    disk_thickness = adm['radius'] * 0.1

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
        '@ADM_centre2X@': f"{adm['centerX'] + diskDir_x * disk_thickness:.8f}",
        '@ADM_centre2Y@': f"{adm['centerY'] + diskDir_y * disk_thickness:.8f}",
        '@ADM_centre2Z@': f"{adm['centerZ'] + diskDir_z * disk_thickness:.8f}",
        '@ADM_cylinderRadius@': f"{adm['radius'] * 1.05}",

        # Flow
        '@Uvec@': f"({flow['Ux']} {flow['Uy']} {flow['Uz']})",
        '@Uinf@': f"{flow['Uinf']}",
        '@Ux@': f"{flow['Ux']}",
        '@Uy@': f"{flow['Uy']}",
        '@Uz@': f"{flow['Uz']}",

        # HiSA compressible (thermodynamic)
        '@pInf@': f"{thermo['pInf']}",
        '@T@': f"{thermo['T']}",

        # Turbulence
        '@kIni@': f"{turb['k_ini']}",
        '@omegaIni@': f"{turb['omega_ini']}",
        '@intensity@': f"{turb['intensity']}",
        '@mixingLength@': f"{turb['lengthScale']}",

        # Fluid
        '@nu@': f"{params['fluid']['nu']}",
        '@rhoInf@': f"{params['fluid']['rho']}",
        '@rho@': f"{params['fluid']['rho']}",

        # Run
        '@endTime@': f"{params['run']['endTime']}",
        '@deltaT@': f"{params['run']['deltaT']}",
        '@writeInterval@': f"{params['run']['writeInterval']}",
        '@pseudoCoNum@': f"{params['run']['pseudoCoNum']}",
        '@pseudoCoNumMax@': f"{params['run']['pseudoCoNumMax']}",
        '@timeScheme@': f"{params['run']['timeScheme']}",

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


def run_parallel_hisa(case_dir, n_procs, params):
    """HiSA parallel execution: topoSet → decomposePar → mpirun hisa -parallel → reconstructPar → cleanup.

    2026-09-10: mpirun detached with setsid + nohup, poll loop to wait.
    - mpirun survives even if openclaw/python session ends (new session, reparented to PID 1)
    - stdout/stderr → log.hisa direct redirect (no pipe → SIGKILL/OOM prevention)
    - poll loop waits for process end, then checks exit code
    """
    print(f"\n  === Parallel HiSA ADM ({n_procs} procs) ===")

    # 0. topoSet (cellZone creation)
    topo_config = params.get('topoSet', {})
    topo_enabled = topo_config.get('enabled', True)
    if topo_enabled:
        topoDict_path = os.path.join(case_dir, "system", "topoSetDict")
        if os.path.isfile(topoDict_path):
            print(f"  [0/5] topoSet (cellZone creation)...")
            cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
                   f"cd {case_dir} && topoSet > log.topoSet 2>&1'")
            ret = os.system(cmd)
            if ret != 0:
                print("  ERROR: topoSet failed.")
                try:
                    with open(os.path.join(case_dir, 'log.topoSet'), 'r') as f:
                        print(f.read())
                except Exception:
                    pass
                return ret
        else:
            print(f"  WARNING: topoSetDict not found at {topoDict_path}, skipping topoSet")

    # 1. decomposePar
    print(f"  [1/5] decomposePar...")
    cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
           f"cd {case_dir} && decomposePar -force > log.decomposePar 2>&1'")
    ret = os.system(cmd)
    if ret != 0:
        print("  ERROR: decomposePar failed.")
        return ret

    # 2. parallel hisa — setsid+nohup detach, poll loop
    print(f"  [2/5] mpirun hisa -parallel ({n_procs} procs)...")
    case_dir_abs = os.path.abspath(case_dir)
    cmd = (
        f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
        f"cd {case_dir_abs} && "
        f"setsid nohup mpirun -np {n_procs} --oversubscribe hisa -parallel "
        f"> log.hisa 2>&1'"
    )
    proc = subprocess.Popen(cmd, shell=True, start_new_session=True)
    last_poll = time.time()
    while proc.poll() is None:
        time.sleep(1)
        if time.time() - last_poll >= 300:
            try:
                with open(os.path.join(case_dir, 'log.hisa'), 'r') as f:
                    lines = f.readlines()
                print(f"  [HiSA] Running... (last 3 lines)\n" + '\n'.join(lines[-3:]))
            except (FileNotFoundError, IOError):
                print(f"  [HiSA] Running...")
            last_poll = time.time()
    ret = proc.returncode

    # 3. reconstructPar — only if hisa succeeded
    if ret == 0:
        print(f"  [3/5] reconstructPar...")
        cmd = (f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
               f"cd {case_dir} && reconstructPar > log.reconstructPar 2>&1'")
        ret = os.system(cmd)
    else:
        print(f"  [3/5] reconstructPar SKIPPED (hisa failed, exit={ret})")

    # 4. Cleanup processor* directories
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

    # Auto-detect JSON
    json_path = None
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

    print(f"\n=== HiSA ADM Workflow Start ===")
    print(f"  Script dir: {script_dir}")
    print(f"  JSON: {json_path}")
    params = read_json(json_path)

    # --- AoA & AoS Velocity Calculation (same as run_hisa.py) ---
    flow = params['flow']
    u_inf = flow['Uinf']
    aoa_rad = math.radians(flow.get('AoA', 0))
    aos_rad = math.radians(flow.get('AoS', 0))
    flow['Ux'] = u_inf * math.cos(aoa_rad) * math.cos(aos_rad)
    flow['Uy'] = u_inf * math.sin(aos_rad)
    flow['Uz'] = u_inf * math.cos(aoa_rad) * math.sin(aos_rad)

    # --- Turbulence k/omega Calculation (same as run_hisa.py) ---
    turb = params['turbulence']
    if 'k_ini' not in turb:
        I = turb.get('intensity', 0.01)
        turb['k_ini'] = 1.5 * (I * u_inf) ** 2
    if 'omega_ini' not in turb:
        Cmu = 0.09
        L = turb.get('lengthScale', 1.0)
        turb['omega_ini'] = math.sqrt(turb['k_ini']) / (Cmu ** 0.25) / L

    adm = params['ADM']
    output_dir = params.get('output_dir', script_dir)
    if output_dir is None or not os.path.isdir(output_dir):
        output_dir = script_dir

    case_dir = create_output_dir(output_dir)
    mesh_path = params.get('meshPath', '')

    # 1. copy template + mesh
    print(f"\n  Copying templates to {case_dir}...")
    copy_template_and_mesh(case_dir, mesh_path)

    # 2. replace placeholders (all: ADM, HiSA compressible, flow, turbulence, upstreamPoint, topoSet)
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
    r = adm['radius']
    off_along = r * 0.1
    off_perp  = r * 0.75
    ref_x, ref_y, ref_z = 0.0, 1.0, 0.0
    if abs(diskDir_x*ref_x + diskDir_y*ref_y + diskDir_z*ref_z) > 0.9:
        ref_x, ref_y, ref_z = 1.0, 0.0, 0.0
    px = diskDir_y*ref_z - diskDir_z*ref_y
    py = diskDir_z*ref_x - diskDir_x*ref_z
    pz = diskDir_x*ref_y - diskDir_y*ref_x
    pn = math.sqrt(px*px + py*py + pz*pz)
    px, py, pz = px/pn, py/pn, pz/pn
    upstream_x = adm['centerX'] + diskDir_x*off_along + px*off_perp
    upstream_y = adm['centerY'] + diskDir_y*off_along + py*off_perp
    upstream_z = adm['centerZ'] + diskDir_z*off_along + pz*off_perp

    print(f"\n  === ADM Parameters ===")
    print(f"  Disk center: ({adm['centerX']}, {adm['centerY']}, {adm['centerZ']}) m")
    print(f"  diskDir (thrust direction): ({diskDir_x:.6f}, {diskDir_y:.6f}, {diskDir_z:.6f}) [user input, auto-normalized]")
    print(f"  upstreamPoint: ({upstream_x:.8f}, {upstream_y:.8f}, {upstream_z:.8f}) m  [upstream: diskDir direction, incoming velocity measurement]")
    print(f"  Disk radius: {adm['radius']:.4f} m")
    print(f"  Ct: {adm['Ct']:.4f}, Cp: {adm['Cp']:.4f}")

    flow = params['flow']
    print(f"\n  Flow: Uinf={flow['Uinf']:.4f} m/s, AoA={flow['AoA']:.2f} deg, AoS={flow['AoS']:.2f} deg")
    print(f"  U = ({flow['Ux']:.6f}, {flow['Uy']:.6f}, {flow['Uz']:.6f})")
    print(f"  k={params['turbulence']['k_ini']:.8e}, omega={params['turbulence']['omega_ini']:.4f}")

    thermo = params.get('thermodynamic', {"T": 293.15, "pInf": 101325})
    print(f"  T={thermo['T']:.2f} K, pInf={thermo['pInf']:.2f} Pa")

    # 3. parallel execution
    n_procs = params.get('num_procs', 1)
    if n_procs < 1:
        n_procs = 1

    create_decomposePar_dict(case_dir, n_procs)
    ret = run_parallel_hisa(case_dir, n_procs, params)

    if ret == 0:
        print(f"\n=== PARALLEL SUCCESS ===")
    else:
        print(f"\n=== PARALLEL FAILED (exit {ret}) ===")
        sys.exit(ret)

    print(f"\n=== DONE ===")


if __name__ == '__main__':
    main()
