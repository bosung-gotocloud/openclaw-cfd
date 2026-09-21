#!/usr/bin/env pvpython
"""
Basic case loader - detects decomposed cases and loads OpenFOAM case.
"""
from paraview.simple import *
import os
import glob

def load_case(case_path, skip_zero_time=True, cell_to_point=True):
    """
    Load OpenFOAM case and return reader.
    
    Args:
        case_path: Directory containing case.foam
        skip_zero_time: Skip time step 0
        cell_to_point: Enable cell-to-point filter
    
    Returns:
        reader, is_decomposed, last_time
    """
    foam_file = os.path.join(case_path, 'case.foam')
    if not os.path.exists(foam_file):
        raise FileNotFoundError(f"case.foam not found: {foam_file}")
    
    # Check decomposed
    processor_dirs = sorted(glob.glob(os.path.join(case_path, 'processor*')))
    is_decomposed = len(processor_dirs) > 0
    
    # Load case
    reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
    
    if is_decomposed:
        reader.CaseType = 'Decomposed Case'
        print(f"Decomposed case detected: {len(processor_dirs)} processors")
    
    if skip_zero_time:
        reader.SkipZeroTime = 1
    
    if cell_to_point:
        reader.Createcelltopointfiltereddata = 1
    
    reader.UpdatePipelineInformation()
    
    # Get last time step
    time_steps = reader.TimestepValues
    last_time = time_steps[-1] if time_steps else 0
    
    return reader, is_decomposed, last_time


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: pvpython load_case.py <case_directory>")
        sys.exit(1)
    
    case_dir = sys.argv[1]
    reader, is_decomposed, last_time = load_case(case_dir)
    
    print(f"Case: {case_dir}")
    print(f"Decomposed: {is_decomposed}")
    print(f"Last time: {last_time}")
    print(f"Time steps: {len(reader.TimestepValues)}")
