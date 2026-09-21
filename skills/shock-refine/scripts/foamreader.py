import argparse
import os
from pathlib import Path
import numpy as np
import pyvista as pv
from vtkmodules.vtkIOGeometry import vtkOpenFOAMReader
from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline

# 1. Command-line argument parsing
parser = argparse.ArgumentParser(
    description="Calculate Sensor Index (SI) for the latest time step using VTK."
)
parser.add_argument(
    "-case",
    required=True,
    type=str,
    help="Full path to the OpenFOAM case directory",
)
args = parser.parse_args()

case_dir = Path(args.case).resolve()
if not case_dir.exists() or not case_dir.is_dir():
    raise FileNotFoundError(f"Case directory does not exist: {case_dir}")

# Define case_root and refined-case output directory
case_root = case_dir.parent
output_dir = case_root / "refined-case"
output_dir.mkdir(parents=True, exist_ok=True)

# 2. Ensure dummy case.foam file exists
foam_file = case_dir / "case.foam"
if not foam_file.exists():
    foam_file.touch()
    print(f"Created empty stub file: {foam_file}")

# 3. Initialize VTK OpenFOAM Reader
reader = vtkOpenFOAMReader()
reader.SetFileName(str(foam_file))
reader.SetCacheMesh(True)

# Update metadata to scan time directories
reader.UpdateInformation()

# 4. Get available time steps directly from VTK pipeline
info = reader.GetOutputInformation(0)
time_steps_key = vtkStreamingDemandDrivenPipeline.TIME_STEPS()

if info.Has(time_steps_key):
    num_time_steps = info.Length(time_steps_key)
    time_values = [info.Get(time_steps_key, i) for i in range(num_time_steps)]
    
    # Target the latest time step value
    latest_time = time_values[-1]
    print(f"VTK identified {num_time_steps} time steps. Requesting latest time: {latest_time}")
    
    # Enable all cell arrays before pipeline execution
    reader.EnableAllCellArrays()
    
    # Instruct VTK to load the specific time step
    reader.UpdateTimeStep(latest_time)
else:
    print("Warning: VTK pipeline did not return time step array. Reading default state.")
    reader.EnableAllCellArrays()
    reader.Update()

# 5. Extract internal mesh
block = pv.wrap(reader.GetOutput())
grid = block["internalMesh"]

# Field verification check
p = grid.cell_data["p"]
U = grid.cell_data["U"]

print(f"Loaded Time Step Field Check:")
print(f" - p (pressure) range: [{p.min():.4e}, {p.max():.4e}]")
print(f" - U (velocity) max mag: {np.linalg.norm(U, axis=1).max():.4e}")

if np.all(p == p[0]):
    print("CRITICAL WARNING: 'p' field is still uniform! Check case path or field files.")

# 6. Compute cell volume and characteristic length h
grid = grid.compute_cell_sizes(length=False, area=False, volume=True)
vol = grid.cell_data["Volume"]
h = vol ** (1.0 / 3.0)

# 7. Compute gradients and vorticity (using PyVista preference='cell')
grid = grid.compute_derivative(
    scalars="p", gradient="grad_p", preference="cell"
)
grad_p = grid.cell_data["grad_p"]
mag_grad_p = np.linalg.norm(grad_p, axis=1)

grid = grid.compute_derivative(
    scalars="U", vorticity="vorticity", preference="cell"
)
vorticity = grid.cell_data["vorticity"]

grid = grid.compute_derivative(
    scalars="vorticity", gradient="grad_vorticity", preference="cell"
)
grad_vorticity = grid.cell_data["grad_vorticity"]
mag_grad_vorticity = np.linalg.norm(grad_vorticity, axis=1)

# 8. Compute Gp and Sensor Index (SI)
p_safe = np.where(np.abs(p) < 1e-12, 1e-12, p)
Gp = h * (mag_grad_p / np.abs(p_safe))
SI = Gp / (1.0 + 0.01 * mag_grad_vorticity)

# 9. Store fields and save VTU output
grid.cell_data["h"] = h
grid.cell_data["Gp"] = Gp
grid.cell_data["SI"] = SI

output_file = output_dir / "processed_case_results.vtu"
grid.save(str(output_file))
print(f"Successfully saved calculated SI to: {output_file}")
