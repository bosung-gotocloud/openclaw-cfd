#!/usr/bin/env python3
"""calculate_solve_params.py - HiSA 계산 파라미터 및 초기값 계산

대화 기반 파라미터 처리:
- mandatory: mesh_path (사용자 필수 제공)
- optional: flow, turbulence, run, reference, thermodynamic 파라미터 → default 값 사용
- 실행 디렉토리 (script_dir)를 output_dir로 자동 사용

L_ref = 1.0 고정 (reference length)

Usage:
  python3 calculate_solve_params.py

  input.json은 사용 안 함. 대화가 필수.
  output_dir는 스크립트가 복사되어 실행되는 디렉토리 (script_dir).
"""

import json
import math
import sys
import os
import subprocess


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
        "lengthScale": 1.0
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


def calculate_k(Uinf, I):
    return 1.5 * (I * Uinf) ** 2


def calculate_omega(k, L_scale):
    Cmu = 0.09
    L_mix = 0.07 * L_scale
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


def main():
    # 실행 디렉토리 (스크립트가 복사되어 실행되는 곳) — 이것이 output_dir
    script_dir = os.path.dirname(os.path.abspath(__file__))

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

    # 2. Ask for mandatory parameters from user
    mesh_path = input("  Enter mesh_path: ").strip()
    if not mesh_path or not os.path.isdir(mesh_path):
        print("ERROR: mesh_path is required and must be a valid directory.")
        sys.exit(1)

    # 3. L_scale = 1.0 고정
    L_scale = 1.0
    params['turbulence']['lengthScale'] = 1.0

    # 4. L_ref = 1.0 고정
    L_ref = 1.0

    # 5. Calculate derived values
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
    omega_ini = calculate_omega(k_ini, L_scale)

    AoA_rad = math.radians(AoA)
    AoS_rad = math.radians(AoS)
    cos_aos = math.cos(AoS_rad)
    cos_aoa = math.cos(AoA_rad)
    sin_aoa = math.sin(AoA_rad)
    sin_aos = math.sin(AoS_rad)

    Ux = Uinf * cos_aos * cos_aoa
    Uy = Uinf * sin_aos
    Uz = Uinf * sin_aoa
    freestream_dir = f"[{cos_aos * cos_aoa:.6f} {sin_aos:.6f} {sin_aos:.6f}]"

    # output_dir는 스크립트 디렉토리 (executed directory)
    output_dir = script_dir

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
        "output_dir": output_dir,
        "num_procs": detect_physical_cores()
    }

    # Output path — 스크립트 디렉토리 (output_dir)에 생성
    output_path = os.path.join(output_dir, "solve_params.json")

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Display summary
    print(f"\n=== Calculated Parameters ===")
    print(f"Output: {output_path}")
    print(f"  mesh_path:    {mesh_path}")
    print(f"  output_dir:   {output_dir}")
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
    print(f"  Re (based on L_scale): {Uinf * L_scale / nu:.2e}")
    print(f"\n--- Thermodynamic ---")
    print(f"  T:        {T:.2f} K")
    print(f"  pInf:     {pInf:.2f} Pa")
    print(f"\n--- Turbulence ---")
    print(f"  Model:    {params['turbulence']['model']}")
    print(f"  Intensity:  {I:.4f} ({I*100:.1f}%)")
    print(f"  mu_t/nu:  {mu_t_by_nu}")
    print(f"  L_scale:  {L_scale:.4f} m (fixed)")
    print(f"  k:        {k_ini:.8e}")
    print(f"  omega:    {omega_ini:.4f}")
    print(f"\n--- Run Settings ---")
    print(f"  endTime:      {params['run']['endTime']}")
    print(f"  deltaT:       {params['run']['deltaT']}")
    print(f"  writeInterval:{params['run']['writeInterval']}")
    print(f"  pseudoCoNum:  {params['run']['pseudoCoNum']}")
    print(f"  pseudoCoNumMax:{params['run']['pseudoCoNumMax']}")
    print(f"\n--- Mesh ---")
    print(f"  path: {mesh_path}")
    print(f"\n--- Reference Values ---")
    print(f"  L_ref: {L_ref} m (fixed)")
    print(f"  A_ref: {params['reference']['A_ref']} m2")
    print(f"\n--- Hardware ---")
    print(f"  procs: {output['num_procs']}")
    print(f"\nJSON saved to: {output_path}")
    print(f"Edit this file to change any parameters, then run run_hisa.py")


if __name__ == '__main__':
    main()
