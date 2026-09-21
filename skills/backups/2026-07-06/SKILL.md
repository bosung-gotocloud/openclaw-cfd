---
name: salome-tip_refine-snappy
description: SALOME-based mesh generation for snappyHexMesh with tip-wake line refinement. STEP import → Netgen mesh → snappyHexMesh case. Auto-discovers tip_points CSV for wake line refinement.
---

# salome-tip_refine-snappy Skill

SALOME-based two-step batch mesh generation for OpenFOAM's `snappyHexMesh`. Adds **tip-wake line refinement** on top of the original `salome-snappy` workflow — auto-discovers `{basename}_tip_points.csv` and generates X-direction wake lines from each tip point to the refine box xmax. Falls back to original refine-box-only mode if no tip CSV found.

**Based on:** `salome-snappy` skill (original untouched)
**Location:** `~/.openclaw/workspace/skills/salome-tip_refine-snappy/`
**SALOME path:** `/home/bosung/opt/salome/salome`

---

## ⚠️ Critical: Surface Curvature Must Be Enabled

**2026-07-06 discovery:** `SetUseSurfaceCurvature(1)` (Limit size surface curvature) **MUST be enabled** for stable STEP mesh computation. When disabled, mesh computation may fail or hang indefinitely on complex STEP files.

In `compute_mesh.py`, this is set via:
```python
params.SetUseSurfaceCurvature(1)
```

**Always confirm this line is present and set to `1`** before running `compute_mesh.py`. If modifying the script, do not remove or change this to `0`.

## ⚠️ Critical: Mesh Size Limit Must Be Disabled

**2026-07-06 discovery:** SALOME Netgen default mesh size limit is **500,000 elements**. This causes mesh computation to fail silently (returns False, no output) on large models.

In `compute_mesh.py`, **must** add:
```python
params.SetSizeLimit(0)  # 0 = unlimited
```

**Always confirm this line is present** before running `compute_mesh.py`. Without it, large STEP files will silently fail during `mesh.Compute()`.

---

## Batch Mode

```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```

**Always use `-t -b`** (terminal + batch) — no GUI, no server mode.

---

## Workflow Overview

```
STEP File + optional tip_points CSV
    │
    ▼
calculate_mesh_params.py   (Stage 1)
    ├─ STEP import + bbox
    ├─ Far-field box + tool solid
    ├─ Boolean Cut/Partition
    ├─ Face classification (far vs model)
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ Calculate mesh params (h1, T, surf_size, etc.)
    ├─ Generate wake lines (if tips found)
    ├─ Save {basename}_mesh_args.json
    └─ Save {basename}_geom.hdf
    │
    ▼  (user reviews & confirms)
    │
compute_mesh.py            (Stage 2)
    ├─ Rebuild geometry fresh from STEP
    ├─ Create refineBox volume group
    ├─ Create wake lines (if tips found)
    ├─ Netgen mesh: SetUseSurfaceCurvature(1) ← CRITICAL
    ├─ Mesh compute (no timeout)
    ├─ Export surface STL
    ├─ Export OpenFOAM polyMesh
    ├─ Setup snappyHexMesh case
    ├─ Parallel snappyHexMesh (mpirun --oversubscribe)
    └─ Auto-run checkMesh
```

---

## Step 1: Calculate Parameters

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Auto-Discovery:** If `{basename}_tip_points.csv` exists in the same directory as the STEP file, it is automatically loaded. CSV format: `x,y,z` header + data rows. If no CSV found, workflow continues in refine-box-only mode (same as original salome-snappy).

**Outputs:**
- `{filename}_geom.hdf` — Geometry study
- `{filename}_mesh_args.json` — Mesh parameters (includes tip fields if CSV found)

### JSON Schema

```json
{
  "step_path": "/path/to/file.stp",
  "base_dir": "/path/to/dir",
  "base_name": "LC62-50B",
  "geom_hdf": "/path/to/LC62-50B_geom.hdf",
  "xl": 2.1090,
  "yl": 2.3160,
  "zl": 0.6945,
  "h1": 0.0001,
  "layers": 5,
  "growth": 1.3524,
  "fineness": 2,
  "T": 0.00244,
  "BASE_MINTHICKNESS": 0.00122,
  "min_size": 0.00244,
  "surf_size": 0.02440,
  "max_size": 0.42180,
  "far_faces_count": 6,
  "model_faces_count": 73,
  "cube_dx": 21.090,
  "cube_dy": 11.580,
  "cube_dz": 6.945,
  "refine_dx": 10.545,
  "refine_dy": 4.632,
  "refine_dz": 1.389,
  "refine_local_size": 0.10545,
  "refine_cx": 10.545,
  "refine_cy": 0.0,
  "refine_cz": 0.0,
  "refine_tx": 0.0,
  "refine_ty": 0.0,
  "refine_tz": 0.0,
  "tip_csv_path": "/path/to/LC62-50B_tip_points.csv",
  "tip_points_count": 6,
  "tip_wake_lines": [[x1,y1,z1,x2,y2,z2], ...],
  "tip_wake_refine_size": 0.04880
}
```

**Tip fields** (`tip_csv_path`, `tip_points_count`, `tip_wake_lines`, `tip_wake_refine_size`) are only populated when a tip CSV is found. All other fields work identically to the original salome-snappy skill.

### ⚠️ Golden Rule — Edit JSON directly, not scripts

Show the parameter table, then allow the user to directly edit `{filename}_mesh_args.json` with any values they want to change. After user edits, re-display ALL calculated parameters (including any derived values that changed as a result). Do NOT re-run `calculate_mesh_params.py` for parameter changes — just edit the JSON file directly.

If the user changes `surf_size`, recompute derived values:
- `refine_local_size = max_size / 4` (if changed by user)

Show updated parameter table after every edit.

---

## Step 2: Compute Mesh (Auto-runs snappyHexMesh + checkMesh)

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

### Key Features

1. **Geometry rebuild from STEP** — fresh import, no dependency on geom.hdf
2. **Tip-wake lines** — if tip CSV found, creates wake lines from each tip → refine_box_xmax (X-direction)
3. **Netgen local size** — refineBox volume + wake lines get different cell sizes
4. **NO viscous layers** — layers added later by snappyHexMesh
5. **Critical:** `SetUseSurfaceCurvature(1)` enabled for stable computation
6. **Critical:** `SetSizeLimit(0)` enabled for unlimited mesh elements

### Mesh Setup Details (compute_mesh.py)

```python
mesh = smesh.Mesh(domain, f"{base_name}_mesh")
netgen = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)

params = netgen.Parameters()
params.SetNbThreads(8)
params.SetMaxSize(max_size)
params.SetMinSize(min_size)
params.SetLocalSizeOnShape(group_model, surf_size)
params.SetUseSurfaceCurvature(1)   # ← CRITICAL: must be 1
params.SetFineness(fineness)
params.SetSizeLimit(0)             # ← CRITICAL: unlimited mesh elements

# refineBox local size
netgen.SetLocalSizeOnShape(refine_box_volume_group, refine_local_size)

# wake lines local size (if tip CSV found)
if wake_line_objects:
    for wake_line in wake_line_objects:
        netgen.SetLocalSizeOnShape(wake_line, tip_wake_refine_size)
```

### Output

- `{filename}_mesh_setup.hdf` — Mesh setup (for manual tuning in SALOME GUI)
- `{filename}_mesh.hdf` — Computed mesh
- `{filename}-case/` — OpenFOAM case:
  - `constant/polyMesh/` — Volume mesh (points, faces, owner, neighbour, boundary, cellZones)
  - `constant/triSurface/{filename}_surface.stl` — Surface for snappyHexMesh layers
  - `system/snappyHexMeshDict` — Pre-configured with BL params
  - `system/controlDict` — Auto-fixed (writeInterval ≥ 1)
  - `log.snappyHexMesh` — snappyHexMesh output
  - `log.reconstructParMesh` — reconstruction log
  - `checkMesh.log` — checkMesh results

### Auto-execution in compute_mesh.py

1. Copies template case to `{filename}-case/`
2. Modifies snappyHexMeshDict with BL parameters from JSON
3. Fixes controlDict writeInterval (must be ≥ 1)
4. Mesh compute via `mesh.Compute()` (no timeout)
5. Export surface STL + OpenFOAM polyMesh
6. Parallel snappyHexMesh via mpirun
7. Reconstruct + checkMesh
8. Print checkMesh summary

---

## Refine Box (Wake Capture Volumetric Refinement)

Volumetric refinement of the wake region behind the STL object using **SALOME Netgen local size**.

### Parameters

| Parameter | Formula | Description |
|------|------|------|-----------|
| **refine_dx** | `5 × xl` | Streamwise X size (wake length) |
| **refine_dy** | `2 × STEP yl` | Spanwise Y size (STEP yl, NOT STL) |
| **refine_dz** | `2 × STEP zl` | Vertical Z size (STEP zl, NOT STL) |
| **Center** | `(cx, cy, cz)` | Object center |
| **Local size** | `max_size / 4` | Cell size inside refineBox |

### Tip Wake Lines (if CSV found)

| Parameter | Value | Description |
|------|------|------|
| **tip_wake_refine_size** | `2 × surf_size` | Wake line local cell size |
| **Line origin** | Tip point (x, y, z) | From CSV |
| **Line end** | `refine_box_xmax` | X-direction only |
| **Count** | Matches CSV row count | One line per tip point |

Wake lines extend from each tip point to the refine box xmax in the X direction. Cells along wake lines get `tip_wake_refine_size` (finer), intersecting with refine box cells gets `refine_local_size` (coarser). The smaller value wins in the intersection zone.

---

## Mesh Parameters

| Parameter | Description | Default |
|------|------|------|
| h1 | First cell height (snappyHexMesh) | 0.0001 m |
| layers | BL layer count (snappyHexMesh) | 5 |
| growth | BL growth rate (snappyHexMesh) | 1.3524 |
| fineness | Netgen density (2=mod/3=fine/4=vfine) | **2** |
| T | Total BL thickness | derived: `h1 × (growth^n - 1) / (growth - 1)` |
| min_size | Minimum mesh size | = T |
| surf_size | Surface mesh size | = **10 × T** |
| max_size | Max mesh size | = **10 × xl / 50** (= domain box X / 50) |
| BASE_MINTHICKNESS | Min layer thickness | = T × 0.5 |

---

## Parallel snappyHexMesh

compute_mesh.py runs snappyHexMesh in parallel using:
1. **Physical cores only** — `lscpu` → `Core(s) per socket × Socket(s)` (HyperThreading excluded)
2. **numberOfSubdomains** — `decomposeParDict` uses `numberOfSubdomains` (OpenFOAM v2512)
3. **--oversubscribe** — mandatory in `mpirun` for hyperthreading systems

### decomposeParDict

```foam
method        scotch;
numberOfSubdomains   <num_physical_cores>;
coeffs
{
    n (<num_procs> 1 1);
}
```

---

## Template Fixes

### snappyHexMeshDict maxGlobalCells
- **100,000,000** (large mesh support)

### 0/p, 0/U boundaryField
- Template `defaultFaces` patch only
- compute_mesh.py generates patch-specific boundaryField from polyMesh/boundary
- Prevents nested `{ }` duplicate errors

### controlDict writeInterval
- Auto-fixed from `0` → `1` + `writeControl timeStep` → `adjustableRunTime`

---

## Template Path

Script uses hardcoded path:
`/home/bosung/.openclaw/workspace/skills/salome-tip_refine-snappy/assets/snappyHexMesh-case-template/`

---

## File Structure

```
skills/salome-tip_refine-snappy/
├── SKILL.md                          ← this file
├── scripts/
│   ├── calculate_mesh_params.py      ← Stage 1: param calc + tip CSV discovery
│   └── compute_mesh.py               ← Stage 2: mesh + snappyHexMesh + checkMesh
└── assets/
    └── snappyHexMesh-case-template/
        ├── system/
        │   ├── controlDict
        │   ├── decomposeParDict
        │   ├── fvSchemes
        │   ├── fvSolution
        │   └── snappyHexMeshDict
        ├── constant/
        │   ├── polyMesh/
        │   └── triSurface/
        └── 0/
```

---

## Known Issues & Resolutions

| Issue | Resolution |
|-------|------|
| `surf_size` undefined when used in tip wake calc | Moved tip wake calc to Step 5 (after surf_size calculation) |
| `geompy.makeEdge` AttributeError | Changed to `geompy.MakeEdge` (PascalCase) |
| Template dir not found | Hardcoded path in compute_mesh.py |
| Wake line end x = STEP max X (wrong) | Fixed: end x = refine_box_xmax |
| Over-refinement causing timeout | Adjusted tip_wake_refine_size sizing |
| **STEP mesh fails/hangs without surface curvature** | **Enable `SetUseSurfaceCurvature(1)` — discovered 2026-07-06** |
| **Mesh compute silently fails / returns False** | **Add `params.SetSizeLimit(0)` — discovered 2026-07-06** |

---

## Backwards Compatibility

- If no `{basename}_tip_points.csv` exists → workflow proceeds exactly like original `salome-snappy`
- No tip-related JSON fields added if CSV not found
- `tip_wake_lines` check prevents errors in compute_mesh.py
- `skills/salome-snappy/` — **NOT MODIFIED**

---

## Workflow Rules

- **calculate_mesh_params.py 실행 후 반드시 모든 파라미터를 표로 보여주고 승인 받을 것**
- **사용자 승인 전에 compute_mesh.py 절대 실행 금지**
- 파라미터 계산 → 확인 → 승인 → 실행 (절대 순서 위반 금지)
- **Golden Rule:** JSON 직접 편집, 스크립트 수정 아님

---

## Comparison: salome-tip_refine-snappy vs salome-snappy

| Feature | salome-snappy | salome-tip_refine-snappy |
|---------|------|------|
| Tip CSV auto-discovery | ✗ | ✓ |
| Wake line refinement | ✗ | ✓ (X-direction from tips) |
| `tip_wake_refine_size` | ✗ | = `2 × surf_size` |
| Backwards compat | — | Fallback to refine-box-only |
| `SetUseSurfaceCurvature` | 1 | 1 (both) |
| `SetSizeLimit` | ✗ | 0 (both, added 2026-07-06) |
| Original file | Unchanged | Unchanged |

---

## Skill Backup

- `skills/backups/2026-07-04/salome-tip_refine-snappy/` exists (from initial backup)
- For updates: `cp -r skills/salome-tip_refine-snappy skills/backups/YYYY-MM-DD/`
