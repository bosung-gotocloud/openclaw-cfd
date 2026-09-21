#!/usr/bin/env pvpython
"""
Visualize field on a slice plane.
Usage: pvpython plot_slice.py <case_dir> [plane] [value] [field]

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS (or from args) ===
if len(sys.argv) >= 5:
    CASE_PATH = sys.argv[1]
    PLANE = sys.argv[2]  # x, y, or z
    VALUE = float(sys.argv[3])
    FIELD_NAME = sys.argv[4]
elif len(sys.argv) >= 2:
    CASE_PATH = sys.argv[1]
    PLANE = 'y'
    VALUE = 0.0
    FIELD_NAME = 'Umag'
else:
    print("Usage: pvpython plot_slice.py <case_dir> [plane] [value] [field]")
    print("Example: pvpython plot_slice.py /path/to/case y 0 Umag")
    sys.exit(1)

print(f"Case: {CASE_PATH}")
print(f"Slice: {PLANE} = {VALUE}")
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

# === CONFIGURE ===
reader.MeshRegions = ['internalMesh']
reader.CellArrays = [FIELD_NAME]

# === LOAD ALL TIME STEPS ===
print("Loading all time steps...")
UpdatePipeline(proxy=reader)

# === SLICE FILTER ===
sliceFilter = Slice(registrationName=f'Slice_{PLANE}{VALUE}', Input=reader)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [VALUE]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]

if PLANE == 'x':
    sliceFilter.SliceType.Normal = [1, 0, 0]
elif PLANE == 'y':
    sliceFilter.SliceType.Normal = [0, 1, 0]
else:  # z
    sliceFilter.SliceType.Normal = [0, 0, 1]

# Update at last time
UpdatePipeline(time=last_time, proxy=sliceFilter)

# === VIEW ===
view = GetActiveViewOrCreate('RenderView')
display = Show(sliceFilter, view, 'GeometryRepresentation')
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
state_file = os.path.join(CASE_PATH, f'slice_{PLANE}{VALUE}_{FIELD_NAME}.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"Animation: {len(time_steps)} time steps loaded, display: {last_time}")
print("Done!")
