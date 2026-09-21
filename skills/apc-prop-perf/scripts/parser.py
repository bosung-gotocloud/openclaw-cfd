import pandas as pd
import numpy as np
import re
import os

def parse_apc_file(file_path):
    """
    Parses an APC propeller .dat file and returns a tuple of (meta, data).
    meta: {'diameter': float, 'pitch': float, 'filename': str, 'version': str, 'sim_date': str}
    data: DataFrame with columns [rpm, v, j, pe, ct, cp, pwr_hp, torque_lbft, thrust_lbf, pwr_w, torque_nm, thrust_n, thr_pwr, mach, reyn, fom]
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # 1. Extract Meta Information (Diameter x Pitch)
    # Look for pattern like "10.5x4.5" in the first few lines
    meta = {'diameter': None, 'pitch': None, 'filename': os.path.basename(file_path),
            'version': None, 'sim_date': None}
    for line in lines[:10]:
        match = re.search(r'(\d+\.?\d*)x(\d+\.?\d*)', line)
        if match:
            meta['diameter'] = float(match.group(1))
            meta['pitch'] = float(match.group(2))
            break

    # Extract version line: "v2022-0915"
    for line in lines[:10]:
        match = re.search(r'v(\d{4})-(\d{4})', line)
        if match:
            meta['version'] = f"v{match.group(1)}{match.group(2)}"
            break

    # Extract simulation date: "Simulation Date: 09/22/2022"
    for line in lines[:15]:
        match = re.search(r'Simulation Date:\s*(\d{2}/\d{2}/\d{4})', line)
        if match:
            meta['sim_date'] = match.group(1)
            break

    # 2. Find the data blocks
    # Data starts after "V J Pe Ct Cp PWR Torque Thrust ..." header
    # Each block starts with "PROP RPM = XXXX"
    all_data = []
    current_rpm = None
    capture = False

    # Define column names based on the file structure
    columns = [
        'v', 'j', 'pe', 'ct', 'cp', 'pwr_hp', 'torque_lbft', 'thrust_lbf', 
        'pwr_w', 'torque_nm', 'thrust_n', 'thr_pwr', 'mach', 'reyn', 'fom'
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect RPM start
        rpm_match = re.search(r'PROP RPM\s*=\s*(\d+)', line)
        if rpm_match:
            current_rpm = int(rpm_match.group(1))
            capture = False # Reset capture for new RPM block
            continue

        # Detect Header to start capture
        if 'V' in line and 'J' in line and 'Pe' in line and 'Ct' in line:
            capture = True
            continue
        
        # Skip units line
        if '(mph)' in line:
            continue

        # Parse numeric data lines
        if capture:
            parts = line.split()
            if len(parts) >= len(columns):
                try:
                    # Convert values to float, handling cases like empty or '-'
                    row = [float(x) if x != '-' else np.nan for x in parts[:len(columns)]]
                    row.insert(0, current_rpm) # Prepend RPM
                    all_data.append(row)
                except ValueError:
                    # This might be a footer or noise
                    capture = False
                    continue

    df = pd.DataFrame(all_data, columns=['rpm'] + columns)
    return meta, df


def parse_per2_summary(file_path):
    """
    Parse PER2 summary files (PER2_MAXPE.DAT, PER2_N100.DAT, etc.)
    These files contain tabular performance data for all props in one file.
    Returns list of (prop_name, diameter, pitch, data_dict) tuples.
    """
    results = []
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check if it's a valid PER2 file (not HTML/error page)
    if '<!DOCTYPE html>' in content[:500]:
        return []
    
    lines = content.strip().split('\n')
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            try:
                D = float(parts[0])
                P = float(parts[1])
                results.append((D, P, parts[2]))
            except ValueError:
                continue
    
    return results

if __name__ == "__main__":
    # Simple test with sample.dat
    import sys
    sample_path = 'assets/sample.dat'
    if os.path.exists(sample_path):
        meta, df = parse_apc_file(sample_path)
        print(f"Meta: {meta}")
        print(df.head())
        print(f"Total rows: {len(df)}")
    else:
        print("Sample file not found.")
