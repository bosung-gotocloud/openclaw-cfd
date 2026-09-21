#!/usr/bin/env pvpython
"""
Slice at y=0 plane, visualize velocity magnitude.
Usage: pvpython slice_y0_Umag.py <case_dir>
"""
from paraview.simple import *
import os
import glob

CASE_PATH = sys.argv[1] if len(sys.argv) >= 2 else os.getcwd()

foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0

reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
if is_decomposed:
    reader.CaseType = 'Decomposed Case'

reader.Createcelltopointfiltereddata = 1
reader.UpdatePipelineInformation()
reader.MeshRegions = ['internalMesh']
reader.CellArrays = ['Umag']

time_steps = reader.TimestepValues
last_time = time_steps[-1] if time_steps else 0
UpdatePipeline(time=last_time, proxy=reader)

sliceFilter = Slice(registrationName='Slice_y0', Input=reader)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [0.0]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]
sliceFilter.SliceType.Normal = [0, 1, 0]
UpdatePipeline(time=last_time, proxy=sliceFilter)

view = GetActiveViewOrCreate('RenderView')
view.ViewTime = last_time
display = Show(sliceFilter, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', 'Umag'))

view.ResetCamera()
Render()

state_file = os.path.join(CASE_PATH, 'slice_y0_Umag.pvsm')
SaveState(state_file)
print(f"Slice Umag at y=0 saved: {state_file}")
