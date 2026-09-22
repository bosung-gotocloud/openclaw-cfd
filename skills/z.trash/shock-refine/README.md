# shock-refine — Shock-Based Mesh Refinement for HisA CFD Results

## Overview

This skill detects shock waves in hisa (compressible k-omega SST) simulation results and creates a refined mesh around the shock locations using edge subdivision.

## Workflow

```
1. User provides case directory containing hisa results + polyMesh
2. shock-sensor-v2.py analyzes latest time step → outputs shock cell IDs
3. Shock cells are extracted as STL for visualization
4. refine-mesh.py sub-divides shock cells by (0.5)^level
5. setup-refined-case.py copies config to case_root/refined-case/
6. Ready for re-simulation with refined mesh
```

## Files

- `scripts/shock-sensor-v2.py` — Multi-criteria shock detection
- `scripts/refine-mesh.py` — Edge subdivision mesh refinement
- `scripts/setup-refined-case.py` — Configuration copy and case setup

## Shock Detection Method

### Criteria (weighted sum)

| # | Criterion | Weight | Formula |
|---|-----------|--------|---------|
| 1 | Pressure gradient | α=0.40 | \|∇p\| × L_cell / p_ref |
| 2 | Density jump ratio | β=0.35 | Δρ/ρ_avg across faces |
| 3 | Vorticity spike | γ=0.15 | |\nabla×U| magnitude |
| 4 | Isentropic deviation | δ=0.10 | gradient of p/ρ^γ |

Combined score: S = α·S_p + β·S_ρ + γ·S_ω + δ·S_iso
Shock detected when S > threshold (default: 1.0)

## Usage Example

```bash
# Step 1: Detect shocks
python3 scripts/shock-sensor-v2.py --case /path/to/hisa-case --threshold 1.0 --level 1

# Step 2: Refine mesh
python3 scripts/refine-mesh.py \
    --case /path/to/hisa-case \
    --refined-case /path/to/case_root/refined-case \
    --shock-cells shock_cells.json \
    --level 1

# Step 3: Set up case config
python3 scripts/setup-refined-case.py \
    --case /path/to/hisa-case \
    --refined-case /path/to/case_root/refined-case
```

## Output Structure

```
case_root/
├── refined-case/
│   ├── polyMesh/        (refined mesh)
│   ├── 0/               (initial fields)
│   ├── constant/        (turbulence, transport props)
│   ├── system/          (controlDict, fvSchemes, fvSolution)
│   ├── shock_cells.json (detection results)
│   └── shock_cells.stl  (shock location visualization)
```

## Refinement Levels

| Level | Subdivision Ratio | Cells per Shock Cell Added |
|-------|------------------|---------------------------|
| 0 | 1.0 (no refinement) | 0 |
| 1 | 0.5 | ~7 (each cell → 8 sub-cells) |
| 2 | 0.25 | ~63 |
| 3 | 0.125 | ~511 |

## Dependencies

- numpy ≥ 1.21
- scipy ≥ 1.7 (for ConvexHull in STL output)
- Python ≥ 3.8
