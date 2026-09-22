#!/usr/bin/env python3
"""Test: generate 10x6 STEP with pipe/sweep approach."""

import cadquery as cq
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
import math

nc = 40
def thk(t, tr):
    if t == 0: return 0
    return tr * (0.2969*math.sqrt(t) - 0.1260*t - 0.3516*t**2 + 0.2843*t**3 - 0.1015*t**4)

def make_airfoil_wire(c, tr):
    chord_m = c * 0.0254
    pts_u, pts_l = [], []
    for j in range(nc+1):
        tn = j/nc
        xl = (tn-0.25)*chord_m
        zl = thk(tn, tr)*chord_m
        pts_u.append(cq.Vector(xl, 0, zl))
        pts_l.append(cq.Vector(xl, 0, -zl))
    pts = pts_u + pts_l[::-1]
    edges = [cq.Edge.makeLine(pts[j], pts[j+1]) for j in range(len(pts)-1)]
    return cq.Wire.assembleEdges(edges)

# Parse PE0
with open('data/10x6-PERF.PE0') as f:
    lines = f.readlines()
data_lines = []
for line in lines:
    parts = line.strip().split()
    if len(parts) >= 10:
        try:
            float(parts[0]); float(parts[1]); float(parts[2])
            data_lines.append(parts)
        except: continue

radius = [float(d[0]) for d in data_lines]
chord = [float(d[1]) for d in data_lines]
pitch_q = [float(d[2]) for d in data_lines]
tr_arr = [float(d[7]) for d in data_lines]
hubrad = 0.5

# Build spine
spine_pts = []
valid_indices = []
for i in range(len(radius)):
    r_i = radius[i]; c_i = chord[i]; tr_i = tr_arr[i]; pitch_i = pitch_q[i]
    if r_i < hubrad: continue
    ac_offset_m = c_i * 0.25 * 0.0254
    pitch_rad = math.radians(pitch_i)
    le_x = ac_offset_m * math.cos(pitch_rad)
    le_y = r_i * 0.0254
    le_z = ac_offset_m * math.sin(pitch_rad)
    spine_pts.append(cq.Vector(le_x, le_y, le_z))
    valid_indices.append(i)

spine_edges = [cq.Edge.makeLine(spine_pts[i], spine_pts[i+1]) for i in range(len(spine_pts)-1)]
spine_wire = cq.Wire.assembleEdges(spine_edges)

idx0 = valid_indices[0]
profile = make_airfoil_wire(chord[idx0], tr_arr[idx0])

pipe = BRepOffsetAPI_MakePipe(spine_wire.wrapped, profile.wrapped)
pipe.Build()
blade_shape = pipe.Shape()
print(f'1. Blade (shell): type={blade_shape.ShapeType()}')

# Create hub using cadquery (handles orientation correctly)
hub = cq.Solid.makeCylinder(hubrad*0.0254, hubrad*2*0.0254, cq.Vector(0,0,0), cq.Vector(0,1,0))
hub_shape = hub.wrapped
print(f'2. Hub (cylinder): type={hub_shape.ShapeType()}')

# Fuse blade + hub using OCC
fuse1 = BRepAlgoAPI_Fuse(blade_shape, hub_shape)
fuse1.Build()
if fuse1.IsDone():
    blade_hub = fuse1.Shape()
    print(f'3. Blade U Hub: type={blade_hub.ShapeType()}')

    # Blade 2 = 180 rotation around Y
    tr2 = gp_Trsf()
    tr2.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,1,0)), math.pi)
    bt2 = BRepBuilderAPI_Transform(blade_hub, tr2)
    bt2.Build()
    blade2 = bt2.Shape()
    print(f'4. Blade2: type={blade2.ShapeType()}')

    # Fuse blade_hub + blade2
    fuse2 = BRepAlgoAPI_Fuse(blade_hub, blade2)
    fuse2.Build()
    if fuse2.IsDone():
        prop = fuse2.Shape()
        print(f'5. Full propeller: type={prop.ShapeType()}')

        # Export
        stepper = STEPControl_Writer()
        stepper.Transfer(prop, STEPControl_AsIs)
        status = stepper.Write('test/10x6.stp')
        print(f'STEP: {status} = {"OK" if status == IFSelect_RetDone else "FAIL"}')
        if status == IFSelect_RetDone:
            import os
            sz = os.path.getsize('test/10x6.stp')
            print(f'File size: {sz/1024:.0f} KB')
            print('\nSUCCESS!')
        else:
            print('Export FAILED')
    else:
        print('Fuse2 FAILED')
else:
    print('Fuse1 FAILED')
