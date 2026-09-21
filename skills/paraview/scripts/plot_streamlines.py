#!/usr/bin/env pvpython
"""
Visualize streamlines from a sphere source.
Usage: pvpython plot_streamlines.py <case_dir> [center_x] [center_y] [center_z] [radius]

Example: pvpython plot_streamlines.py /path/to/case 0.696 0.911 0.322 0.1

Loads ALL time steps and displays the LAST time step.
"""
from paraview.simple import *
import os
import sys
import glob

# === USER SETTINGS ===
if len(sys.argv) >= 6:
    CASE_PATH = sys.argv[1]
    CENTER = [float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])]
    RADIUS = float(sys.argv[5])
elif len(sys.argv) >= 2:
    CASE_PATH = sys.argv[1]
    CENTER = [0.0, 0.0, 0.0]
    RADIUS = 0.1
else:
    print("Usage: pvpython plot_streamlines.py <case_dir> [cx] [cy] [cz] [radius]")
    print("Example: pvpython plot_streamlines.py /path/to/case 0.696 0.911 0.322 0.1")
    sys.exit(1)

print(f"Case: {CASE_PATH}")
print(f"Streamline center: {CENTER}")
print(f"Radius: {RADIUS}")

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

# Select internal mesh and velocity field
reader.MeshRegions = ['internalMesh']
reader.CellArrays = ['U']

# === LOAD ALL TIME STEPS ===
print("Loading all time steps...")
UpdatePipeline(proxy=reader)
UpdatePipeline(time=last_time, proxy=reader)

# === CREATE SPHERE SOURCE FOR SEEDS ===
sphere = Sphere(registrationName='SeedSphere')
sphere.Center = CENTER
sphere.Radius = RADIUS
sphere.ThetaResolution = 8
sphere.PhiResolution = 8

# === STREAM TRACER WITH CUSTOM SOURCE ===
streamTracer = StreamTracerWithCustomSource(registrationName='Streamlines', Input=reader)
streamTracer.SeedSource = sphere

# Update at last time
UpdatePipeline(time=last_time, proxy=streamTracer)

# === VIEW ===
view = GetActiveViewOrCreate('RenderView')

# Show streamlines
display = Show(streamTracer, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', 'U'))
display.SetScalarBarVisibility(view, True)

# Also show mesh outline for reference
meshDisplay = Show(reader, view, 'GeometryRepresentation')
meshDisplay.SetRepresentationType('Outline')
meshDisplay.Opacity = 0.3

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
state_file = os.path.join(CASE_PATH, "streamlines.pvsm")
SaveState(state_file)
print(f"State saved: {state_file}")
print(f"Animation: {len(time_steps)} time steps loaded, display: {last_time}")
print("Done!")
