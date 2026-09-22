#!/usr/bin/env python3
"""calculate_solve_params.py - HiSA 계산 파라미터 및 초기값 계산

대화 기반 파라미터 처리:
- mandatory: mesh_path (사용자 필수 제공)
- optional: flow, turbulence, run, reference, thermodynamic 파라미터 → default 값 사용
- mesh_points에서 bounding box 자동 계산 → turbulence length scale 자동 추정

L_ref = 1.0 고정 (reference length)

Usage:
  python3 calculate_solve_params.py [input.json]

  input.json은 optional. 없으면 default 값 사용.
"""

import json
import math
import sys
import os
import subprocess
import re


# ===== Default Values =====
DEFAULTS = {
    "flow": {
        "Uinf": 41.667,
        "AoA": 0.0,
        "AoS": 0.0
    },
    "fluid": {
        "rho": 1.225,
        "nu": 1.5e-5
    },
    "thermodynamic": {
        "T": 293.15,
        "pInf": 101325
    },
    "turbulence": {
        "model": "kOmegaSST",
        "intensity": 0.01,
        "viscosityRatio": 10,
        "lengthScale": 0.1
    },
    "run": {
        "endTime": 1000,
        "deltaT": 1,
        "writeInterval": 100,
        "pseudoCoNum": 10,
        "pseudoCoNumMax": 10000,
        "timeScheme": "steadyState"
    },
    "reference": {
        "L_ref": 1.0,
        "A_ref": 1.0
    },
    "CofR": {
        "CofR_x": 0.0,
        "CofR_y": 0.0,
        "CofR_z": 0.0
    },
    "boundary": {
        "patch": ["far", "surface"],
        "far_BC": "freestream",
        "surface_BC": "wall"
    }
}


def detect_surface_patch(mesh_path):
    """메쉬 boundary 파일에서 far patch 제외한 surface patch 이름 자동 감지."""
    boundary_file = os.path.join(mesh_path, 'boundary')
    if not os.path.isfile(boundary_file):
        return None
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    # polyBoundaryMesh: ( ... ) 블록에서 패치 이름 추출
    m = re.search(r'\(\s*\n(.*?)\n\s*\)', content, re.DOTALL)
    if not m:
        return None
    
    block = m.group(1)
    # 각 패치는 patchName { 형태로 시작
    patches = re.findall(r'^\s*(\S+)\s*\{', block, re.MULTILINE)
    
    patch_names = [p for p in patches if p != 'far']
    return patch_names if patch_names else None

def calculate_k(Uinf, I):
    return 1.5 * (I * Uinf) ** 2


def calculate_omega(k, characteristic_length):
    Cmu = 0.09

    # SST turbulence length scale
    L_mix = 0.07 * characteristic_length

    return math.sqrt(k) / ((Cmu ** 0.25) * L_mix)

def detect_physical_cores():
    """Detect physical CPU cores (no HyperThreading) for parallel execution."""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        sockets = len(set(
            line.split(':')[1].strip()
            for line in cpuinfo.splitlines()
            if line.startswith('physical id')
        ))
        cores_per_socket = int(
            [line for line in cpuinfo.splitlines()
             if line.startswith('cpu cores')][0].split(':')[1].strip()
        )
        return sockets * cores_per_socket
    except Exception:
        return max(1, int(subprocess.getoutput('nproc')) // 2)


def auto_estimate_length_scale(mesh_path):
    """mesh의 bounding box에서 characteristic length 자동 추정."""
    boundary_file = os.path.join(mesh_path, 'boundary')
    if not os.path.isfile(boundary_file):
        return None
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    far_faces = None
    lines = content.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'far' or stripped.startswith('"far"'):
            for j in range(i+1, min(i+10, len(lines))):
                if 'nFaces' in lines[j]:
                    match = re.search(r'nFaces\s+(\d+)', lines[j])
                    if match:
                        far_faces = int(match.group(1))
                    break
            break
    
    if far_faces is None:
        return None
    
    points_file = os.path.join(mesh_path, 'points')
    if not os.path.isfile(points_file):
        return None
    
    try:
        n_points = int(re.search(r'^\d+', open(points_file).read().splitlines()[8]).group())
    except Exception:
        return None
    
    bbox_side_est = max(2.0, (n_points ** 0.15) * 1.5)
    return bbox_side_est


def main():
    # 1. Start with defaults
    params = {
        "flow": dict(DEFAULTS["flow"]),
        "fluid": dict(DEFAULTS["fluid"]),
        "thermodynamic": dict(DEFAULTS["thermodynamic"]),
        "turbulence": dict(DEFAULTS["turbulence"]),
        "run": dict(DEFAULTS["run"]),
        "reference": dict(DEFAULTS["reference"]),
        "CofR": dict(DEFAULTS["CofR"]),
        "boundary": dict(DEFAULTS["boundary"])
    }

    # 2. Merge optional JSON input (if provided)
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
        if os.path.isfile(input_path):
            with open(input_path, 'r') as f:
                user_input = json.load(f)
            for key in ["flow", "fluid", "thermodynamic", "turbulence", "run", "reference", "CofR", "boundary"]:
                if key in user_input:
                    params[key].update(user_input[key])
            for key in ["mesh_path", "surfaceName", "farBC", "surfaceBC"]:
                if key in user_input:
                    params[key] = user_input[key]
        elif os.path.isdir(input_path):
            params["mesh_path"] = input_path
        else:
            params["mesh_path"] = input_path

    # 3. Interactive mandatory check
    is_tty = sys.stdin.isatty() if sys.stdin else False
    mandatory_fields = ["mesh_path"]
    missing = [f for f in mandatory_fields if f not in params]

    if missing:
        print("\n=== Missing mandatory parameters ===")
        for field in missing:
            val = input(f"  Enter {field}: ").strip()
            if not val:
                print(f"  ERROR: {field} is mandatory. Aborted.")
                sys.exit(1)
            params[field] = val

    mesh_path = params['mesh_path']
    
    # Auto-detect surface patch name from boundary file
    surface_patch_auto = None
    if mesh_path and os.path.isdir(mesh_path):
        detected = detect_surface_patch(mesh_path)
        if detected:
            surface_patch_auto = detected[0]
            if len(params['boundary']['patch']) <= 1 or params['boundary']['patch'][1] == 'surface':
                params['boundary']['patch'][1] = surface_patch_auto
            print(f"\n=== Auto-detected surface patch: {surface_patch_auto} ===")
    
    # 4. Auto-estimate length scale from mesh if not explicitly set
    L_scale = params['turbulence']['lengthScale']
    mesh_bbox = None
    
    if mesh_path and os.path.isdir(mesh_path):
        points_file = os.path.join(mesh_path, 'points')
        if os.path.isfile(points_file):
            content = open(points_file, 'r').read()
            lines = content.splitlines()
            in_points = False
            x_min = x_max = y_min = y_max = z_min = z_max = 0
            for line in lines:
                stripped = line.strip()
                if stripped == '(' and not in_points:
                    in_points = True
                    continue
                if in_points and stripped == ')':
                    break
                if in_points:
                    match = re.match(r'\(([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)', stripped)
                    if match:
                        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
                        if x_min == 0:
                            x_min = x_max = x
                            y_min = y_max = y
                            z_min = z_max = z
                        else:
                            x_min = min(x_min, x); x_max = max(x_max, x)
                            y_min = min(y_min, y); y_max = max(y_max, y)
                            z_min = min(z_min, z); z_max = max(z_max, z)
            
            dx = x_max - x_min
            dy = y_max - y_min
            dz = z_max - z_min
            mesh_bbox = {'dx': dx, 'dy': dy, 'dz': dz}
            L_mesh = max(dx, dy, dz)
            
            if L_scale == DEFAULTS["turbulence"]["lengthScale"]:
                L_scale = L_mesh
                params['turbulence']['lengthScale'] = L_mesh
            print(f"\n=== Mesh Bounding Box ===")
            print(f"  X: [{x_min:.4f}, {x_max:.4f}] = {dx:.4f} m")
            print(f"  Y: [{y_min:.4f}, {y_max:.4f}] = {dy:.4f} m")
            print(f"  Z: [{z_min:.4f}, {z_max:.4f}] = {dz:.4f} m")
            print(f"  max_dim: {L_mesh:.4f} m (used as L_ref for turbulence)")
            print(f"  lengthScale updated: {L_scale:.4f} m")

    # FIXED: L_ref = 1.0 (constant reference length)
    L_ref = 1.0

    # Calculate derived values
    Uinf = params['flow']['Uinf']
    AoA = params['flow']['AoA']
    AoS = params['flow']['AoS']
    nu = params['fluid']['nu']
    rho = params['fluid']['rho']
    T = params['thermodynamic']['T']
    pInf = params['thermodynamic']['pInf']
    I = params['turbulence']['intensity']
    mu_t_by_nu = params['turbulence']['viscosityRatio']
    mu = rho * nu

    k_ini = calculate_k(Uinf, I)
    omega_ini = calculate_omega(k_ini, 1.0e-5)

    AoA_rad = math.radians(AoA)
    AoS_rad = math.radians(AoS)
    cos_aos = math.cos(AoS_rad)
    cos_aoa = math.cos(AoA_rad)
    sin_aoa = math.sin(AoA_rad)
    sin_aos = math.sin(AoS_rad)

    Ux = Uinf * cos_aos * cos_aoa
    Uy = Uinf * sin_aos
    Uz = Uinf * sin_aoa
    freestream_dir = f"[{cos_aos * cos_aoa:.6f} {sin_aos:.6f} {sin_aoa:.6f}]"

    # Build output
    output = {
        "Uinf": Uinf,
        "AoA": AoA,
        "AoS": AoS,
        "Ux": round(Ux, 6),
        "Uy": round(Uy, 6),
        "Uz": round(Uz, 6),
        "nu": nu,
        "rho": rho,
        "T": T,
        "pInf": pInf,
        "k_ini": round(k_ini, 8),
        "omega_ini": round(omega_ini, 4),
        "freestreamDirection": freestream_dir,
        "mu": mu,
        "endTime": params['run']['endTime'],
        "deltaT": params['run']['deltaT'],
        "writeInterval": params['run']['writeInterval'],
        "turbModel": params['turbulence']['model'],
        "startFrom": "startTime",
        "startTime": 0,
        "surfaceName": params['boundary']['patch'][1] if len(params['boundary']['patch']) > 1 else params['boundary']['patch'][0],
        "farBC": params['boundary']['far_BC'],
        "surfaceBC": params['boundary']['surface_BC'],
        "Aref": params['reference']['A_ref'],
        "lRef": params['reference']['L_ref'],
        "CofR_x": params['CofR']['CofR_x'],
        "CofR_y": params['CofR']['CofR_y'],
        "CofR_z": params['CofR']['CofR_z'],
        "magUInf": Uinf,
        "meshPath": mesh_path,
        "num_procs": detect_physical_cores(),
        "output_dir": None
    }

    # Determine output path
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
        if os.path.isfile(input_path):
            output_path = input_path.replace('.json', '_solve_params.json')
        else:
            output_path = "solve_params.json"
    else:
        output_path = "solve_params.json"

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Display summary
    print(f"\n=== Calculated Parameters ===")
    print(f"Output: {output_path}")
    print(f"\n--- Flow Conditions ---")
    print(f"  Uinf:     {Uinf:.4f} m/s")
    print(f"  AoA:      {AoA:.2f} deg")
    print(f"  AoS:      {AoS:.2f} deg")
    print(f"  U = ({Ux:.6f}, {Uy:.6f}, {Uz:.6f})")
    print(f"  Direction: {freestream_dir}")
    print(f"\n--- Fluid Properties ---")
    print(f"  rho:      {rho:.4f} kg/m3")
    print(f"  nu:       {nu:.2e} m2/s")
    print(f"  Re (based on L_ref): {Uinf * L_ref / nu:.2e}")
    print(f"  Re (based on mesh L): {Uinf * L_scale / nu:.2e}")
    print(f"\n--- Thermodynamic ---")
    print(f"  T:        {T:.2f} K")
    print(f"  pInf:     {pInf:.2f} Pa")
    print(f"\n--- Turbulence ---")
    print(f"  Model:    {params['turbulence']['model']}")
    print(f"  Intensity:  {I:.4f} ({I*100:.1f}%)")
    print(f"  mu_t/nu:  {mu_t_by_nu}")
    print(f"  L_scale:  {L_scale:.4f} m (mesh-estimated)")
    print(f"  k:        {k_ini:.8e}")
    print(f"  omega:    {omega_ini:.4f}")
    print(f"\n--- Run Settings ---")
    print(f"  endTime:      {params['run']['endTime']}")
    print(f"  deltaT:       {params['run']['deltaT']}")
    print(f"  writeInterval:{params['run']['writeInterval']}")
    print(f"\n--- Mesh ---")
    print(f"  path: {mesh_path}")
    if mesh_bbox:
        print(f"  bbox: X={mesh_bbox['dx']:.4f} Y={mesh_bbox['dy']:.4f} Z={mesh_bbox['dz']:.4f} m")
    print(f"\n--- Reference Values ---")
    print(f"  L_ref: {L_ref} m (fixed)")
    print(f"  A_ref: {params['reference']['A_ref']} m2")
    print(f"\n--- Hardware ---")
    print(f"  procs: {output['num_procs']}")
    print(f"\nJSON saved to: {output_path}")
    print(f"Edit this file to change any parameters, then run run_hisa.py")


if __name__ == '__main__':
    main()
