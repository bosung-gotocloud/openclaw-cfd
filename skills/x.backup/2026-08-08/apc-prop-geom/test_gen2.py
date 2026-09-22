#!/usr/bin/env python3
"""Test: generate 10x6 STEP with pipe/sweep approach."""
import cadquery as cq
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.gp import gp_Pnt
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
    w = BRepBuilderAPI_MakeWire()
    for j in range(len(pts)-1):
        p1 = gp_Pnt(pts[j].x, pts[j].y, pts[j].z)
        p2 = gp_Pnt(pts[j+1].x, pts[j+1].y, pts[j+1].z)
        edge = BRepBuilderAPI_MakeEdge(p1, p2)
        w.Add(edge.Edge())
    w.Build()
    return w.Wire()

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

spine_w = BRepBuilderAPI_MakeWire()
for i in range(len(spine_pts)-1):
    p1 = gp_Pnt(spine_pts[i].x, spine_pts[i].y, spine_pts[i].z)
    p2 = gp_Pnt(spine_pts[i+1].x, spine_pts[i+1].y, spine_pts[i+1].z)
    edge = BRepBuilderAPI_MakeEdge(p1, p2)
    spine_w.Add(edge.Edge())
spine_w.Build()
spine_wire_obj = spine_w.Wire()

idx0 = valid_indices[0]
profile = make_airfoil_wire(chord[idx0], tr_arr[idx0])

print(f'Spine: {len(spine_pts)} points, Profile: chord={chord[idx0]*25.4:.1f}mm')

sweep = BRepOffsetAPI_MakePipeShell(spine_wire_obj)
sweep.Add(profile)
sweep.SetMode(False)
sweep.Build()

if sweep.IsDone():
    shape = sweep.Shape()
    print(f'Sweep: type={shape.ShapeType()}')
    
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    vol = props.Mass()
    print(f'Volume: {vol*1e9:.1f} mm3')
    
    bb = Bnd_Box()
    BRepBndLib.Add_s(shape, bb)
    if not bb.IsVoid():
        xmin, ymin, zmin, xmax, ymax, zmax = bb.Get()
        print(f'BB: X=[{xmin*1000:.1f},{xmax*1000:.1f}] Y=[{ymin*1000:.1f},{ymax*1000:.1f}] Z=[{zmin*1000:.1f},{zmax*1000:.1f}] mm')
    
    # Export
    stepper = STEPControl_Writer()
    stepper.Transfer(shape, STEPControl_AsIs)
    status = stepper.Write('test/10x6.stp')
    print(f'STEP: {"OK" if status == IFSelect_RetDone else "FAIL"}')
    if status == IFSelect_RetDone:
        import os
        print(f'File: {os.path.getsize("test/10x6.stp")/1024:.0f} KB')
        print('\n=== SUCCESS ===')
    else:
        print('Export FAILED')
else:
    print('Sweep FAILED')
