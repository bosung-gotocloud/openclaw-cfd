#!/usr/bin/env pvpython
"""
Render surface mesh from OpenFOAM case and save as image.

Usage: pvpython plot_surface_mesh_offscreen.py <case_directory> [output_image.png]

Renders the mesh with boundary layer visualization and saves to PNG.
"""
from paraview.simple import *
import os
import glob

def plot_surface_mesh_offscreen(case_dir, output_image=None):
    """Render OpenFOAM mesh to PNG image."""
    
    if output_image is None:
        output_image = os.path.join(case_dir, "mesh_surface.png")
    
    # === Load case ===
    foam_file = os.path.join(case_dir, "case.foam")
    if not os.path.exists(foam_file):
        print("[!] case.foam not found:", foam_file)
        return
    
    reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
    
    # Check decomposed
    processor_dirs = sorted(glob.glob(os.path.join(case_dir, 'processor*')))
    if len(processor_dirs) > 0:
        reader.CaseType = 'Decomposed Case'
        print(f"[OK] Decomposed case: {len(processor_dirs)} processors")
    
    reader.Createcelltopointfiltereddata = 1
    reader.UpdatePipelineInformation()
    
    # Get time steps
    time_steps = reader.TimestepValues
    if time_steps:
        last_time = time_steps[-1]
        print(f"[OK] Last time step: {last_time}")
    
    # === View ===
    view = GetActiveViewOrCreate('RenderView')
    view.Background = [0.3, 0.3, 0.3]  # Dark gray
    view.WindowSize = [1920, 1080]
    
    # === Show mesh (surface representation) ===
    rep = Show(reader, view)
    rep.Representation = 'Surface'
    rep.AmbientColor = (0.2, 0.5, 0.8)
    rep.DiffuseColor = (0.2, 0.5, 0.8)
    rep.Specular = 0.5
    rep.SpecularPower = 25
    
    # === Camera ===
    view.ResetCamera()
    cam = view.GetActiveCamera()
    cam.Azimuth(30)
    cam.Elevation(30)
    cam.Zoom(1.0)
    view.UpdateCamera()
    
    # === Render ===
    Render()
    
    # === Save image ===
    SaveScreenshot(output_image, window_size=[1920, 1080])
    print(f"[OK] Saved image: {output_image}")
    
    # === Save ParaView state ===
    state_file = os.path.join(case_dir, "surface_mesh.pvsm")
    SaveState(state_file)
    print(f"[OK] ParaView state: {state_file}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: pvpython plot_surface_mesh_offscreen.py <case_directory> [output_image.png]")
        sys.exit(1)
    case_dir = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) >= 3 else None
    plot_surface_mesh_offscreen(case_dir, output)
