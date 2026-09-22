#!/usr/bin/env pvpython
"""
List all available patches in an OpenFOAM case.
"""
from paraview.simple import *
import os
import sys

def list_patches(case_path):
    """List all patches in the case."""
    foam_file = os.path.join(case_path, 'case.foam')
    if not os.path.exists(foam_file):
        print(f"Error: case.foam not found in {case_path}")
        return
    
    reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
    
    # Check decomposed
    processor_dirs = [d for d in os.listdir(case_path) 
                     if d.startswith('processor') and os.path.isdir(os.path.join(case_path, d))]
    if processor_dirs:
        reader.CaseType = 'Decomposed Case'
    
    reader.UpdatePipelineInformation()
    
    # Get patch info
    proxy = reader.SMProxy
    patchInfoProp = proxy.GetProperty("PatchArrayInfo")
    
    print(f"Patches in {case_path}:")
    print("-" * 50)
    
    wall_patches = []
    for i in range(patchInfoProp.GetNumberOfElements()):
        name = patchInfoProp.GetElement(i)
        if name and not name.startswith(('internalMesh', 'group/')):
            print(f"  {name}")
            if 'wall' in name.lower():
                wall_patches.append(name)
    
    print("-" * 50)
    print(f"Wall-type patches: {wall_patches}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        case_path = os.getcwd()
    else:
        case_path = sys.argv[1]
    
    list_patches(case_path)
