#!/usr/bin/env pvpython
from paraview.simple import *
import os
import glob

CASE_PATH = '/mnt/d/0.cfd/202601-KAU-Drone-Class/day1_examples/3.BARAM/magnus.bf/case'

foam_file = os.path.join(CASE_PATH, 'case.foam')
processor_dirs = sorted(glob.glob(os.path.join(CASE_PATH, 'processor*')))
is_decomposed = len(processor_dirs) > 0

reader = OpenFOAMReader(registrationName='case.foam', FileName=foam_file)
if is_decomposed:
    reader.CaseType = 'Decomposed Case'

reader.UpdatePipelineInformation()
reader.MeshRegions = ['internalMesh']
reader.CellArrays = ['Umag']
reader.Createcelltopointfiltereddata = 1
UpdatePipeline()

sliceFilter = Slice(registrationName='Slice_y0', Input=reader)
sliceFilter.SliceType = 'Plane'
sliceFilter.SliceOffsetValues = [0.0]
sliceFilter.SliceType.Origin = [0.0, 0.0, 0.0]
sliceFilter.SliceType.Normal = [0, 1, 0]
UpdatePipeline()

view = GetActiveViewOrCreate('RenderView')
display = Show(sliceFilter, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', 'Umag'))

view.ResetCamera()
Render()

state_file = os.path.join(CASE_PATH, 'slice_y0_Umag.pvsm')
SaveState(state_file)
print(f"Slice Umag saved: {state_file}")
