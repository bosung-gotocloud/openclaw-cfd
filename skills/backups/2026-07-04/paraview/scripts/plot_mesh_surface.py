#!/usr/bin/env pvpython
"""
Plot OpenFOAM mesh surface.

Usage: pvpython plot_mesh_surface.py <case_directory>

Loads the OpenFOAM case and displays the mesh with surface representation.
"""
from paraview.simple import *
from paraview import vtk
import os
import glob

def plot_mesh_surface(case_dir):
    """Load OpenFOAM case and display mesh as surface."""
    
    # === Find case.foam ===
    foam_file = os.path.join(case_dir, 'case.foam')
    if not os.path.exists(foam_file):
        print("[!] case.foam not found:", foam_file)
        return
    
    # === Check decomposed ===
    processor_dirs = sorted(glob.glob(os.path.join(case_dir, 'processor*')))
    is_decomposed = len(processor_dirs) > 0
    
    # === Load case (same pattern as load_case.py) ===
    reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
    
    if is_decomposed:
        reader.CaseType = 'Decomposed Case'
        print(f"Decomposed case: {len(processor_dirs)} processors")
    
    reader.SkipZeroTime = 1
    reader.Createcelltopointfiltereddata = 1
    reader.UpdatePipelineInformation()
    
    time_steps = reader.TimestepValues
    if not time_steps:
        print("Error: No timesteps detected!")
        return
    
    last_time = time_steps[-1]
    print(f"Time steps: {len(time_steps)}, Last: {last_time}")
    
    # === Load all time steps ===
    print("Loading all time steps...")
    UpdatePipeline(proxy=reader)
    UpdatePipeline(time=last_time, proxy=reader)
    
    # === View ===
    view = GetActiveViewOrCreate('RenderView')
    view.Background = [0.3, 0.3, 0.3]  # Dark gray
    view.InteractionMode = '2D'
    
    # === Show mesh as surface ===
    display = Show(reader, view, 'GeometryRepresentation')
    display.SetRepresentationType('Surface')
    
    # Mesh styling
    display.AmbientColor = (0.2, 0.5, 0.8)  # Blue
    display.DiffuseColor = (0.2, 0.5, 0.8)
    display.Specular = 0.5
    display.SpecularPower = 25
    
    # === Camera angle ===
    view.ResetCamera()
    cam = view.GetActiveCamera()
    cam.Azimuth(30)
    cam.Elevation(30)
    cam.Zoom(1.0)
    view.UpdateCamera()
    
    # === Animation setup ===
    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    scene.StartTime = time_steps[0]
    scene.EndTime = last_time
    scene.AnimationTime = last_time
    scene.PlayMode = 'Snap To TimeSteps'
    
    # === Render ===
    view.ViewTime = last_time
    Render()
    
    # === Save state ===
    state_file = os.path.join(case_dir, 'mesh_surface.pvsm')
    SaveState(state_file)
    print(f"State saved: {state_file}")
    print(f"Mesh cells: {display.NumberOfCells}")
    print(f"Mesh faces: {display.NumberOfFaces}")
    print("Done!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: pvpython plot_mesh_surface.py <case_directory>")
        sys.exit(1)
    plot_mesh_surface(sys.argv[1])
