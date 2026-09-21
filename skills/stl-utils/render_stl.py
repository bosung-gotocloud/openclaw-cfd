#!/usr/bin/env python3
"""
render_stl.py — STL 다중뷰 렌더링 (정사영 + 3D iso)

Output files (in the same directory as the STL file):
    {name}_front.png   — XZ 정사영
    {name}_top.png     — XY 정사영
    {name}_side.png    — YZ 정사영
    {name}_3d.png      — 3D iso 뷰
    {name}_bbox.csv    — BBox 정보

Dependencies:
    pip install trimesh numpy matplotlib
"""

import sys
import os
import numpy as np
import csv
import argparse

try:
    import trimesh
except ImportError:
    print("ERROR: trimesh가 설치되어 있지 않습니다.")
    print("pip install trimesh")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def render_view(mesh, ax, view_name, color):
    """Render a single orthographic view on given matplotlib axes."""
    ax.set_title(view_name, fontsize=12)
    ax.set_aspect('equal')

    # Project mesh faces onto the view plane
    verts = mesh.vertices
    faces = mesh.faces

    if view_name == 'XZ':
        # Project along Y axis
        pts = verts[:, [0, 2]]  # X, Z
        ax.scatter(pts[:, 0], pts[:, 1], s=0.1, c=color, alpha=0.6)
    elif view_name == 'XY':
        # Project along Z axis
        pts = verts[:, [0, 1]]  # X, Y
        ax.scatter(pts[:, 0], pts[:, 1], s=0.1, c=color, alpha=0.6)
    elif view_name == 'YZ':
        # Project along X axis
        pts = verts[:, [1, 2]]  # Y, Z
        ax.scatter(pts[:, 0], pts[:, 1], s=0.1, c=color, alpha=0.6)


def render_iso(mesh, ax):
    """Render 3D iso view."""
    ax.set_title('3D Iso', fontsize=12)
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_zlim(-1, 1)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')

    # Plot mesh wireframe
    ax.plot_trisurf(mesh.vertices[:, 0], mesh.vertices[:, 1],
                    mesh.faces, verts=mesh.vertices,
                    color='lightblue', alpha=0.3, edgecolor='gray', linewidth=0.1)


def compute_bbox_csv(mesh):
    """Compute BBox info for CSV output."""
    mins = mesh.vertices.min(axis=0)
    maxs = mesh.vertices.max(axis=0)
    extents = maxs - mins

    return {
        'extent_mm': f"{extents[0]*1000:.2f}x{extents[1]*1000:.2f}x{extents[2]*1000:.2f}",
        'xmin_mm': mins[0] * 1000,
        'xmax_mm': maxs[0] * 1000,
        'ymin_mm': mins[1] * 1000,
        'ymax_mm': maxs[1] * 1000,
        'zmin_mm': mins[2] * 1000,
        'zmax_mm': maxs[2] * 1000,
        'vertex_count': len(mesh.vertices),
        'face_count': len(mesh.faces),
    }


def render_stl(path):
    """Main render function."""
    mesh = trimesh.load(path)
    if not isinstance(mesh, trimesh.Trimesh):
        if isinstance(mesh, trimesh.Scene):
            meshes = list(mesh.dump())
            if meshes:
                mesh = trimesh.util.concatenate(meshes)
            else:
                print("Error: No mesh data found.")
                sys.exit(1)
        else:
            print(f"Error: Cannot load {path}")
            sys.exit(1)

    # Convert mm to m
    if mesh.vertices.max() > 100:  # Heuristic: if max coord > 100, likely mm
        mesh.vertices *= 0.001

    step_name = os.path.splitext(os.path.basename(path))[0]
    step_dir = os.path.dirname(os.path.abspath(path))

    print(f"{'='*60}")
    print(f"STL Multi-view Rendering")
    print(f"{'='*60}")
    print(f"File: {path}")
    print(f"Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}")
    print(f"{'='*60}")

    if not HAS_MATPLOTLIB:
        print("ERROR: matplotlib이 필요합니다.")
        print("pip install matplotlib")
        sys.exit(1)

    # Render orthographic views
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.tight_layout()

    view_configs = [
        ('XZ', 'front', 'blue'),
        ('XY', 'top', 'green'),
        ('YZ', 'side', 'orange'),
    ]

    for ax, (view_name, view_label, color) in zip(axes, view_configs):
        render_view(mesh, ax, view_name, color)

    out_base = f"{step_name}"
    fig_path = os.path.join(step_dir, f"{out_base}_orthographic.png")
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Orthographic: {fig_path}")

    # 3D iso view
    fig3d = plt.figure(figsize=(10, 10))
    ax3d = fig3d.add_subplot(111, projection='3d')
    render_iso(mesh, ax3d)
    fig3d.tight_layout()
    fig3d_path = os.path.join(step_dir, f"{out_base}_3d.png")
    plt.savefig(fig3d_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  3D iso:       {fig3d_path}")

    # BBox CSV
    bbox = compute_bbox_csv(mesh)
    csv_path = os.path.join(step_dir, f"{out_base}_bbox.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['field', 'value'])
        writer.writerow(['extent_mm', bbox['extent_mm']])
        writer.writerow(['xmin_mm', bbox['xmin_mm']])
        writer.writerow(['xmax_mm', bbox['xmax_mm']])
        writer.writerow(['ymin_mm', bbox['ymin_mm']])
        writer.writerow(['ymax_mm', bbox['ymax_mm']])
        writer.writerow(['zmin_mm', bbox['zmin_mm']])
        writer.writerow(['zmax_mm', bbox['zmax_mm']])
        writer.writerow(['vertex_count', bbox['vertex_count']])
        writer.writerow(['face_count', bbox['face_count']])
    print(f"  BBox CSV:     {csv_path}")

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='STL multi-view rendering')
    parser.add_argument('input', help='Input STL file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    render_stl(args.input)


if __name__ == '__main__':
    main()
