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
reader.MeshRegions = ['patch/ball_surface']
reader.CellArrays = ['p']
reader.Createcelltopointfiltereddata = 1
UpdatePipeline()

view = GetActiveViewOrCreate('RenderView')
display = Show(reader, view, 'GeometryRepresentation')
display.SetRepresentationType('Surface')
ColorBy(display, ('POINTS', 'p'))

view.ResetCamera()
Render()

state_file = os.path.join(CASE_PATH, 'wall_p.pvsm')
SaveState(state_file)
print(f"Wall p saved: {state_file}")
