#!/usr/bin/env pvpython
"""
Plot surface mesh from STL file and OpenFOAM case.

Usage: pvpython plot_surface_mesh.py <case_directory>
"""
from paraview.simple import *
from paraview import vtk
import os
import glob

def plot_surface_mesh(case_dir):
    """Plot STL surface + OpenFOAM mesh in ParaView."""
    
    # === Find STL surface ===
    triSurface_dir = os.path.join(case_dir, "constant", "triSurface")
    stl_files = glob.glob(os.path.join(triSurface_dir, "*.stl"))
    
    if not stl_files:
        print("[!] No STL file found in:", triSurface_dir)
        return
    
    stl_path = stl_files[0]
    print("[OK] STL surface:", stl_path)
    
    # === Create render view ===
    view = GetActiveViewOrCreate('RenderView')
    view.Background = [0.95, 0.95, 0.95]  # Light gray background
    view.InteractionMode = '2D'
    
    # === Load STL surface ===
    stl = CreateSource('STLReader')
    stl.FileName = stl_path
    rep_stl = Show(stl, view)
    rep_stl.Representation = 'Surface'
    rep_stl.DiffuseColor = (1.0, 0.35, 0.35)  # Red
    rep_stl.Specular = 0.4
    rep_stl.SpecularPower = 30
    print("[OK] STL surface rendered")
    
    # === Load OpenFOAM case ===
    foam_file = os.path.join(case_dir, "case.foam")
    if not os.path.exists(foam_file):
        print("[!] case.foam not found, skipping OpenFOAM mesh")
        view.ResetCamera()
        Render()
        state_file = os.path.join(case_dir, "surface_mesh_only.pvsm")
        SaveState(state_file)
        print("[OK] State saved:", state_file)
        os.system("/opt/paraview/bin/paraview " + state_file + " &")
        print("[OK] ParaView launched (mesh only)")
        return
    
    case_foam = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
    RenameSource('OpenFOAMReader1', case_foam)
    
    # Check decomposed case
    processor_dirs = glob.glob(os.path.join(case_dir, 'processor*'))
    if len(processor_dirs) > 0:
        case_foam.CaseType = 'Decomposed Case'
        print(f"Decomposed case: {len(processor_dirs)} processors")
    
    case_foam.Createcelltopointfiltereddata = 1
    case_foam.UpdatePipelineInformation()
    
    # Show mesh
    rep_mesh = Show(case_foam, view)
    rep_mesh.Representation = 'Surface'
    rep_mesh.AmbientColor = (0.2, 0.55, 0.8)  # Blue-ish
    rep_mesh.Specular = 0.3
    rep_mesh.SpecularPower = 20
    
    # === Camera ===
    view.ResetCamera()
    Render()
    
    # === Legend / info ===
    print(f"Mesh cells: {rep_mesh.NumberOfCells}")
    print(f"Mesh faces: {rep_mesh.NumberOfFaces}")
    
    # === Save state ===
    state_file = os.path.join(case_dir, "surface_mesh.pvsm")
    SaveState(state_file)
    print("[OK] State saved:", state_file)
    
    # === Launch ParaView GUI ===
    print("[OK] Launching ParaView...")
    os.system("/opt/paraview/bin/paraview " + state_file + " &")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: pvpython plot_surface_mesh.py <case_directory>")
        sys.exit(1)
    plot_surface_mesh(sys.argv[1])
