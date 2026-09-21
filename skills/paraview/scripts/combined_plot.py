#!/usr/bin/env pvpython
"""
Combined visualization: patch + slice in same view.
Usage: pvpython combined_plot.py <case_dir> <patch> <patch_field> <slice_plane> <slice_value> <slice_field>

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS ===
CASE_PATH = sys.argv[1] if len(sys.argv) > 1 else '/path/to/case'
WALL_PATCH = sys.argv[2] if len(sys.argv) > 2 else 'patch/wall_name'
WALL_FIELD = sys.argv[3] if len(sys.argv) > 3 else 'p'
SLICE_PLANE = sys.argv[4] if len(sys.argv) > 4 else 'y'
SLICE_VALUE = float(sys.argv[5]) if len(sys.argv) > 5 else 0
SLICE_FIELD = sys.argv[6] if len(sys.argv) > 6 else 'Umag'

foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0

print(f"Case: {CASE_PATH}")
print(f"Decomposed: {is_decomposed}")

# === LOAD CASE 1 (WALL) ===
reader1 = OpenFOAMReader(registrationName='wall_reader', FileName=foam_file)
if is_decomposed:
    reader1.CaseType = 'Decomposed Case'

reader1.SkipZeroTime = 1
reader1.Createcelltopointfiltereddata = 1
reader1.UpdatePipelineInformation()

# === TIMESTEP ===
time_steps = reader1.TimestepValues
if not time_steps:
    print("Error: No timesteps detected!")
    sys.exit(1)

last_time = time_steps[-1]
print(f"Time steps: {time_steps}")
print(f"Last time: {last_time}")

# === CONFIGURE WALL ===
reader1.MeshRegions = [WALL_PATCH]
reader1.CellArrays = [WALL_FIELD]

# === LOAD CASE 2 (SLICE) ===
reader2 = OpenFOAMReader(registrationName='slice_reader', FileName=foam_file)
if is_decomposed:
    reader2.CaseType = 'Decomposed Case'

reader2.SkipZeroTime = 1
reader2.Createcelltopointfiltereddata = 1
reader2.MeshRegions = ['internalMesh']
reader2.CellArrays = [SLICE_FIELD]

# === LOAD ALL TIME STEPS ===
print("Loading all time steps...")
UpdatePipeline(proxy=reader1)
UpdatePipeline(proxy=reader2)

# Update at last time
UpdatePipeline(time=last_time, proxy=reader1)

# === SLICE FILTER ===
sliceFilter = Slice(registrationName=f'Slice_{SLICE_PLANE}{SLICE_VALUE}', 
                    Input=reader2)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [float(SLICE_VALUE)]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]

if SLICE_PLANE == 'x':
    sliceFilter.SliceType.Normal = [1, 0, 0]
elif SLICE_PLANE == 'y':
    sliceFilter.SliceType.Normal = [0, 1, 0]
else:
    sliceFilter.SliceType.Normal = [0, 0, 1]

UpdatePipeline(time=last_time, proxy=sliceFilter)

# === SETUP VIEW ===
view = GetActiveViewOrCreate('RenderView')

# Wall display
wallDisplay = Show(reader1, view, 'GeometryRepresentation')
wallDisplay.SetRepresentationType('Surface')
wallDisplay.Opacity = 0.5
ColorBy(wallDisplay, ('POINTS', WALL_FIELD))
wallDisplay.SetScalarBarVisibility(view, True)

# Slice display
sliceDisplay = Show(sliceFilter, view, 'GeometryRepresentation')
sliceDisplay.SetRepresentationType('Surface')
ColorBy(sliceDisplay, ('POINTS', SLICE_FIELD))

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
state_file = os.path.join(CASE_PATH, f'wall_{WALL_FIELD}_{SLICE_FIELD}_slice{SLICE_PLANE}{SLICE_VALUE}.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"1. Wall: {WALL_PATCH}, {WALL_FIELD}")
print(f"2. Slice: {SLICE_PLANE}={SLICE_VALUE}, {SLICE_FIELD}")
print(f"Time steps: {len(time_steps)}, View time: {last_time}")
print("Done!")
