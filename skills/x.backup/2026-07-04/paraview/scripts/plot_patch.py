#!/usr/bin/env pvpython
"""
Visualize field on patch(es).
Usage: pvpython plot_patch.py <case_dir> [patch_name] [field_name]

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS (or from args) ===
if len(sys.argv) >= 4:
    CASE_PATH = sys.argv[1]
    PATCH_NAME = sys.argv[2]
    FIELD_NAME = sys.argv[3]
elif len(sys.argv) >= 2:
    CASE_PATH = sys.argv[1]
    PATCH_NAME = 'patch/wall'
    FIELD_NAME = 'p'
else:
    print("Usage: pvpython plot_patch.py <case_dir> [patch_name] [field_name]")
    print("Example: pvpython plot_patch.py /path/to/case patch/body p")
    sys.exit(1)

print(f"Case: {CASE_PATH}")
print(f"Patch: {PATCH_NAME}")
print(f"Field: {FIELD_NAME}")

# === CHECK DECOMPOSED ===
foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0
print(f"Decomposed: {is_decomposed}")

# === LOAD CASE ===
reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)

if is_decomposed:
    reader.CaseType = 'Decomposed Case'

reader.SkipZeroTime = 1
reader.Createcelltopointfiltereddata = 1
reader.UpdatePipelineInformation()

# === TIMESTEP ===
time_steps = reader.TimestepValues
if not time_steps:
    print("Error: No timesteps detected!")
    sys.exit(1)

last_time = time_steps[-1]
print(f"Time steps: {len(time_steps)}, Last: {last_time}")

# === CONFIGURE PATCH AND FIELD ===
reader.MeshRegions = [PATCH_NAME]
reader.CellArrays = [FIELD_NAME]

# === LOAD ALL TIME STEPS ===
print("Loading all time steps...")
UpdatePipeline(proxy=reader)

# === UPDATE AT LAST TIME ===
UpdatePipeline(time=last_time, proxy=reader)

# === VIEW ===
view = GetActiveViewOrCreate('RenderView')
display = Show(reader, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', FIELD_NAME))
display.SetScalarBarVisibility(view, True)

# === SET VIEW TO LAST TIME ===
view.ViewTime = last_time

# === CONFIGURE ANIMATION FOR ALL TIME STEPS ===
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
state_file = os.path.join(CASE_PATH, f'{FIELD_NAME}_{PATCH_NAME.replace("/", "_")}.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"Animation: {len(time_steps)} time steps loaded, display: {last_time}")
print("Done!")
