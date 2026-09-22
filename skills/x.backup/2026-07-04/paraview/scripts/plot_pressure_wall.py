#!/usr/bin/env pvpython
from paraview.simple import *

# Load decomposed case
casefoam = OpenFOAMReader(registrationName='case.foam', 
                          FileName='/mnt/d/0.cfd/202601-KAU-Drone-Class/day3_examples/3.supersonic_airfoil/supersonicwing.bf/case/case.foam')

# Set to only show the wall patch (supersonicwing_surface)
casefoam.MeshRegions = ['patch/supersonicwing_surface']

# Force update
casefoam.UpdatePipeline()

# Get render view
renderView = GetActiveViewOrCreate('RenderView')

# Show the wall patch
Show(casefoam, renderView)

# Color by pressure using the display representation
rep = GetRepresentation()
if rep:
    rep.ColorBy = ('POINTS', 'p')

# Set white background
renderView.Background = [1, 1, 1]

# Reset camera to fit
ResetCamera()

# Save state to the case directory
statePath = '/mnt/d/0.cfd/202601-KAU-Drone-Class/day3_examples/3.supersonic_airfoil/supersonicwing.bf/case/pressure_wall.pvsm'
SaveState(statePath)

print(f"SUCCESS: Saved state to {statePath}")
print("Wall patch: patch/supersonicwing_surface")
print("Field: p (pressure)")
print("Representation: Surface")
