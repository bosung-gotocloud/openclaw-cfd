#!/usr/bin/env python3
"""
Compute mean and std of force/moment coefficients (Cd, Cl, CmPitch)
over time range 1501-3000 for each tilt angle from OpenFOAM coefficient data.
"""
import os
import glob
import sys
import numpy as np
import re

base_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/bosung/WinD/0.cfd/2.kari-cabin-drone/02.no-prop-rounded"

# Find tilt directories
tilt_dirs = sorted(glob.glob(os.path.join(base_dir, "tilt_*")))

def get_tilt_angle(d):
    name = os.path.basename(d)
    m = re.match(r'tilt_(\d+)', name)
    if m:
        return int(m.group(1))
    return None

results = []

for d in tilt_dirs:
    tilt = get_tilt_angle(d)
    if tilt is None:
        continue

    # Find coefficient.dat under case/postProcessing/XXX/0/
    pp_dir = os.path.join(d, "case", "postProcessing")
    coeff_dat = None
    for root, dirs, files in os.walk(pp_dir):
        if "coefficient.dat" in files:
            coeff_dat = os.path.join(root, "coefficient.dat")
            break

    if coeff_dat is None or not os.path.exists(coeff_dat):
        print(f"  No coefficient.dat in {d}")
        continue

    data = []
    with open(coeff_dat) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            try:
                t = float(parts[0])
                if 1501 <= t <= 3000 and len(parts) >= 4:
                    cd = float(parts[1])
                    cl = float(parts[2])
                    cmp = float(parts[3])
                    data.append([cd, cl, cmp])
            except (ValueError, IndexError):
                continue

    if not data:
        print(f"  No data in 1501-3000 for tilt_{tilt}")
        continue

    arr = np.array(data)
    results.append({
        'tilt': tilt,
        'n': len(arr),
        'Cd': {'mean': np.mean(arr[:, 0]), 'std': np.std(arr[:, 0])},
        'Cl': {'mean': np.mean(arr[:, 1]), 'std': np.std(arr[:, 1])},
        'CmPitch': {'mean': np.mean(arr[:, 2]), 'std': np.std(arr[:, 2])},
    })

results.sort(key=lambda r: r['tilt'])

print(f"{'Tilt':>5} | {'N':>4} | {'Cd':>14} | {'Cl':>14} | {'CmPitch':>14}")
print("-" * 65)
for r in results:
    t = r['tilt']
    print(f"{t:>5} | {r['n']:>4} | "
          f"{r['Cd']['mean']:>10.4f}±{r['Cd']['std']:>.4f} | "
          f"{r['Cl']['mean']:>10.4f}±{r['Cl']['std']:>.4f} | "
          f"{r['CmPitch']['mean']:>10.4f}±{r['CmPitch']['std']:>.4f}")
