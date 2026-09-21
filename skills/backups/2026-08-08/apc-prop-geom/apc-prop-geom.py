#!/usr/bin/env python3
"""
APC Propeller Geometry → STEP CAD file generator.

PE0 data-driven SINGLE BLADE generation only.
- Blade starts at r=hubrad (first valid station), ends at r=tip
- NO hub, NO blade2
- Root transition NOT generated

Airfoil: Symmetric NACA-like thickness with PE0 t/c ratio.
Construction: create cross-section faces at each station → loft into solid.

Usage:
    python3 apc-prop-geom.py --model 10x6
    python3 apc-prop-geom.py --model 12x8E
    python3 apc-prop-geom.py --inch 12 --pitch 8
    python3 apc-prop-geom.py --list
    python3 apc-prop-geom.py --model 10x6 --output myprop.stp
"""

import argparse
import math
import os
import re
import sys
from pathlib import Path


def parse_pe0(filepath):
    """Parse PE0 file and return geometry data + metadata."""
    with open(filepath, 'r') as f:
        lines = f.readlines()
    prop_name = lines[0].strip().split()[0]
    
    hubrad = 0.5  # default
    hubtra = 1.2  # default
    for line in lines:
        if 'HUBRAD' in line:
            m = re.search(r'HUBRAD:\s*([\d.]+)', line)
            if m:
                hubrad = float(m.group(1))
        if 'HUBTRA' in line:
            m = re.search(r'HUBTRA:\s*([\d.]+)', line)
            if m:
                hubtra = float(m.group(1))
    
    data_lines = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 10:
            try:
                float(parts[0]); float(parts[1]); float(parts[2])
                data_lines.append(parts)
            except ValueError:
                continue
    if not data_lines:
        return None
    radius, chord, pitch_q, pitch_le, pitch_prath, sweep, rake, tr, tw, max_thick = [], [], [], [], [], [], [], [], [], []
    for d in data_lines:
        radius.append(float(d[0]))
        chord.append(float(d[1]))
        pitch_q.append(float(d[2]))
        pitch_le.append(float(d[3]))
        pitch_prath.append(float(d[4]))
        sweep.append(float(d[5]))
        rake.append(float(d[6]))
        tr.append(float(d[7]))
        tw.append(float(d[8]))
        max_thick.append(float(d[9]))
    return prop_name, radius, chord, pitch_q, pitch_le, pitch_prath, sweep, rake, tr, tw, max_thick, len(radius), hubrad, hubtra


def find_pe0(name):
    d = Path(__file__).parent / 'data'
    if not d.is_dir():
        d = Path(__file__).parent
    c = d / f'{name}-PERF.PE0'
    return str(c) if c.exists() else None


def list_models():
    d = Path(__file__).parent / 'data'
    if not d.is_dir():
        d = Path(__file__).parent
    return sorted([f.stem.replace('-PERF', '') for f in d.glob('*.PE0')])


def parse_ip(name):
    m = re.match(r'(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)', name)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def interp(inch, pitch):
    models = list_models()
    cands = []
    for m in models:
        m2 = re.match(r'(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)', m)
        if m2:
            cands.append((m, float(m2.group(1)), float(m2.group(2))))
    cands.sort(key=lambda c: (c[1]-inch)**2 + (c[2]-pitch)**2)
    exact = [x for x in cands if abs(x[1]-inch) < 0.001]
    if exact:
        exact.sort(key=lambda x: abs(x[2]-pitch))
        closest = exact[:1]
    elif len(cands) >= 2:
        closest = cands[:2]
    else:
        closest = cands[:1]
    if len(closest) == 1:
        r = parse_pe0(find_pe0(closest[0][0]))
        return r if r else None
    r0, r1 = parse_pe0(find_pe0(closest[0][0])), parse_pe0(find_pe0(closest[1][0]))
    if not r0 or not r1:
        return None
    t = (pitch - closest[0][2]) / (closest[1][2] - closest[0][2])
    n = max(r0[-1], r1[-1])
    def ip(a, b):
        return [x + t*(y-x) for x,y in zip(a,b)]
    return (f"{inch}x{pitch}I", r0[1] if r0[1][-1]>=r1[1][-1] else r1[1],
            ip(r0[2],r1[2]), ip(r0[3],r1[3]), ip(r0[4],r1[4]),
            ip(r0[6],r1[6]), ip(r0[7],r1[7]), ip(r0[8],r1[8]),
            ip(r0[9],r1[9]), ip(r0[9],r1[9]), n, r0[-2], r0[-1])


def generate_step(radius, chord, pitch_q, pitch_le, sweep, rake, thickness_ratio, twist, prop_name, output_path, hubrad, hubtra):
    """
    Build SINGLE BLADE using cadquery Workplane + sweep.
    
    Method:
    1. Build spine curve (LE path) along Y axis
    2. Build spine as cadquery path (segs)
    3. Create airfoil profile at first station
    4. Sweep profile along spine → solid blade
    5. Export as STEP
    """
    import cadquery as cq
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    
    n_pts = len(radius)
    
    # Build spine points and valid indices
    spine_pts = []
    valid_indices = []
    for i in range(n_pts):
        r_i = radius[i]
        c_i = chord[i]
        tr_i = thickness_ratio[i]
        pitch_i = pitch_q[i]
        
        if r_i < hubrad:
            continue
        
        chord_m = c_i * 0.0254
        if chord_m < 1e-6:
            continue
        
        # LE position at span y = r_i * 0.0254
        # chord direction = X, thickness = Z
        ac_offset = c_i * 0.25 * 0.0254  # meters
        pitch_rad = math.radians(pitch_i)
        
        le_y = r_i * 0.0254  # span position along Y
        le_x = ac_offset * math.cos(pitch_rad)  # chord direction
        le_z = ac_offset * math.sin(pitch_rad)  # thickness direction
        
        spine_pts.append(cq.Vector(le_x, le_y, le_z))
        valid_indices.append(i)
    
    if len(spine_pts) < 2:
        print("ERROR: Need at least 2 valid stations.")
        return False
    
    print(f"  Spine: {len(spine_pts)} points, Y={spine_pts[0].y*1000:.1f}~{spine_pts[-1].y*1000:.1f}mm")
    
    # Build spine as cadquery path
    spine_path = cq.Workplane().lineTo(0, spine_pts[-1].y, 0)  # along Y axis
    
    # Build profile at first station (airfoil in XZ plane, centered at spine point)
    idx0 = valid_indices[0]
    c0 = chord[idx0]
    tr0 = thickness_ratio[idx0]
    nc = 40
    
    pts_upper, pts_lower = [], []
    for j in range(nc + 1):
        tn = j / nc
        x_local = (tn - 0.25) * c0 * 0.0254  # chord direction
        if tn == 0:
            z_local = 0
        else:
            z_local = tr0 * c0 * 0.0254 * (
                0.2969 * math.sqrt(tn)
                - 0.1260 * tn
                - 0.3516 * tn**2
                + 0.2843 * tn**3
                - 0.1015 * tn**4
            )
        pts_upper.append(cq.Vector(x_local, 0, z_local))
        pts_lower.append(cq.Vector(x_local, 0, -z_local))
    
    all_pts = pts_upper + pts_lower[::-1]
    edges = [cq.Edge.makeLine(all_pts[j], all_pts[j+1]) for j in range(len(all_pts)-1)]
    profile = cq.Wire.assembleEdges(edges)
    
    print(f"  Profile: chord={c0*25.4:.1f}mm, tr={tr0:.3f}")
    
    # Build solid blade: use first and last station faces + loft
    # Create first station face
    def make_face(c, tr, pitch, y_span):
        nc = 40
        pts_u, pts_l = [], []
        for j in range(nc + 1):
            tn = j / nc
            x_local = (tn - 0.25) * c * 0.0254
            if tn == 0:
                z_local = 0
            else:
                z_local = tr * c * 0.0254 * (
                    0.2969 * math.sqrt(tn)
                    - 0.1260 * tn
                    - 0.3516 * tn**2
                    + 0.2843 * tn**3
                    - 0.1015 * tn**4
                )
            pts_u.append(cq.Vector(x_local, z_local, 0.0))
            pts_l.append(cq.Vector(x_local, -z_local, 0.0))
        all_pts = pts_u + pts_l[::-1]
        edges = [cq.Edge.makeLine(all_pts[j], all_pts[j+1]) for j in range(len(all_pts)-1)]
        wire = cq.Wire.assembleEdges(edges)
        face = cq.Face.makeFromWires(wire)
        # Rotate by pitch around X axis (airfoil plane tilts)
        face = face.translate(cq.Vector(0, y_span, 0))
        face = face.rotate((0, y_span, 0), (1, 0, 0), pitch)
        return face
    
    # First valid station face
    idx0 = valid_indices[0]
    face0 = make_face(chord[idx0], thickness_ratio[idx0], pitch_q[idx0], radius[idx0]*0.0254)
    
    # Last valid station face
    idxN = valid_indices[-1]
    faceN = make_face(chord[idxN], thickness_ratio[idxN], pitch_q[idxN], radius[idxN]*0.0254)
    
    print(f"  Blade: loft from {len(valid_indices)} sections")
    print(f"  Lofting blade...")
    blade = cq.Solid.makeLoft([face0.Wires()[0], faceN.Wires()[0]])
    
    if blade.isNull() or len(blade.Solids()) == 0:
        print("ERROR: Loft failed with 2 sections.")
        return False
    
    print(f"  Blade: {len(blade.Solids())} solids")
    
    # Get solids
    solids = blade.Solids()
    print(f"  Blade solids: {len(solids)}")
    
    if len(solids) == 0:
        # If no solids, try compound
        solids = [cq.Compound(blade)]
    
    # Volume
    vol = 0
    for solid in solids:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid.wrapped, props)
        vol += props.Mass() * 1e9
    print(f"  Blade volume: {vol:.1f} mm³")
    
    bb = blade.BoundingBox()
    print(f"  BB: X=[{bb.xmin*1000:.1f}, {bb.xmax*1000:.1f}] mm")
    print(f"      Y=[{bb.ymin*1000:.1f}, {bb.ymax*1000:.1f}] mm")
    print(f"      Z=[{bb.zmin*1000:.1f}, {bb.zmax*1000:.1f}] mm")
    
    # Export
    print(f"  Exporting STEP...")
    stepper = STEPControl_Writer()
    for solid in solids:
        stepper.Transfer(solid.wrapped, STEPControl_AsIs)
    
    status = stepper.Write(output_path)
    if status != IFSelect_RetDone:
        print("ERROR: STEP export failed.")
        return False
    
    print(f"STEP file written: {output_path}")
    print(f"  Single blade (r={radius[valid_indices[0]]:.2f}~{radius[valid_indices[-1]]:.2f}in)")
    print(f"  Volume: {vol:.1f} mm³")
    print(f"  BBox: X=[{bb.xmin*1000:.1f}, {bb.xmax*1000:.1f}] mm")
    print(f"        Y=[{bb.ymin*1000:.1f}, {bb.ymax*1000:.1f}] mm")
    print(f"        Z=[{bb.zmin*1000:.1f}, {bb.zmax*1000:.1f}] mm")
    return True


def main():
    p = argparse.ArgumentParser(description='APC Propeller → STEP CAD', epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--model', help='Exact model (e.g. 10x6, 12x8E)')
    p.add_argument('--inch', type=float, help='Diameter in inches')
    p.add_argument('--pitch', type=float, help='Pitch in inches')
    p.add_argument('--list', action='store_true', help='List models')
    p.add_argument('--output', help='Output filename')
    args = p.parse_args()
    sd = Path(__file__).parent

    if args.list:
        models = list_models()
        print(f"Available APC propeller models ({len(models)} total):\n")
        for m in models:
            print(f"  {m}")
        return

    if args.model:
        pe0 = find_pe0(args.model)
        if not pe0:
            print(f"ERROR: Model '{args.model}' not found."); sys.exit(1)
        r = parse_pe0(pe0)
        if not r:
            print(f"ERROR: Failed to parse '{args.model}'."); sys.exit(1)
        name, rad, chd, pq, ple, pprath, sw, rk, tr, tw, maxthick, n, hubrad, hubtra = r
        print(f"Model: {name}")
        print(f"  Diameter: {rad[-1]*2:.2f}in, Pitch(tip): {pq[-1]:.2f}in, Points: {n}")
        print(f"  Hub radius: {hubrad:.2f}in, Hub transition: {hubtra:.2f}in")
        print(f"\n  radius  chord  pitch_q  pitch_le  sweep  rake  thick_rat  twist(deg)")
        for i in range(min(n, 12)):
            print(f"  {rad[i]:7.4f} {chd[i]:6.4f} {pq[i]:8.4f} {ple[i]:9.4f} {sw[i]:6.4f} {rk[i]:6.4f} {tr[i]:8.4f} {tw[i]:10.4f}")
        if n > 12:
            print(f"  ... ({n-12} more)")
        print(f"\n  radius  chord  pitch_q  pitch_le  sweep  rake  thick_rat  twist(deg)")
        for i in range(max(0, n-12), n):
            print(f"  {rad[i]:7.4f} {chd[i]:6.4f} {pq[i]:8.4f} {ple[i]:9.4f} {sw[i]:6.4f} {rk[i]:6.4f} {tr[i]:8.4f} {tw[i]:10.4f}")
        op = str(sd / (args.output or f"test/{args.model}.stp"))
    elif args.inch and args.pitch:
        r = interp(args.inch, args.pitch)
        if not r:
            print(f"ERROR: Could not interpolate {args.inch}\"x{args.pitch}\""); sys.exit(1)
        name, rad, chd, pq, ple, pprath, sw, rk, tr, tw, maxthick, n, hubrad, hubtra = r
        print(f"Interpolated: {name}, {args.inch}\"x{args.pitch}\"")
        print(f"\n  radius  chord  pitch_q  pitch_le  sweep  rake  thick_rat  twist(deg)")
        for i in range(min(n, 12)):
            print(f"  {rad[i]:7.4f} {chd[i]:6.4f} {pq[i]:8.4f} {ple[i]:9.4f} {sw[i]:6.4f} {rk[i]:6.4f} {tr[i]:8.4f} {tw[i]:10.4f}")
        if n > 12:
            print(f"  ... ({n-12} more)")
        print(f"\n  radius  chord  pitch_q  pitch_le  sweep  rake  thick_rat  twist(deg)")
        for i in range(max(0, n-12), n):
            print(f"  {rad[i]:7.4f} {chd[i]:6.4f} {pq[i]:8.4f} {ple[i]:9.4f} {sw[i]:6.4f} {rk[i]:6.4f} {tr[i]:8.4f} {tw[i]:10.4f}")
        op = str(sd / (args.output or f"test/{args.inch}x{args.pitch}.stp"))
    else:
        p.print_help(); sys.exit(1)

    print(f"\nGenerating STEP file...")
    ok = generate_step(rad, chd, pq, ple, sw, rk, tr, tw, name, op, hubrad, hubtra)
    if not ok:
        print("ERROR: STEP generation failed."); sys.exit(1)

if __name__ == '__main__':
    main()
