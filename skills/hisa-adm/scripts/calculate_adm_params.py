#!/usr/bin/env python3
"""calculate_adm_params.py - HiSA ADM (Actuator Disk Model) 파라미터 계산

HiSA (compressible, kOmegaSST, AUSMPlusUp, pseudoTime) + Actuator Disk Model.

대화 기반 파라미터 처리:
- mandatory: mesh_path, disk center(X,Y,Z), disk radius
- diskDir: **user 직접 입력** (disk normal vector = propeller thrust vector direction)
- upstreamPoint: diskCenter + diskDir×0.1×radius (upstream: diskDir direction, incoming velocity 측정용)
- 프로펠러 정보 (선택): diameter(inch), pitch(inch), RPM -> APC DB에서 Ct/Cp 자동 조회 (U_perp 기반 속도)

Usage:
  python3 calculate_adm_params.py

output_dir는 스크립트가 복사되어 실행되는 디렉토리 (script_dir).
"""

import json
import math
import sys
import os
import subprocess


def query_apc_ct_cp(diameter_inch, pitch_inch, rpm, speed_mph):
    """APC DB에서 Ct/Cp 가져오기. speed_mph 포함 보간."""
    try:
        apc_path = '/home/bosung/.openclaw/workspace/skills/apc-prop-perf/scripts/database.py'
        apc_interp_path = '/home/bosung/.openclaw/workspace/skills/apc-prop-perf/scripts/interpolator.py'
        if not os.path.exists(apc_interp_path):
            return None, None
        import importlib.util as iu
        db_spec = iu.spec_from_file_location('database', apc_path)
        interp_spec = iu.spec_from_file_location('interpolator', apc_interp_path)
        database_mod = iu.module_from_spec(db_spec)
        db_spec.loader.exec_module(database_mod)
        interpolator_mod = iu.module_from_spec(interp_spec)
        interp_spec.loader.exec_module(interpolator_mod)
        db = database_mod.APCDatabase('/home/bosung/.openclaw/workspace/skills/apc-prop-perf/data/apc_prop.db')
        props = db.get_all_props()
        exact = props[(props['diameter'] == diameter_inch) & (props['pitch'] == pitch_inch)]
        if not exact.empty:
            prop_df = db.get_propeller_data(diameter_inch, pitch_inch)
            interp = interpolator_mod.APCInterpolator(prop_df)
            results = interp.query(rpm, speed_mph)
            return results.get('ct'), results.get('cp')
        combined = interpolator_mod.APCInterpolator.interpolate_between_props(
            db, diameter_inch, pitch_inch, rpm, speed_mph,
            metrics=['ct', 'cp']
        )
        return combined.get('ct'), combined.get('cp')
    except Exception:
        return None, None


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
        "pseudoCoNum": 1,
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
    },
    "topoSet": {
        "enabled": True,
        "name": "actuatorDiskZone",
        "type": "cellZone"
    },
    "ADM": {
        "diskDirX": 1.0,
        "diskDirY": 0.0,
        "diskDirZ": 0.0
    }
}


def calculate_k(Uinf, I):
    return 1.5 * (I * Uinf) ** 2


def calculate_omega(k, L_scale):
    """omega = sqrt(k) / (Cmu^0.25 * L)  (L_ref = 1.0 fixed, same as HiSA skill)"""
    Cmu = 0.09
    return math.sqrt(k) / (Cmu ** 0.25) / L_scale


def detect_physical_cores():
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
    script_dir = os.path.dirname(os.path.abspath(__file__))

    params = {
        "flow": dict(DEFAULTS["flow"]),
        "fluid": dict(DEFAULTS["fluid"]),
        "thermodynamic": dict(DEFAULTS["thermodynamic"]),
        "turbulence": dict(DEFAULTS["turbulence"]),
        "run": dict(DEFAULTS["run"]),
        "reference": dict(DEFAULTS["reference"]),
        "CofR": dict(DEFAULTS["CofR"]),
        "boundary": dict(DEFAULTS["boundary"]),
        "topoSet": dict(DEFAULTS["topoSet"]),
        "ADM": dict(DEFAULTS["ADM"])
    }

    # mandatory: mesh_path
    mesh_path = input("  Enter mesh_path: ").strip()
    if not mesh_path or not os.path.isdir(mesh_path):
        print("ERROR: mesh_path is required and must be a valid directory.")
        sys.exit(1)

    # ADM parameters (user: center + radius + diskDir)
    print("\n=== Actuator Disk Parameters ===")
    adm_center_x = float(input("  Disk center X (m): ").strip() or "0")
    adm_center_y = float(input("  Disk center Y (m): ").strip() or "0")
    adm_center_z = float(input("  Disk center Z (m): ").strip() or "0")
    adm_radius = float(input("  Disk radius (m): ").strip() or "1")

    # diskDir: user input (normalize)
    print("\n=== Disk Normal Vector (propeller thrust direction) ===")
    print("  diskDir is the direction of the thrust vector of the propeller.")
    diskDir_x = float(input("  diskDir X [{}]: ".format(DEFAULTS['ADM']['diskDirX'])).strip() or str(DEFAULTS['ADM']['diskDirX']))
    diskDir_y = float(input("  diskDir Y [{}]: ".format(DEFAULTS['ADM']['diskDirY'])).strip() or str(DEFAULTS['ADM']['diskDirY']))
    diskDir_z = float(input("  diskDir Z [{}]: ".format(DEFAULTS['ADM']['diskDirZ'])).strip() or str(DEFAULTS['ADM']['diskDirZ']))

    d_norm = math.sqrt(diskDir_x**2 + diskDir_y**2 + diskDir_z**2)
    if d_norm < 1e-12:
        print("ERROR: diskDir cannot be zero vector. Exiting.")
        sys.exit(1)
    diskDir_x /= d_norm
    diskDir_y /= d_norm
    diskDir_z /= d_norm

    # Flow
    print("\n=== Flow Conditions ===")
    Uinf_str = input("  Uinf (m/s) [{}]: ".format(DEFAULTS['flow']['Uinf'])).strip()
    Uinf_ms = float(Uinf_str) if Uinf_str else DEFAULTS['flow']['Uinf']
    AoA = float(input("  AoA (deg) [{}]: ".format(DEFAULTS['flow']['AoA'])).strip() or str(DEFAULTS['flow']['AoA']))
    AoS = float(input("  AoS (deg) [{}]: ".format(DEFAULTS['flow']['AoS'])).strip() or str(DEFAULTS['flow']['AoS']))

    AoA_rad = math.radians(AoA)
    AoS_rad = math.radians(AoS)
    cos_aos = math.cos(AoS_rad)
    cos_aoa = math.cos(AoA_rad)
    sin_aoa = math.sin(AoA_rad)
    sin_aos = math.sin(AoS_rad)

    Ux = Uinf_ms * cos_aos * cos_aoa
    Uy = Uinf_ms * sin_aos
    Uz = Uinf_ms * sin_aoa

    print("\n  Uinf vector: ({:.6f}, {:.6f}, {:.6f}) m/s".format(Ux, Uy, Uz))
    print("  diskDir (thrust direction): ({:.6f}, {:.6f}, {:.6f})  [user input, auto-normalized]".format(diskDir_x, diskDir_y, diskDir_z))

    # upstreamPoint: 0.1R in diskDir + 0.75R perpendicular to disk
    # (perp = cross(diskDir, (0,1,0)) if not parallel, else cross(diskDir, (1,0,0)))
    dx, dy, dz = diskDir_x, diskDir_y, diskDir_z
    # pick a non-parallel ref
    if abs(dy) < 0.99:
        px, py, pz = 0.0, 1.0, 0.0
    else:
        px, py, pz = 1.0, 0.0, 0.0
    # cross(diskDir, ref)
    cx = dy*pz - dz*py
    cy = dz*px - dx*pz
    cz = dx*py - dy*px
    cn = math.sqrt(cx*cx + cy*cy + cz*cz)
    cx, cy, cz = cx/cn, cy/cn, cz/cn
    off_disk = adm_radius * 0.1
    off_perp = adm_radius * 0.75
    upstream_x = adm_center_x + dx*off_disk + cx*off_perp
    upstream_y = adm_center_y + dy*off_disk + cy*off_perp
    upstream_z = adm_center_z + dz*off_disk + cz*off_perp

    # U_perp = Uinf dot diskDir (disk face perpendicular velocity, for APC Ct/Cp lookup)
    U_perp = Ux * diskDir_x + Uy * diskDir_y + Uz * diskDir_z
    U_perp_magnitude = abs(U_perp)

    # Propeller info -> Ct/Cp auto lookup
    print("\n=== Propeller Info (Ct/Cp auto lookup) ===")
    prop_diameter = input("  Propeller diameter (inch) [empty=skip]: ").strip()
    prop_pitch = input("  Propeller pitch (inch) [empty=skip]: ").strip()
    prop_rpm = input("  Propeller RPM [empty=skip]: ").strip()

    adm_ct = None
    adm_cp = None
    if prop_diameter and prop_pitch and prop_rpm:
        try:
            prop_diameter = float(prop_diameter)
            prop_pitch = float(prop_pitch)
            prop_rpm = float(prop_rpm)
            speed_mph = U_perp_magnitude / 0.44704  # m/s -> mph
            adm_ct, adm_cp = query_apc_ct_cp(prop_diameter, prop_pitch, prop_rpm, speed_mph)
            if adm_ct is not None and adm_cp is not None:
                print("  OK Ct={:.4f}, Cp={:.4f} (APC DB {}x{} @ {} RPM, U_perp={:.1f} m/s, speed={:.1f} mph)".format(
                    adm_ct, adm_cp, prop_diameter, prop_pitch, prop_rpm, U_perp_magnitude, speed_mph))
            else:
                print("  APC DB: {}x{} not found. Manual input required.".format(prop_diameter, prop_pitch))
        except Exception as e:
            print("  APC DB lookup failed ({}). Manual input required.".format(e))

    if adm_ct is None:
        adm_ct = float(input("  Ct (manual) [0.8]: ").strip() or "0.8")
    if adm_cp is None:
        adm_cp = float(input("  Cp (manual) [0.4]: ").strip() or "0.4")

    # Thermodynamic (HiSA compressible)
    T = params['thermodynamic']['T']
    pInf = params['thermodynamic']['pInf']
    nu = params['fluid']['nu']
    rho = params['fluid']['rho']
    I = params['turbulence']['intensity']
    L_scale = params['turbulence']['lengthScale']

    k_ini = calculate_k(Uinf_ms, I)
    omega_ini = calculate_omega(k_ini, L_scale)

    output_dir = script_dir

    output = {
        "ADM": {
            "centerX": adm_center_x,
            "centerY": adm_center_y,
            "centerZ": adm_center_z,
            "diskDirX": round(diskDir_x, 6),
            "diskDirY": round(diskDir_y, 6),
            "diskDirZ": round(diskDir_z, 6),
            "radius": adm_radius,
            "Ct": adm_ct,
            "Cp": adm_cp
        },
        "propeller": {
            "diameter_inch": float(prop_diameter) if prop_diameter else None,
            "pitch_inch": float(prop_pitch) if prop_pitch else None,
            "rpm": float(prop_rpm) if prop_rpm else None,
            "Ct_source": "apc-db" if (prop_diameter and prop_pitch and prop_rpm) else "manual",
            "Cp_source": "apc-db" if (prop_diameter and prop_pitch and prop_rpm) else "manual"
        },
        "flow": {
            "Uinf": Uinf_ms,
            "AoA": AoA,
            "AoS": AoS,
            "Ux": round(Ux, 6),
            "Uy": round(Uy, 6),
            "Uz": round(Uz, 6),
            "diskDirX": round(diskDir_x, 6),
            "diskDirY": round(diskDir_y, 6),
            "diskDirZ": round(diskDir_z, 6),
            "upstreamX": round(upstream_x, 8),
            "upstreamY": round(upstream_y, 8),
            "upstreamZ": round(upstream_z, 8),
            "U_perp": round(U_perp, 6),
            "U_perp_magnitude": round(U_perp_magnitude, 6)
        },
        "fluid": {
            "rho": rho,
            "nu": nu
        },
        "thermodynamic": {
            "T": T,
            "pInf": pInf
        },
        "turbulence": {
            "model": params['turbulence']['model'],
            "intensity": I,
            "viscosityRatio": params['turbulence']['viscosityRatio'],
            "lengthScale": L_scale,
            "k_ini": round(k_ini, 8),
            "omega_ini": round(omega_ini, 4)
        },
        "run": {
            "endTime": params['run']['endTime'],
            "deltaT": params['run']['deltaT'],
            "writeInterval": params['run']['writeInterval'],
            "pseudoCoNum": params['run']['pseudoCoNum'],
            "pseudoCoNumMax": params['run']['pseudoCoNumMax'],
            "timeScheme": params['run']['timeScheme']
        },
        "reference": {
            "L_ref": params['reference']['L_ref'],
            "A_ref": params['reference']['A_ref']
        },
        "CofR": {
            "x": params['CofR']['CofR_x'],
            "y": params['CofR']['CofR_y'],
            "z": params['CofR']['CofR_z']
        },
        "boundary": dict(params['boundary']),
        "topoSet": dict(params['topoSet']),
        "meshPath": mesh_path,
        "output_dir": output_dir,
        "num_procs": detect_physical_cores()
    }

    output_path = os.path.join(output_dir, "adm_params.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Display
    print("\n=== Calculated Parameters ===")
    print("Output: {}".format(output_path))

    print("\n--- Actuator Disk ---")
    print("  Center:       ({:.4f}, {:.4f}, {:.4f}) m".format(adm_center_x, adm_center_y, adm_center_z))
    print("  diskDir:      ({:.6f}, {:.6f}, {:.6f})  [thrust vector direction, user input + normalize]".format(diskDir_x, diskDir_y, diskDir_z))
    print("  Radius:       {:.4f} m".format(adm_radius))
    print("  Ct:           {:.4f}".format(adm_ct))
    print("  Cp:           {:.4f}".format(adm_cp))

    if prop_diameter and prop_pitch and prop_rpm:
        print("  Propeller:    {:.1f}x{:.1f} @ {:.0f} RPM".format(prop_diameter, prop_pitch, prop_rpm))
        print("  Ct/Cp from APC DB @ U_perp={:.1f} m/s".format(U_perp_magnitude))

    print("\n--- Flow Conditions ---")
    print("  Uinf:     {:.4f} m/s".format(Uinf_ms))
    print("  AoA:      {:.2f} deg".format(AoA))
    print("  AoS:      {:.2f} deg".format(AoS))
    print("  U =       ({:.6f}, {:.6f}, {:.6f})".format(Ux, Uy, Uz))
    print("  U_perp:   {:.6f} m/s  (Uinf dot diskDir, disk face perpendicular)".format(U_perp))

    print("\n--- Thermodynamic (HiSA compressible) ---")
    print("  T:        {:.2f} K".format(T))
    print("  pInf:     {:.2f} Pa".format(pInf))

    print("\n--- ADM Derived ---")
    print("  upstreamPoint: ({:.6f}, {:.6f}, {:.6f}) m  [upstream: diskDir direction, incoming velocity measurement]".format(upstream_x, upstream_y, upstream_z))
    print("    (disk center + diskDir x {:.6f})  [upstream: diskDir direction]".format(epsilon))
    print("  epsilon: {:.6f} m (radius x 0.1)".format(epsilon))

    print("\n--- Turbulence ---")
    print("  Model:   {}".format(params['turbulence']['model']))
    print("  k:       {:.8e}".format(k_ini))
    print("  omega:   {:.4f}".format(omega_ini))

    print("\n--- Run Settings ---")
    print("  endTime:      {}".format(params['run']['endTime']))
    print("  deltaT:       {}".format(params['run']['deltaT']))
    print("  writeInterval:{}".format(params['run']['writeInterval']))
    print("  pseudoCoNum:  {}".format(params['run']['pseudoCoNum']))
    print("  pseudoCoNumMax: {}".format(params['run']['pseudoCoNumMax']))

    print("\n--- Hardware ---")
    print("  procs: {}".format(output['num_procs']))

    print("\nJSON saved to: {}".format(output_path))
    print("Edit this file to change parameters, then run run_hisa_adm.py")


if __name__ == '__main__':
    main()
