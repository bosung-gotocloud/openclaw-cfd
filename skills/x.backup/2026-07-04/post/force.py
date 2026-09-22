#!/usr/bin/env python3
"""
Compute mean and std of total force/moment (x,y,z) over the last N time steps
for each tilt angle from OpenFOAM forces/moments data.

Usage:
    python3 force.py [base_dir] [N_last_steps]

Defaults:
    base_dir  = /home/bosung/WinD/0.cfd/2.kari-cabin-drone/02.no-prop-rounded
    N         = 1500
"""
import os
import glob
import sys
import numpy as np
import re

base_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/bosung/WinD/0.cfd/2.kari-cabin-drone/02.no-prop-rounded"
n_last = int(sys.argv[2]) if len(sys.argv) > 2 else 1500

# Find tilt directories
tilt_dirs = sorted(glob.glob(os.path.join(base_dir, "tilt_*")))

def get_tilt_angle(d):
    name = os.path.basename(d)
    m = re.match(r'tilt_(\d+)', name)
    return int(m.group(1)) if m else None

results = []

for d in tilt_dirs:
    tilt = get_tilt_angle(d)
    if tilt is None:
        continue

    # Find _forces directory
    pp_dir = os.path.join(d, "case", "postProcessing")
    forces_dirs = glob.glob(os.path.join(pp_dir, "*_forces"))
    if not forces_dirs:
        print(f"  No _forces dir in {d}")
        continue
    forces_dir = forces_dirs[0]

    force_dat = os.path.join(forces_dir, "0", "force.dat")
    moment_dat = os.path.join(forces_dir, "0", "moment.dat")

    if not os.path.exists(force_dat) or not os.path.exists(moment_dat):
        print(f"  Missing data files in {d}")
        continue

    def read_last_n(path, col, n):
        """Read column 'col' from last 'n' non-comment data lines."""
        data = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if col < len(parts):
                    data.append(float(parts[col]))
        # Take last n lines
        data = data[-n:]
        if data:
            return np.array(data)
        return None

    force_data = read_last_n(force_dat, col=1, n=n_last)
    moment_data = read_last_n(moment_dat, col=1, n=n_last)

    if force_data is None or moment_data is None:
        print(f"  No data in last {n_last} for tilt_{tilt}")
        continue

    force_means, force_stds = {}, {}
    moment_means, moment_stds = {}, {}
    for i, label in enumerate(['X', 'Y', 'Z']):
        force_means[label] = np.mean(force_data[:, i])
        force_stds[label] = np.std(force_data[:, i])
        moment_means[label] = np.mean(moment_data[:, i])
        moment_stds[label] = np.std(moment_data[:, i])

    n_samples = len(force_data)
    results.append({
        'tilt': tilt,
        'n_samples': n_samples,
        'force_means': force_means,
        'force_stds': force_stds,
        'moment_means': moment_means,
        'moment_stds': moment_stds,
    })

results.sort(key=lambda r: r['tilt'])

print(f"{'Tilt':>5} | {'N':>5} | {'F_X mean':>12} | {'F_X std':>12} | {'F_Y mean':>12} | {'F_Y std':>12} | {'F_Z mean':>12} | {'F_Z std':>12} | {'M_X mean':>12} | {'M_X std':>12} | {'M_Y mean':>12} | {'M_Y std':>12} | {'M_Z mean':>12} | {'M_Z std':>12}")
print("-" * 150)
for r in results:
    t = r['tilt']
    print(f"{t:>5} | {r['n_samples']:>5} | "
          f"{r['force_means']['X']:>12.6f} | {r['force_stds']['X']:>12.6f} | "
          f"{r['force_means']['Y']:>12.6f} | {r['force_stds']['Y']:>12.6f} | "
          f"{r['force_means']['Z']:>12.6f} | {r['force_stds']['Z']:>12.6f} | "
          f"{r['moment_means']['X']:>12.6f} | {r['moment_stds']['X']:>12.6f} | "
          f"{r['moment_means']['Y']:>12.6f} | {r['moment_stds']['Y']:>12.6f} | "
          f"{r['moment_means']['Z']:>12.6f} | {r['moment_stds']['Z']:>12.6f}")
