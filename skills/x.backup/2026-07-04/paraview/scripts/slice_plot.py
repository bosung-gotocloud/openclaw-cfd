#!/usr/bin/env pvpython
"""
Plot field on slice plane.
Usage: pvpython slice_plot.py <case_dir> [plane] [value] [field]

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS ===
CASE_PATH = sys.argv[1] if len(sys.argv) > 1 else '/path/to/case'
SLICE_PLANE = sys.argv[2] if len(sys.argv) > 2 else 'y'
SLICE_VALUE = float(sys.argv[3]) if len(sys.argv) > 3 else 0
FIELD = sys.argv[4] if len(sys.argv) > 4 else 'Umag'

foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0

print(f"Case: {CASE_PATH}")
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
print(f"Time steps: {time_steps}")
print(f"Last time: {last_time}")

# === CONFIGURE REGIONS AND FIELDS ===
reader.MeshRegions = ['internalMesh']
reader.CellArrays = [FIELD]

# === LOAD ALL TIME STEPS ===
print("Loading all time steps...")
UpdatePipeline(proxy=reader)

# === SLICE FILTER ===
sliceFilter = Slice(registrationName=f'Slice_{SLICE_PLANE}{SLICE_VALUE}', Input=reader)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [float(SLICE_VALUE)]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]

if SLICE_PLANE == 'x':
    sliceFilter.SliceType.Normal = [1, 0, 0]
elif SLICE_PLANE == 'y':
    sliceFilter.SliceType.Normal = [0, 1, 0]
else:
    sliceFilter.SliceType.Normal = [0, 0, 1]

# Update at last time
UpdatePipeline(time=last_time, proxy=sliceFilter)

# === SETUP VIEW ===
view = GetActiveViewOrCreate('RenderView')
display = Show(sliceFilter, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', FIELD))
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
state_file = os.path.join(CASE_PATH, f'slice_{SLICE_PLANE}{SLICE_VALUE}_{FIELD}.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"Slice: {SLICE_PLANE} = {SLICE_VALUE}")
print(f"Field: {FIELD} (point data)")
print(f"Time steps: {len(time_steps)}, View time: {last_time}")
print("Done!")
