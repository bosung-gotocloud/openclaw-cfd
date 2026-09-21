#!/usr/bin/env pvpython
"""
Visualize wall pressure on OpenFOAM case wall patch.
Usage: pvpython plot_pressure_wall.py <case_dir>

Finds wall patch from boundary file and visualizes pressure (p) on it.
"""
from paraview.simple import *
import os
import sys
import glob
import re

# === USER SETTINGS (or from args) ===
CASE_PATH = sys.argv[1] if len(sys.argv) >= 2 else os.getcwd()

print(f"Case: {CASE_PATH}")

# === CHECK DECOMPOSED ===
foam_file = os.path.join(CASE_PATH, 'case.foam')
if not os.path.exists(foam_file):
    print(f"Error: case.foam not found in {CASE_PATH}")
    sys.exit(1)

processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0
print(f"Decomposed: {is_decomposed}")

# === Find wall patch from boundary file ===
boundary_file = os.path.join(CASE_PATH, 'constant', 'polyMesh', 'boundary')
wall_patch = None
if os.path.exists(boundary_file):
    with open(boundary_file, 'r') as f:
        content = f.read()
    # Find wall-type patches
    matches = re.findall(r'(\S+)\s*\{\s*\n\t*\s*type\s+wall', content, re.MULTILINE)
    if matches:
        wall_patch = matches[0]
        print(f"Wall patch found: {wall_patch}")
    else:
        print("No wall-type patches found in boundary file")
        wall_patch = None

# === LOAD CASE ===
reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)

if is_decomposed:
    reader.CaseType = 'Decomposed Case'

reader.Createcelltopointfiltereddata = 1
reader.UpdatePipelineInformation()

# === TIMESTEP ===
time_steps = reader.TimestepValues
if not time_steps:
    print("Error: No timesteps detected!")
    sys.exit(1)

last_time = time_steps[-1]
print(f"Time steps: {len(time_steps)}, Last: {last_time}")

# === VIEW ===
view = GetActiveViewOrCreate('RenderView')
view.ViewTime = last_time

if wall_patch:
    # ParaView MeshRegions uses patch/name format (not bare name)
    pv_patch = f'patch/{wall_patch}'
    print(f'ParaView patch name: {pv_patch}')
    reader.MeshRegions = [pv_patch]
    reader.CellArrays = ['p']
    UpdatePipeline(time=last_time, proxy=reader)
    
    display = Show(reader, view, 'GeometryRepresentation')
    display.SetRepresentationType('Surface')
    ColorBy(display, ('POINTS', 'p'))
    
    print(f"Showing pressure on wall patch: {wall_patch}")
else:
    # No wall patch found - show internal mesh
    reader.MeshRegions = ['internalMesh']
    reader.CellArrays = ['p']
    UpdatePipeline(time=last_time, proxy=reader)
    
    display = Show(reader, view, 'GeometryRepresentation')
    display.SetRepresentationType('Surface')
    ColorBy(display, ('POINTS', 'p'))
    print("No wall patch found - showing internal mesh with p")

# === CONFIGURE ANIMATION ===
scene = GetAnimationScene()
scene.UpdateAnimationUsingDataTimeSteps()
scene.StartTime = time_steps[0]
scene.EndTime = last_time
scene.AnimationTime = last_time
scene.PlayMode = 'Snap To TimeSteps'

# === RENDER ===
view.ResetCamera()
Render()

# === SAVE STATE ===
state_file = os.path.join(CASE_PATH, 'pressure_wall.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print("Done!")
