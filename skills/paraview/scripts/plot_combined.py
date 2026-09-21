#!/usr/bin/env pvpython
"""
Combined visualization: patch + slice in same view.
Usage: pvpython plot_combined.py <case_dir> <patch> <patch_field> <slice_plane> <slice_value> <slice_field>

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS (or from args) ===
if len(sys.argv) >= 7:
    CASE_PATH = sys.argv[1]
    PATCH_NAME = sys.argv[2]
    PATCH_FIELD = sys.argv[3]
    SLICE_PLANE = sys.argv[4]
    SLICE_VALUE = float(sys.argv[5])
    SLICE_FIELD = sys.argv[6]
elif len(sys.argv) >= 2:
    CASE_PATH = sys.argv[1]
    PATCH_NAME = 'patch/wall'
    PATCH_FIELD = 'p'
    SLICE_PLANE = 'y'
    SLICE_VALUE = 0.0
    SLICE_FIELD = 'Umag'
else:
    print("Usage: pvpython plot_combined.py <case_dir> <patch> <patch_field> <slice_plane> <slice_value> <slice_field>")
    print("Example: pvpython plot_combined.py /path/to/case patch/wall p y 0 Umag")
    sys.exit(1)

print(f"Case: {CASE_PATH}")
print(f"Patch: {PATCH_NAME}, Field: {PATCH_FIELD}")
print(f"Slice: {SLICE_PLANE}={SLICE_VALUE}, Field: {SLICE_FIELD}")

# === CHECK DECOMPOSED ===
foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0
print(f"Decomposed: {is_decomposed}")

# === READER 1: PATCH ===
reader1 = OpenFOAMReader(registrationName='patch_reader', FileName=foam_file)
if is_decomposed:
    reader1.CaseType = 'Decomposed Case'

reader1.SkipZeroTime = 1
reader1.Createcelltopointfiltereddata = 1
reader1.UpdatePipelineInformation()

# Get time steps
time_steps = reader1.TimestepValues
last_time = time_steps[-1] if time_steps else 0
print(f"Time steps: {len(time_steps)}, Last: {last_time}")

reader1.MeshRegions = [PATCH_NAME]
reader1.CellArrays = [PATCH_FIELD]

# === READER 2: SLICE ===
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

# === SLICE FILTER ===
sliceFilter = Slice(registrationName=f'Slice_{SLICE_PLANE}{SLICE_VALUE}', Input=reader2)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [SLICE_VALUE]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]

if SLICE_PLANE == 'x':
    sliceFilter.SliceType.Normal = [1, 0, 0]
elif SLICE_PLANE == 'y':
    sliceFilter.SliceType.Normal = [0, 1, 0]
else:
    sliceFilter.SliceType.Normal = [0, 0, 1]

# Update at last time
UpdatePipeline(time=last_time, proxy=reader1)
UpdatePipeline(time=last_time, proxy=sliceFilter)

# === VIEW ===
view = GetActiveViewOrCreate('RenderView')

# Patch display (semi-transparent)
patchDisplay = Show(reader1, view, 'GeometryRepresentation')
patchDisplay.SetRepresentationType('Surface')
patchDisplay.Opacity = 0.5
ColorBy(patchDisplay, ('POINTS', PATCH_FIELD))
patchDisplay.SetScalarBarVisibility(view, True)

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
state_file = os.path.join(CASE_PATH, f'combined_{PATCH_FIELD}_{SLICE_FIELD}_slice{SLICE_PLANE}{SLICE_VALUE}.pvsm')
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"Animation: {len(time_steps)} time steps loaded, display: {last_time}")
print("Done!")
