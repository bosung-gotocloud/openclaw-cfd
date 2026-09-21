#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP File Analyzer - SALOME batch mode
Runs via: salome -t -b analyze_step_salome.py args:<dir>:<file.step>

Outputs:
    - {basename}_analysis.md  (detailed report)
    - {basename}-fixed.step   (if --fix requested)
"""

import sys
import os
import math
import statistics
from datetime import datetime
from collections import defaultdict

import salome
salome.salome_init()
from salome.geom import geomBuilder
geompy = geomBuilder.New()
import GEOM


def run_analyzer():
    """Main analysis using SALOME geompy."""
    # Parse args
    step_path = None
    fix_requested = False
    
    all_args = sys.argv[1:]
    # Also check os.environ in case salome passes args differently
    if not all_args:
        all_args = os.environ.get('SALOME_ARGS', '').split()
    
    for arg in all_args:
        if arg == '--fix':
            fix_requested = True
            continue
        if arg.startswith('args:'):
            arg = arg[5:]
            if ':' in arg:
                directory, filename = arg.split(':', 1)
                step_path = os.path.join(os.path.abspath(directory), filename)
            else:
                step_path = os.path.abspath(arg)
    
    if not step_path or not os.path.exists(step_path):
        print(f"ERROR: STEP file not found: {step_path}")
        sys.exit(1)
    
    base_name = os.path.splitext(os.path.basename(step_path))[0]
    base_dir = os.path.dirname(os.path.abspath(step_path))
    report_path = os.path.join(base_dir, f"{base_name}_analysis.md")
    fixed_path = os.path.join(base_dir, f"{base_name}-fixed.step")
    
    # Import STEP with correct units (salome handles units correctly)
    print(f"[1] Importing STEP: {step_path}")
    shape = geompy.ImportSTEP(step_path)
    
    # Basic properties
    print("[2] Analyzing geometry...")
    
    props = geompy.BasicProperties(shape)
    volume = props[2]
    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(shape)
    dx = x_max - x_min
    dy = y_max - y_min
    dz = z_max - z_min
    
    # Analyze face quality
    face_quality = []
    face_issues = []
    min_face_area = float('inf')
    max_face_area = 0
    
    faces_list = list(geompy.SubShapeAll(shape, geompy.ShapeType["FACE"]))
    edges_list = list(geompy.SubShapeAll(shape, geompy.ShapeType["EDGE"]))
    vertices_list = list(geompy.SubShapeAll(shape, geompy.ShapeType["VERTEX"]))
    n_faces = len(faces_list)
    n_edges = len(edges_list)
    n_vertices = len(vertices_list)
    
    for i, f in enumerate(faces_list):
        props_f = geompy.BasicProperties(f)
        area = props_f[2] if props_f[2] > 0 else props_f[1]
        fx_min, fx_max, fy_min, fy_max, fz_min, fz_max = geompy.BoundingBox(f)
        f_diag = ((fx_max-fx_min)**2 + (fy_max-fy_min)**2 + (fz_max-fz_min)**2)**0.5
        f_center = ((fx_min+fx_max)/2, (fy_min+fy_max)/2, (fz_min+fz_max)/2)
        
        face_quality.append({
            'index': i, 'area': area, 'diag': f_diag,
            'center': f_center
        })
        
        if area < min_face_area:
            min_face_area = area
        if area > max_face_area:
            max_face_area = area
        
        if area < 1e-10:
            face_issues.append({'index': i, 'type': 'zero_area', 'area': area})
        elif area < 1e-6:
            face_issues.append({'index': i, 'type': 'very_small_face', 'area': area})
    
    # Analyze edge quality
    edge_lengths = []
    edge_issues = []
    min_edge_len = float('inf')
    max_edge_len = 0
    
    for i, e in enumerate(edges_list):
        props_e = geompy.BasicProperties(e)
        length = props_e[1]
        edge_lengths.append(length)
        
        if length < min_edge_len:
            min_edge_len = length
        if length > max_edge_len:
            max_edge_len = length
        
        if length < 1e-10:
            edge_issues.append({'index': i, 'type': 'zero_length', 'length': length})
        elif length < 1e-6:
            edge_issues.append({'index': i, 'type': 'very_short_edge', 'length': length})
    
    # Face areas sorted
    face_areas_sorted = sorted([fq['area'] for fq in face_quality])
    edge_lengths_sorted = sorted(edge_lengths)
    
    if face_areas_sorted:
        area_std = statistics.stdev(face_areas_sorted) if len(face_areas_sorted) > 1 else 0
        max_area_ratio = max_face_area / min_face_area if min_face_area > 0 else 0
    else:
        area_std = 0
        max_area_ratio = 0
    
    # Severity
    total_issues = len(face_issues) + len(edge_issues)
    if total_issues > 10:
        severity = "🔴 CRITICAL"
    elif total_issues > 3:
        severity = "🟠 HIGH"
    elif total_issues > 0:
        severity = "🟡 MODERATE"
    else:
        severity = "🟢 GOOD"
    
    # Generate report
    report = []
    report.append(f"# STEP File Analysis Report\n")
    report.append(f"**File**: {os.path.basename(step_path)}\n")
    report.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Analyzer**: step-analyzer v1.1 (SALOME geompy)\n")
    report.append(f"---\n\n")
    
    report.append("## Overall Quality Summary\n\n")
    report.append(f"**Severity**: {severity}\n")
    report.append(f"**Total issues**: {total_issues}\n")
    report.append(f"**Volume**: {volume:.6f} m³\n")
    report.append(f"**BoundingBox**: {dx:.6f} x {dy:.6f} x {dz:.6f} m\n")
    report.append(f"**Faces**: {n_faces}\n")
    report.append(f"**Edges**: {n_edges}\n")
    report.append(f"**Vertices**: {n_vertices}\n")
    report.append(f"\n---\n\n")
    
    report.append("## Face Quality\n\n")
    if face_areas_sorted:
        report.append(f"- **Min area**: {min(face_areas_sorted):.6f} m²\n")
        report.append(f"- **Max area**: {max(face_areas_sorted):.6f} m²\n")
        report.append(f"- **Avg area**: {sum(face_areas_sorted)/len(face_areas_sorted):.6f} m²\n")
        report.append(f"- **Std dev**: {area_std:.6f} m²\n")
        report.append(f"- **Max/Min ratio**: {max_area_ratio:.0f}:1\n")
    
    report.append(f"\n## Min area face details\n\n")
    if face_quality:
        min_face = min(face_quality, key=lambda x: x['area'])
        report.append(f"- **Index**: {min_face['index']}\n")
        report.append(f"- **Area**: {min_face['area']:.6f} m²\n")
        report.append(f"- **Diagonal**: {min_face['diag']:.6f} m\n")
        report.append(f"- **Center**: ({min_face['center'][0]:.4f}, {min_face['center'][1]:.4f}, {min_face['center'][2]:.4f})\n")
    
    report.append(f"\n## Max area face details\n\n")
    if face_quality:
        max_face = max(face_quality, key=lambda x: x['area'])
        report.append(f"- **Index**: {max_face['index']}\n")
        report.append(f"- **Area**: {max_face['area']:.6f} m²\n")
        report.append(f"- **Diagonal**: {max_face['diag']:.6f} m\n")
        report.append(f"- **Center**: ({max_face['center'][0]:.4f}, {max_face['center'][1]:.4f}, {max_face['center'][2]:.4f})\n")
    
    report.append(f"\n## Edge Quality\n\n")
    if edge_lengths_sorted:
        report.append(f"- **Min length**: {min(edge_lengths_sorted):.6f} m\n")
        report.append(f"- **Max length**: {max(edge_lengths_sorted):.6f} m\n")
        report.append(f"- **Avg length**: {sum(edge_lengths_sorted)/len(edge_lengths_sorted):.6f} m\n")
    
    report.append(f"\n## Issues\n\n")
    if face_issues:
        report.append(f"### Face Issues\n\n")
        for issue in face_issues:
            report.append(f"- {'🔴' if issue['type']=='zero_area' else '🟠'} Face #{issue['index']}: {issue['type']} ({issue['area']:.6f} m²)\n")
    
    if edge_issues:
        report.append(f"\n### Edge Issues\n\n")
        for issue in edge_issues:
            report.append(f"- {'🔴' if issue['type']=='zero_length' else '🟠'} Edge #{issue['index']}: {issue['type']} ({issue['length']:.6f} m)\n")
    
    report.append(f"\n## Recommendations\n\n")
    
    recommendations = []
    if any(i['type'] == 'zero_area' for i in face_issues):
        recommendations.append("- Remove degenerate (zero-area) faces")
    if any(i['type'] == 'very_small_face' for i in face_issues):
        recommendations.append("- Merge or remove very small faces")
    if any(i['type'] == 'zero_length' for i in edge_issues):
        recommendations.append("- Remove zero-length edges")
    if max_area_ratio > 1000:
        recommendations.append(f"- **Large face area ratio ({max_area_ratio:.0f}:1)** may cause Netgen issues — consider face merging")
    if total_issues == 0:
        recommendations.append("- ✅ No critical issues found")
    recommendations.append("- Test with SetUseSurfaceCurvature(0) in Netgen meshing")
    
    for rec in recommendations:
        report.append(rec + "\n")
    
    report.append(f"\n---\n\n")
    report.append(f"**END OF REPORT**\n")
    
    # Write report
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(''.join(report))
    
    # Print summary to console
    print(f"\n{'='*60}")
    print(''.join(report))
    print(f"\nReport saved to: {report_path}")
    
    # Fix if requested
    if fix_requested:
        print(f"\n{'='*60}")
        print("GENERATING FIXED STEP FILE")
        print("="*60)
        
        try:
            # OCC sewing to repair topology
            from OCP.BRepOffsetAPI import BRepOffsetAPI_Sewing
            
            sewing = BRepOffsetAPI_Sewing(1e-6)
            sewing.Add(shape)
            sewing.SetTolerance(1e-6)
            sewing.Build()
            
            if not sewing.IsDone():
                print("Sewing failed: IsDone() = False")
                return
            
            fixed = sewing.SewedShape()
            
            # Export
            geompy.ExportSTEP(fixed, fixed_path, GEOM.LU_METER)
            print(f"Fixed STEP written to: {fixed_path}")
            
            # Verify
            props_fixed = geompy.BasicProperties(fixed)
            print(f"Fixed volume: {props_fixed[2]:.6f} m³")
            
        except Exception as e:
            print(f"Fix error: {e}")


if __name__ == "__main__":
    run_analyzer()
