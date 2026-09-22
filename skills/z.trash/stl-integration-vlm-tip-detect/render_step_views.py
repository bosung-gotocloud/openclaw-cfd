#!/usr/bin/env python3
"""
render_step_views.py — STEP 파일을 3방향 정사영 이미지로 렌더링 (PNG 4개)

출력:
  - {stepname}_front.png  (XZ 정사영, 상단에서 본 것)
  - {stepname}_top.png    (XY 정사영, 상단에서 본 것)
  - {stepname}_side.png   (YZ 정사영, 측면에서 본 것)
  - {stepname}_3d.png     (3D iso 뷰)

모든 이미지는 STEP 파일이 있는 디렉토리에 저장.
"""

import sys
import os
import numpy as np
import cadquery as cq

try:
    import matplotlib
    matplotlib.use('Agg')  # 비주얼 백엔드
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    print("ERROR: matplotlib 필요 — pip install matplotlib")
    sys.exit(1)


def render_front(shape_mm, ax, title, color=(0.2, 0.4, 0.8)):
    """XZ 정사영 (상단에서 본 것)"""
    verts, faces = shape_mm.tessellate(1.0)
    if verts is None or len(verts) == 0:
        return
    verts = np.array([[v.x, v.y, v.z] for v in verts])
    faces = np.array(faces)
    
    # XZ plane projection
    xs = verts[:, 0]
    zs = verts[:, 2]
    
    # face별로 색칠
    for face in faces:
        v0, v1, v2 = verts[face[0]], verts[face[1]], verts[face[2]]
        ax.fill([v0[0], v1[0], v2[0]], [v0[1], v1[1], v2[1]], 
                alpha=0.6, color=color)
    
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Z (m)')


def render_top(shape_mm, ax, title, color=(0.2, 0.8, 0.4)):
    """XY 정사영 (상단에서 본 것)"""
    verts, faces = shape_mm.tessellate(1.0)
    if verts is None or len(verts) == 0:
        return
    verts = np.array([[v.x, v.y, v.z] for v in verts])
    faces = np.array(faces)
    
    for face in faces:
        v0, v1, v2 = verts[face[0]], verts[face[1]], verts[face[2]]
        ax.fill([v0[0], v1[0], v2[0]], [v0[1], v1[1], v2[1]], 
                alpha=0.6, color=color)
    
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')


def render_side(shape_mm, ax, title, color=(0.8, 0.4, 0.2)):
    """YZ 정사영 (측면에서 본 것)"""
    verts, faces = shape_mm.tessellate(1.0)
    if verts is None or len(verts) == 0:
        return
    verts = np.array([[v.x, v.y, v.z] for v in verts])
    faces = np.array(faces)
    
    for face in faces:
        v0, v1, v2 = verts[face[0]], verts[face[1]], verts[face[2]]
        ax.fill([v0[1], v1[1], v2[1]], [v0[2], v1[2], v2[2]], 
                alpha=0.6, color=color)
    
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.set_xlabel('Y (m)')
    ax.set_ylabel('Z (m)')


def render_3d(shape_mm, ax3d, title):
    """3D iso 뷰"""
    from mpl_toolkits.mplot3d import Axes3D
    verts, faces = shape_mm.tessellate(1.0)
    if verts is None or len(verts) == 0:
        return
    verts = np.array([[v.x, v.y, v.z] for v in verts])
    faces = np.array(faces)
    
    ax3d.plot_trisurf(verts[:, 0], verts[:, 1], verts[:, 2], 
                    triangles=faces, color='steelblue', alpha=0.8, linewidth=0.5, edgecolor='gray')
    ax3d.set_title(title)
    ax3d.set_xlabel('X (m)')
    ax3d.set_ylabel('Y (m)')
    ax3d.set_zlabel('Z (m)')
    ax3d.set_box_aspect([1,1,1])


def main():
    if len(sys.argv) < 2:
        print("Usage: python render_step_views.py <input.stp>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"오류: 파일이 없습니다 — {input_path}")
        sys.exit(1)
    
    output_dir = os.path.dirname(os.path.abspath(input_path))
    basename = os.path.splitext(os.path.basename(input_path))[0]
    
    print(f"STEP 파일 로드 중: {input_path}")
    shape_mm = cq.importers.importStep(input_path, unit='MM').val()
    print(f"  mm로 로드 완료")
    
    bb = shape_mm.BoundingBox()
    bb_extent_mm = [bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin]
    print(f"  BBox (mm): [{bb_extent_mm[0]:.2f}, {bb_extent_mm[1]:.2f}, {bb_extent_mm[2]:.2f}]")
    
    # 3 방향 렌더링 (2x2 grid: 3 projection + 3D)
    fig = plt.figure(figsize=(20, 10))
    
    # Front (XZ)
    ax_front = fig.add_subplot(2, 2, 1)
    render_front(shape_mm, ax_front, f'{basename} Front (XZ)')
    
    # Top (XY)
    ax_top = fig.add_subplot(2, 2, 2)
    render_top(shape_mm, ax_top, f'{basename} Top (XY)')
    
    # Side (YZ)
    ax_side = fig.add_subplot(2, 2, 3)
    render_side(shape_mm, ax_side, f'{basename} Side (YZ)')
    
    # 3D (iso)
    ax_3d = fig.add_subplot(2, 2, 4, projection='3d')
    render_3d(shape_mm, ax_3d, f'{basename} 3D')
    
    plt.tight_layout()
    
    # 저장
    front_png = os.path.join(output_dir, f'{basename}_front.png')
    top_png = os.path.join(output_dir, f'{basename}_top.png')
    side_png = os.path.join(output_dir, f'{basename}_side.png')
    fig3d_png = os.path.join(output_dir, f'{basename}_3d.png')
    
    # 4장 저장
    fig.savefig(front_png, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # 3D 별도
    fig4 = plt.figure(figsize=(10, 10))
    ax4 = fig4.add_subplot(111, projection='3d')
    render_3d(shape_mm, ax4, f'{basename} 3D')
    fig4.savefig(fig3d_png, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # 3D 별도
    fig4 = plt.figure(figsize=(10, 10))
    ax4 = fig4.add_subplot(111, projection='3d')
    render_3d(shape_mm, ax4, f'{basename} 3D')
    fig4.savefig(fig3d_png, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    # bbox info도 CSV로 저장 (tip 위치 참고용)
    
    print(f"\n저장 완료:")
    print(f"  Front: {front_png}")
    print(f"  Top:   {top_png}")
    print(f"  Side:  {side_png}")
    print(f"  3D:    {fig3d_png}")
    
    # bbox info도 CSV로 저장 (tip 위치 참고용)
    bb_csv = os.path.join(output_dir, f'{basename}_bbox.csv')
    with open(bb_csv, 'w') as f:
        f.write('dim,extent_mm\n')
        f.write(f'xl,{bb_extent_mm[0]:.2f}\n')
        f.write(f'yl,{bb_extent_mm[1]:.2f}\n')
        f.write(f'zl,{bb_extent_mm[2]:.2f}\n')
        f.write(f'xmin,{bb.xmin:.2f}\n')
        f.write(f'xmax,{bb.xmax:.2f}\n')
        f.write(f'ymin,{bb.ymin:.2f}\n')
        f.write(f'ymax,{bb.ymax:.2f}\n')
        f.write(f'zmin,{bb.zmin:.2f}\n')
        f.write(f'zmax,{bb.zmax:.2f}\n')
    print(f"  BBox:  {bb_csv}")


if __name__ == '__main__':
    main()
