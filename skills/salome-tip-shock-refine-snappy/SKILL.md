# salome-tip-shock-refine-snappy Skill

SALOME-based two-step batch mesh generation with **shock wave point-based local refinement** for OpenFOAM's `snappyHexMesh`. Adds shock CSV auto-discovery and vertex-based local sizing on top of the original `salome-tip_refine-snappy` workflow.

## Workflow Overview

```
STEP File + optional tip_points CSV + optional shock CSV
    │
    ▼ Stage 1: calculate_mesh_params.py
    ├─ STEP import + bbox calculation
    ├─ Auto-discover {basename}-shock-wave*.csv (NEW)
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ Shock point → vertex objects (if CSV found) ← NEW
    └─ Output: {basename}_mesh_args.json + {basename}_geom.hdf
    │
    ▼ Stage 2: compute_mesh.py
    ├─ SALOME Netgen mesh generation
    │   ├─ Refine box volumetric refinement
    │   ├─ tip_wake line local size (if tip CSV found)
    │   └─ shock_vertex local size (if shock CSV found) ← NEW
    ├─ Export surface STL for snappyHexMesh
    ├─ snappyHexMesh case setup + addLayers (viscous BL)
    ├─ Parallel decomposePar + snappyHexMesh + reconstructParMesh
    └─ checkMesh execution + log output
```

## Parameters

### Mesh Sizing Logic

| Parameter | Formula | Description |
|-----------|---------|-------------|
| `max_size` | `max(cube_dx, cube_dy, cube_dz) / 50` | Background mesh cell size (domain far-field) |
| **`T`** | **`h1 * (growth^layers - 1) / (growth - 1)`** | BL total thickness (**from salome-tip_refine-snappy**) |
| **`surf_size`** | **`4 × T`** | Surface mesh cell size (BL-based, **updated**) |
| **`min_size`** | **`2 × T`** | Minimum allowed cell size (auto-corrected) |
| `refine_local_size` | `max_size / 4` | Refine box local cell size |
| `tip_wake_refine_size` | `surf_size * 2` | Wake line refinement cell size |
| **`shock_refine_size`** | **`surf_size * 2`** | Shock point local cell size (**NEW**) |

### Auto-Correction Logic

- If STEP file's smallest face edge length < `min_size`, set `min_size = smallest_edge`
- Netgen cannot mesh faces smaller than its configured min_size

## Batch Execution

```bash
# Stage 1: Calculate parameters (always use -t -b for batch mode)
/home/bosung/opt/salome/salome -t -b scripts/calculate_mesh_params.py args:<case_dir>:<step_file.stp>

# Stage 2: Compute mesh with shock refinement
/home/bosung/opt/salome/salome -t -b scripts/compute_mesh.py args:<case_dir>:<basename>_mesh_args.json
```

## Shock CSV Format

Shock wave positions are defined in CSV files matching `{basename}-shock-wave*.csv`:

```csv
cellID,x,y,z,SI,h
1,0.5,0.0,0.0,1.0,0.001
2,0.6,0.0,0.0,1.0,0.001
...
```

- Columns 1,2,3: shock point x,y,z coordinates
- SI,h: additional mesh parameters (optional)

## Critical Notes

### Surface Curvature
`SetUseSurfaceCurvature(1)` MUST be enabled for stable STEP mesh computation.

### Viscous Layers
Viscous boundary layers are handled **after** SALOME meshing via `snappyHexMesh addLayers`. No viscous layer configuration in the SALOME step.

### No snappyHexMesh Dependency for Base Mesh
The base mesh (without shock refinement) is generated entirely by SALOME Netgen. The only snappyHexMesh usage here is for adding boundary layers on top of the pre-computed mesh.

## File Structure (Output)

```
{case_dir}/
├── {basename}_geom.hdf       - Geometry study file
├── {basename}_mesh_args.json - Computed mesh parameters
├── {basename}_mesh.hdf       - Final computed mesh
└── {basename}-case/          - OpenFOAM case directory
    ├── constant/
    │   ├── polyMesh/         - Volume mesh (points, faces, owner, neighbour)
    │   └── triSurface/       - Surface STL for snappyHexMesh
    ├── system/
    │   ├── snappyHexMeshDict - Pre-configured with BL parameters
    │   ├── controlDict
    │   ├── fvSchemes
    │   └── fvSolution
    ├── 0/                    - Initial fields (p, U)
    ├── processor*/           - Decomposed mesh (parallel runs)
    └── checkMesh.log         - Mesh quality report
```

## File Structure (Skill)

```
~/.openclaw/workspace/skills/salome-tip-shock-refine-snappy/
├── SKILL.md                  - This file
└── scripts/
    ├── calculate_mesh_params.py  - Stage 1: parameter calculation
    └── compute_mesh.py           - Stage 2: mesh computation
```
