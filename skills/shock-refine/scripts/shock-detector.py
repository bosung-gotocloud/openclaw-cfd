#!/usr/bin/env python3
"""
Shock-Detector v2 - SI 기반 충격파 감지 + vtu/stl/csv 출력

충격파 위치를 Sensor Index (SI) 기반으로 감지하고, 세 가지 output을 생성:
  1. vtu  - PyVista/Paraview 시각화용 (SI, Gp, h 등 cell data 포함)
  2. stl  - Shock interface surface (ASCII STL)
  3. csv  - 충격파 감지된 셀의 cellID + center (x, y, z)

기존 shock-detector.py(vtu만), step5_extract_stl.py(stl 추출) 기능을 통합.
full_pipeline.py는 변경/건드리지 않음.
"""

import argparse
import os
import csv
from pathlib import Path
import numpy as np
import pyvista as pv
from vtkmodules.vtkIOGeometry import vtkOpenFOAMReader
from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline


# ===================================================================
# 1. Argument parsing — 기존 shock-detector.py와 동일
# ===================================================================
parser = argparse.ArgumentParser(
    description="Calculate Sensor Index (SI) for the latest time step and output vtu/stl/csv."
)
parser.add_argument(
    "-case",
    required=True,
    type=str,
    help="Full path to the OpenFOAM case directory",
)
parser.add_argument(
    "--h_min",
    type=float,
    default=1e-3,
    help="Minimum cell size (m) for SI calculation. Cells with h < h_min are excluded.",
)
parser.add_argument(
    "--percentile",
    type=float,
    default=75.0,
    help="Percentile threshold for shock cell detection (default: 75)",
)
parser.add_argument(
    "--out-dir",
    type=str,
    default=None,
    help="Output directory (default: <case_root>/refined-case/)",
)
args = parser.parse_args()

case_dir = Path(args.case).resolve()
if not case_dir.exists() or not case_dir.is_dir():
    raise FileNotFoundError(f"Case directory does not exist: {case_dir}")

# Output directory: --out-dir 사용, 없으면 case_root/refined-case/
if args.out_dir:
    output_dir = Path(args.out_dir).resolve()
    case_root = case_dir.parent  # out_dir 지정 시 case_name을 위해 필요
else:
    case_root = case_dir.parent
    output_dir = case_root / "refined-case"
output_dir.mkdir(parents=True, exist_ok=True)

case_name = case_root.name
foam_file = case_dir / "case.foam"

# Dummy case.foam 생성 (기존 shock-detector.py 로직 동일)
if not foam_file.exists():
    foam_file.touch()
    print(f"Created empty stub file: {foam_file}")


# ===================================================================
# 2. VTK OpenFOAM Reader — 기존 shock-detector.py 로직 그대로
# ===================================================================
reader = vtkOpenFOAMReader()
reader.SetFileName(str(foam_file))
reader.SetCacheMesh(True)
reader.UpdateInformation()

info = reader.GetOutputInformation(0)
time_steps_key = vtkStreamingDemandDrivenPipeline.TIME_STEPS()

if info.Has(time_steps_key):
    num_time_steps = info.Length(time_steps_key)
    time_values = [info.Get(time_steps_key, i) for i in range(num_time_steps)]
    latest_time = int(time_values[-1])
    print(f"VTK identified {num_time_steps} time steps. Requesting latest time: {latest_time}")

    reader.EnableAllCellArrays()
    reader.UpdateTimeStep(latest_time)
else:
    print("Warning: VTK pipeline did not return time step array. Reading default state.")
    reader.EnableAllCellArrays()
    reader.Update()
    latest_time = 0


# ===================================================================
# 3. Internal mesh extraction + SI 계산 — 기존 shock-detector.py 로직 그대로
# ===================================================================
block = pv.wrap(reader.GetOutput())
grid = block["internalMesh"]

p = grid.cell_data["p"]
U = grid.cell_data["U"]

print(f"\nLoaded Time Step Field Check:")
print(f" - p (pressure) range: [{p.min():.4e}, {p.max():.4e}]")
print(f" - U (velocity) max mag: {np.linalg.norm(U, axis=1).max():.4e}")

if np.all(p == p[0]):
    print("CRITICAL WARNING: 'p' field is still uniform! Check case path or field files.")

# Cell volume & characteristic length h
grid = grid.compute_cell_sizes(length=False, area=False, volume=True)
vol = grid.cell_data["Volume"]
h = vol ** (1.0 / 3.0)

# Gradients
grid = grid.compute_derivative(
    scalars="p", gradient="grad_p", preference="cell"
)
grad_p = grid.cell_data["grad_p"]
mag_grad_p = np.linalg.norm(grad_p, axis=1)

grid = grid.compute_derivative(
    scalars="U", vorticity="vorticity", preference="cell"
)
vorticity = grid.cell_data["vorticity"]
mag_vorticity = np.linalg.norm(vorticity, axis=1)

# Gp and SI
p_safe = np.where(np.abs(p) < 1e-12, 1e-12, p)
Gp = h * (mag_grad_p / np.abs(p_safe))
SI = Gp / (1.0 + 0.01 * mag_vorticity)

# h_min filter
valid_mask = h >= args.h_min
cells_filtered = (~valid_mask).sum()
if cells_filtered > 0:
    SI = np.where(valid_mask, SI, 0.0)
    print(f"[h_min filter] Excluded {cells_filtered} cells with h < {args.h_min} m from shock detection")

# Store fields
grid.cell_data["h"] = h
grid.cell_data["Gp"] = Gp
grid.cell_data["SI"] = SI


# ===================================================================
# 4. Output 1: VTU — 기존 shock-detector.py 로직 그대로
# ===================================================================
output_vtu_name = f"{case_name}-{latest_time}.vtu"
output_vtu_path = output_dir / output_vtu_name
grid.save(str(output_vtu_path))
print(f"\n[Output 1] ✅ VTU saved: {output_vtu_path}")


# ===================================================================
# 5. Output 2: STL — step5_extract_stl.py 로직 통합
# ===================================================================
threshold = float(np.percentile(SI, args.percentile))
cell_mask = SI > threshold
n_refine_cells = int(cell_mask.sum())

if n_refine_cells > 0:
    print(f"\n[Output 2] Extracting {n_refine_cells} refined cells → STL ...")

    # Masked grid extraction → surface (PolyData)
    refined_grid = grid.extract_cells(cell_mask)
    poly = refined_grid.extract_surface(algorithm="dataset_surface")

    verts = poly.points
    faces_arr = poly.faces

    tri_list = []
    i = 0
    while i < len(faces_arr):
        nv = int(faces_arr[i])
        if nv == 3:
            tri_list.append([int(faces_arr[i+1]), int(faces_arr[i+2]), int(faces_arr[i+3])])
            i += 4
        elif nv > 3:
            base = int(faces_arr[i+1])
            for j in range(2, nv):
                tri_list.append([base, int(faces_arr[i+j]), int(faces_arr[i+j+1])])
            i += nv + 1
        else:
            i += 1

    faces = np.array(tri_list, dtype=np.int32)

    # Manual ASCII STL write (trimesh dependency 없이)
    stl_filename = f"{case_name}-{latest_time}_P{int(args.percentile)}.stl"
    stl_path = output_dir / stl_filename

    with open(stl_path, "w") as f:
        f.write("solid extracted_shock_interface\n")

        # Compute face normals manually
        v0_idx = faces[:, 0]
        v1_idx = faces[:, 1]
        v2_idx = faces[:, 2]
        v0 = verts[v0_idx]
        v1 = verts[v1_idx]
        v2 = verts[v2_idx]
        edge1 = v1 - v0
        edge2 = v2 - v0
        normals = np.cross(edge1, edge2)
        norm_mag = np.linalg.norm(normals, axis=1, keepdims=True)
        norm_mag = np.where(norm_mag == 0, 1e-16, norm_mag)
        normals = normals / norm_mag

        for i in range(len(faces)):
            normal = normals[i]
            f.write(
                f"facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n"
                f"  outer loop\n"
                f"    vertex {verts[v0_idx[i]][0]:.6f} {verts[v0_idx[i]][1]:.6f} {verts[v0_idx[i]][2]:.6f}\n"
                f"    vertex {verts[v1_idx[i]][0]:.6f} {verts[v1_idx[i]][1]:.6f} {verts[v1_idx[i]][2]:.6f}\n"
                f"    vertex {verts[v2_idx[i]][0]:.6f} {verts[v2_idx[i]][1]:.6f} {verts[v2_idx[i]][2]:.6f}\n"
                f"  endloop\n"
                f"endfacet\n"
            )

        f.write("endsolid extracted_shock_interface\n")

    print(f"[Output 2] ✅ STL saved: {stl_path}")
else:
    print(f"\n[Output 2] ⚠️ No refined cells (SI > {threshold:.4g}, P{args.percentile}) → STL skipped")


# ===================================================================
# 6. Output 3: CSV — Shock 감지 셀의 cellID + center(x,y,z)
# ===================================================================
if n_refine_cells > 0:
    # cell centers (vertices aren't the same as cell centers in OpenFOAM)
    cell_centers = grid.cell_centers().points  # Nx3 numpy array

    # Get cell IDs of refined cells
    refined_cell_ids = np.where(cell_mask)[0]

    csv_filename = f"{case_name}-{latest_time}_P{int(args.percentile)}.csv"
    csv_path = output_dir / csv_filename

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["cellID", "center_x", "center_y", "center_z", "SI", "h"])

        for cid in refined_cell_ids:
            c = cell_centers[cid]
            writer.writerow([
                int(cid),
                f"{c[0]:.8e}",
                f"{c[1]:.8e}",
                f"{c[2]:.8e}",
                f"{SI[cid]:.8e}",
                f"{h[cid]:.8e}"
            ])

    print(f"[Output 3] ✅ CSV saved: {csv_path}")
    print(f"          ({n_refine_cells} shock cells with SI > {threshold:.4g})")
else:
    print(f"\n[Output 3] ⚠️ No refined cells → CSV skipped")


# ===================================================================
# Summary
# ===================================================================
print(f"\n{'='*60}")
print("Shock-Detector v2 — Complete!")
print(f"  Output dir : {output_dir}")
print(f"  VTU        : {output_vtu_path.name if n_refine_cells > 0 else 'N/A'}")
print(f"  STL        : {stl_path.name if n_refine_cells > 0 else 'N/A'}")
print(f"  CSV        : {csv_path.name if n_refine_cells > 0 else 'N/A'}")
print(f"{'='*60}")
