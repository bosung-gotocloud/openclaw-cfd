#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP File Analyzer - Uses SALOME geompy for correct unit handling.
Reports geometric quality and optionally generates cleaned STEP.

Usage:
    python analyze_step.py args:<directory>:<file.step> [--fix]
    python analyze_step.py args:/path/to/folder:myPart.stp
    python analyze_step.py args:/path/to/folder:myPart.stp --fix

Outputs:
    - {basename}_analysis.md  (detailed report)
    - {basename}-fixed.step   (if --fix requested and approved)
"""

import sys
import os
import math
import statistics
from datetime import datetime
from collections import defaultdict


def run_analyzer():
    """Main analysis using SALOME geompy."""
    # Parse args
    step_path = None
    fix_requested = False
    
    for arg in sys.argv[1:]:
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
    
    # Import SALOME GEOM
    import salome
    salome.salome_init()
    geompy = geomBuilder.New()
    
    # Import STEP with correct units
    print(f"[1] Importing STEP: {step_path}")
    shape = geompy.ImportSTEP(step_path)
    
    # Get basic properties
    print("[2] Analyzing geometry...")
    
    props = geompy.BasicProperties(shape)
    volume = props[2]  # volume is index 2
    x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(shape)
    dx = x_max - x_min
    dy = y_max - y_min
    dz = z_max - z_max
    
    faces = geompy.SubShapeAll(shape, geompy.ShapeType["FACE"])
    edges = geompy.SubShapeAll(shape, geompy.ShapeType["EDGE"])
    vertices = geompy.SubShapeAll(shape, geompy.ShapeType["VERTEX"])
    
    n_faces = geompy.GetSubShape(faces).getNumberOfSubShapes() if hasattr(faces, 'getNumberOfSubShapes') else geompy.GetSubShapeCount(faces)
    n_edges = geompy.GetSubShapeCount(edges)
    n_vertices = geompy.GetSubShapeCount(vertices)
    
    print(f"\n=== STEP Analysis (SALOME geompy) ===")
    print(f"  Volume: {volume:.6e} m³")
    print(f"  BoundingBox: {dx:.6f} x {dy:.6f} x {dz:.6f} m")
    print(f"  Faces: {n_faces}, Edges: {n_edges}, Vertices: {n_vertices}")
    print(f"  Center: ({(x_min+x_max)/2:.4f}, {(y_min+y_max)/2:.4f}, {(z_min+z_max)/2:.4f})")
    
    # Analyze face quality
    face_areas = []
    face_diags = []
    face_quality = []
    face_issues = []
    
    for i in range(n_faces):
        f = geompy.SubShape(faces, i)
        area = geompy.BasicProperties(f)[2]  # area for face
        fx_min, fx_max, fy_min, fy_max, fz_min, fz_max = geompy.BoundingBox(f)
        f_diag = ((fx_max-fx_min)**2 + (fy_max-fy_min)**2 + (fz_max-fz_min)**2)**0.5
        fc = geompy.MakeVectorDXDYDZ(0, 0, 0)
        center = geompy.MakeTranslation(f, (fx_min+fx_max)/2, (fy_min+fy_max)/2, (fz_min+fz_max)/2)
        
        face_areas.append(area)
        face_diags.append(f_diag)
        face_quality.append({
            'index': i,
            'area': area,
            'diag': f_diag,
            'center': ((fx_min+fx_max)/2, (fy_min+fy_max)/2, (fz_min+fz_max)/2)
        })
        
        if area < 1e-10:
            face_issues.append({'index': i, 'type': 'zero_area', 'area': area})
        elif area < 1e-6:
            face_issues.append({'index': i, 'type': 'very_small_face', 'area': area})
    
    # Analyze edge quality
    edge_lengths = []
    edge_issues = []
    for i in range(n_edges):
        e = geompy.SubShape(edges, i)
        length = geompy.BasicProperties(e)[1]  # length for edge
        edge_lengths.append(length)
        if length < 1e-10:
            edge_issues.append({'index': i, 'type': 'zero_length', 'length': length})
        elif length < 1e-6:
            edge_issues.append({'index': i, 'type': 'very_short_edge', 'length': length})
    
    # BRepCheck
    pass
    
    # Calculate statistics
    if face_areas:
        area_std = statistics.stdev(face_areas) if len(face_areas) > 1 else 0
    else:
        area_std = 0
    
    max_area_ratio = max(face_areas) / min(face_areas) if face_areas else 0
    
    # Severity assessment
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
    if face_areas:
        report.append(f"- **Min area**: {min(face_areas):.6f} m²\n")
        report.append(f"- **Max area**: {max(face_areas):.6f} m²\n")
        report.append(f"- **Avg area**: {sum(face_areas)/len(face_areas):.6f} m²\n")
        report.append(f"- **Std dev**: {area_std:.6f} m²\n")
        report.append(f"- **Max/Min ratio**: {max_area_ratio:.0f}:1\n")
    
    report.append(f"\n## Min area face details\n\n")
    min_face = min(face_quality, key=lambda x: x['area'])
    report.append(f"- **Index**: {min_face['index']}\n")
    report.append(f"- **Area**: {min_face['area']:.6f} m²\n")
    report.append(f"- **Diagonal**: {min_face['diag']:.6f} m\n")
    report.append(f"- **Center**: ({min_face['center'][0]:.4f}, {min_face['center'][1]:.4f}, {min_face['center'][2]:.4f})\n")
    
    report.append(f"\n## Max area face details\n\n")
    max_face = max(face_quality, key=lambda x: x['area'])
    report.append(f"- **Index**: {max_face['index']}\n")
    report.append(f"- **Area**: {max_face['area']:.6f} m²\n")
    report.append(f"- **Diagonal**: {max_face['diag']:.6f} m\n")
    report.append(f"- **Center**: ({max_face['center'][0]:.4f}, {max_face['center'][1]:.4f}, {max_face['center'][2]:.4f})\n")
    
    report.append(f"\n## Edge Quality\n\n")
    if edge_lengths:
        report.append(f"- **Min length**: {min(edge_lengths):.6f} m\n")
        report.append(f"- **Max length**: {max(edge_lengths):.6f} m\n")
        report.append(f"- **Avg length**: {sum(edge_lengths)/len(edge_lengths):.6f} m\n")
    
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
            from OCP.TopoDS import topods
            
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
