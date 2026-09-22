#!/usr/bin/env python3
"""
setup-refined-case.py — Copy and adjust hisa case configuration for refined mesh.

Copies all necessary files from the original case to a new refined-case directory,
replacing only the polyMesh with the refined mesh.

Usage:
    python3 setup-refined-case.py --case /path/to/case --refined-case /path/to/refined-case
"""

import argparse
import json
import os
import shutil
from pathlib import Path


def setup_refined_case(case_dir, refined_case_dir):
    """Copy case configuration and replace polyMesh with refined mesh.
    
    Args:
        case_dir: Original case directory path
        refined_case_dir: Destination refined-case directory path
        
    Returns:
        dict with copy statistics
    """
    os.makedirs(refined_case_dir, exist_ok=True)
    
    # Determine case_root (parent of case directory)
    case_path = Path(case_dir).resolve()
    case_root = case_path.parent
    
    print(f"[setup-refined-case] Case root: {case_root}")
    print(f"[setup-refined-case] Source case: {case_dir}")
    print(f"[setup-refined-case] Destination refined case: {refined_case_dir}")
    
    copied_files = []
    skipped_files = []
    
    # === Copy directories (not polyMesh — handled separately) ===
    dirs_to_copy = [
        "0",                    # Initial fields
        "constant/turbulenceProperties",
        "constant/transportProperties",
        "constant/fvOptions",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/decomposeParDict",
        "system/forceCoeffs",
        "shock_cells.json",     # Sensor results
    ]
    
    for rel_path in dirs_to_copy:
        src = case_dir / rel_path
        dst = Path(refined_case_dir) / rel_path
        
        if not src.exists():
            skipped_files.append(str(rel_path))
            continue
        
        if src.is_dir():
            os.makedirs(dst.parent, exist_ok=True)
            if dst.exists():
                shutil.rmtree(str(dst))
            shutil.copytree(str(src), str(dst))
            print(f"  [copied dir] {rel_path}")
        else:
            os.makedirs(dst.parent, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            print(f"  [copied file] {rel_path}")
        
        copied_files.append(str(rel_path))
    
    # === Replace polyMesh with refined version if exists ===
    refined_poly = Path(refined_case_dir).parent / "refined-polyMesh"
    if (case_root / "refined-polyMesh").exists():
        dst_poly = Path(refined_case_dir) / "polyMesh"
        os.makedirs(str(dst_poly), exist_ok=True)
        
        src_poly = case_root / "refined-polyMesh"
        for item in src_poly.iterdir():
            if item.is_file():
                shutil.copy2(str(item), str(dst_poly / item.name))
                print(f"  [replaced] polyMesh/{item.name}")
    
    # === Copy shock visualization files ===
    shock_stl = case_dir / "shock_cells.stl"
    if shock_stl.exists():
        shutil.copy2(str(shock_stl), str(Path(refined_case_dir) / "shock_cells.stl"))
        print(f"  [copied] shock_cells.stl")
    
    # === Adjust controlDict if needed ===
    control_dict = Path(refined_case_dir) / "system" / "controlDict"
    if control_dict.exists():
        content = control_dict.read_text()
        
        # Check if we need to adjust endTime based on mesh size increase
        shock_data_path = Path(refined_case_dir) / "shock_cells.json"
        if shock_data_path.exists():
            with open(shock_data_path, 'r') as f:
                shock_data = json.load(f)
            
            n_original = shock_data.get("total_cells_analyzed", 0)
            n_shock = shock_data.get("shock_cells_detected", 0)
            
            # Estimate refined cell count (rough)
            n_refined_est = n_original + n_shock * 7  # level=1 adds ~7 cells per shock cell
            
            if n_refined_est > n_original:
                increase_ratio = n_refined_est / max(n_original, 1)
                print(f"\n[setup-refined-case] Mesh size increase estimate:")
                print(f"  Original cells: {n_original}")
                print(f"  Estimated refined cells: {n_refined_est}")
                print(f"  Increase ratio: {increase_ratio:.2f}x")
                
                # Adjust writeInterval to maintain output frequency relative to mesh size
                if "writeInterval" in content or "writeInterval" in content:
                    print(f"\n[setup-refined-case] Note: Review controlDict writeInterval")
                    print(f"  for the refined mesh. Current settings should work, but monitor.")
    
    return {
        "case_root": str(case_root),
        "source_case": str(case_dir),
        "refined_case": str(refined_case_dir),
        "files_copied": len(copied_files),
        "files_skipped": len(skipped_files)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up refined case from hisa results")
    parser.add_argument("--case", required=True, help="Original case directory")
    parser.add_argument("--refined-case", required=True, help="Output refined-case directory")
    
    args = parser.parse_args()
    
    case_path = Path(args.case).resolve()
    refined_path = Path(args.refined_case)
    
    # If refined-case is relative, make it under case_root
    if not refined_path.is_absolute():
        refined_path = case_path.parent / refined_path
    
    result = setup_refined_case(case_path, refined_path)
    
    print(f"\n[setup-refined-case] Done!")
    for k, v in result.items():
        print(f"  {k}: {v}")
