## Environment Setup

This skill requires OpenFOAM. Before executing any OpenFOAM commands (blockMesh, snappyHexMesh, etc.), the environment must be sourced:

```bash
source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc
```

Ensure this is included in your execution shell or added to your `.bashrc`.

## Environment Setup

This skill requires OpenFOAM. Before executing any OpenFOAM commands (blockMesh, snappyHexMesh, etc.), the environment must be sourced:

```bash
source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc
```

Ensure this is included in your execution shell or added to your `.bashrc`.

**Installation:** OpenFOAM v2512 installed at `/opt/OpenFOAM/OpenFOAM-v2512/`. The source line is already registered in `/etc/bash.bashrc` (system-wide).

> ⚠️ `exec` shell does NOT auto-source `.bashrc`. Always prepend OpenFOAM commands with `source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc &&`.

> ### SnappyHexMesh Full Workflow

## ⚠️ Golden Rule — Never Modify Template Files

**The template directory (`skills/snappyMesh/assets/snappyHexMesh-case-template/`) is READ-ONLY.**

## Workflow

### Step 0: Copy Scripts

**Always copy all scripts to the target STL directory first.** Never execute scripts from the skill directory directly.

```bash
cp /home/bosung/.openclaw/workspace/skills/snappyMesh/scripts/*.py <target_dir>/
```

### Execution Order

```
1. calculate_mesh_params.py <filename>.stl   → JSON 생성
2. block_mesh.py <filename>_mesh_args.json    → template 복사 → blockMeshDict 생성 → blockMesh 실행
3. snappy_mesh.py <filename>_mesh_args.json → STL 복사 → OBJ 생성 → snappyHexMeshDict 수정
                                              → boundary patch 확인 → 0/U 0/p 수정
                                              → decomposePar → snappyHexMesh 병렬 → reconstructParMesh
```

### Workflow Rules

1. **Always copy scripts to the target STL directory first**, then modify the **copies**.
2. **Always copy template case files to `{name}-case/`**, then modify those copies.
3. **Never modify template files** — `assets/` and `skills/snappyMesh/scripts/` are READ-ONLY.
4. **Show parameters as table** — Present all calculated parameters in a table.
5. **Ask for confirmation** — 반드시 파라미터 테이블을 보여주고 "proceed", "go", "yes" 또는 명시적인 승인을 받을 때까지 **절대로 다음 단계로 넘어가지 마세요**.
   - 파라미터 테이블을 표시하고, 파일 경로와 수정 가능 항목을 명시
   - 사용자가 직접 `{filename}_mesh_args.json`을 수정할 수 있도록 허용
   - 사용자가 확인하기 전까지 `block_mesh.py`, `snappy_mesh.py` 절대 실행 금지
6. **Iterate on changes** — 사용자가 파라미터를 수정한 경우, 계산 → 확인 → 수정 주기를 반복하세요.
7. **Execute step by step** — Run each phase sequentially and report results.
8. **Correct Working Directory** — ALWAYS execute OpenFOAM commands (`blockMesh`, `snappyHexMesh`, etc.) inside the `{name}-case` directory, NOT the root STL directory.
9. **Step-by-Step Mesh Preservation** — By default, do NOT use the `-overwrite` flag for `snappyHexMesh`. This ensures that each phase (castellation, snapping, layering) is saved as a separate time-step directory (e.g., `1`, `2`, `3`), allowing for later verification and debugging.

**Important:** Do not modify default values in the template scripts. If user requests changes, edit scripts *after* they have been copied to the STL file directory.

---

## Template Case

Located at: `~/.openclaw/workspace/skills/snappyMesh/assets/snappyHexMesh-case-template/`

Contains base files copied to `{name}-case/` by `block_mesh.py`. Modified by scripts at runtime.

**Far patch:** blockMesh에서 단일 `far` patch 1개 생성 (6 faces: ymin, xmax, ymax, xmin, zmin, zmax).

```
snappyHexMesh-case-template/
├── constant/
│   ├── polyMesh/
│   │   └── polyMesh          ← empty placeholder
│   └── triSurface/           ← created at runtime (STL copied here)
├── 0/
│   ├── p                     ← initial condition (calculated)
│   └── U                     ← initial condition (0 0 0)
└── system/
    ├── blockMeshDict           ← template, modified by block_mesh.py
    ├── snappyHexMeshDict       ← template, modified by snappy_mesh.py
    ├── controlDict             ← base config
    ├── fvSchemes               ← base config
    └── fvSolution              ← base config
```

---

## Parameters

### Far Field Box (same as Salome skill)

| Parameter | Description | Default |
|-----------|---|---|
| box_xl | Domain X = 10 × object xl | auto |
| box_yl | Domain Y = 5 × object yl (or 2.5 × object yl for half-span) | auto |
| box_zl | Domain Z = 10 × object zl | auto |
| span_type | "full" or "half" | "full" |

### BlockMesh

| Parameter | Description | Default |
|-----------|---|---|
| max_size | Background mesh max size | 0.1 |
| n_edge_x | Edge divisions X | auto (based on xl/max_size) |
| n_edge_y | Edge divisions Y | auto (based on yl/max_size) |
| n_edge_z | Edge divisions Z | auto (based on zl/max_size) |

### Castellations

| Parameter | Description | Default |
|------|---|-|
| castellations | Enable castellation | true |
| refinement_region | Region-based refinement (optional) | auto (refine box) |

### Refinement Regions (region-based volumetric refinement)

**Purpose:** Capture wake and flow features behind the STL body. Refines the near-field region downstream of the geometry where flow gradients are strongest (e.g., drag, lift, pressure wake). Without this region, the background mesh is too coarse to resolve boundary layer separation and wake dynamics.

Volumetric refinement using `searchableBox` geometry + `refinementRegions` in `castellatedMeshControls`.

**snappyHexMeshDict structure:**
```foam
geometry
{
    refine_box_surface
    {
        type searchableBox;
        min (refine_min_x refine_min_y refine_min_z);
        max (refine_max_x refine_max_y refine_max_z);
    }
}

castellatedMeshControls
{
    refinementRegions
    {
        refine_box_surface
        {
            mode    inside;   // "inside" or "outside"
            levels    ((1 N)); // min 1, max N (OpenFOAM v2512)
        }
    }
}
```

**How it works:**
- `geometry` section defines the searchableBox (min/max corners)
- `refinementRegions` in `castellatedMeshControls` references it by name
- `mode inside` = refine cells INSIDE the box; `outside` = OUTSIDE
- `levels ((1 N))` = min level 1, max level N (cells refined by 2^N inside)

**- `REFINEBOX_MIN`, `REFINEBOX_MAX`는 `(x y z)` 형식으로 감쌈 (OpenFOAM 벡터)
- `PATCH_NAME` → `STL_SURFACE`로 template에서 변경
- `STL_SURFACE` → `{stl_surface_name}`으로 snappy_mesh.py에서 대체**

| Dimension | Default Rule | Rationale |
|------|---|-|
| **X (streamwise)** | `0.5 × far_box_dx` (extends behind STL) | Must cover the region where wake forms and develops. Typical wake length ≈ 2-5× object length. Adjust larger for bluff bodies, smaller for streamlined. |
| **Y (spanwise)** | `2 × stl_y_size` | Just wide enough to cover the object span ± a margin for vortices shedding from edges. |
| **Z (vertical)** | `2 × stl_z_size` | Same as Y — covers the object height ± margin. |
| **Center** | `= far_box center` | Aligns with the domain center so the box sits behind the STL along the X-axis. |

> **Tuning tip:** For bluff body drag prediction, increase `refine_dx` toward `0.85 × far_box_dx` (or adjust `refine_tx` downstream) to push the refine box further downstream. For streamlined bodies, default is sufficient.

**Default calculation:**
| Parameter | Formula |
|------|-|
| refine_dx | 0.5 × far_box_dx (5 × xl) |
| refine_dy | 2 × stl_ysize |
| refine_dz | 2 × stl_zsize |
| refine_tx,y,z | cx - 1.25xl, cy - 1.25yl, cz - 2.5zl |
| refine_mode | "inside" |
| refine_level | = min_level (surface refinement level) |

**User modification in JSON:**
```json
{
  "refine_dx": 5.0,
  "refine_dy": 2.0,
  "refine_dz": 1.5,
  "refine_cx": 5.5,
  "refine_cy": 1.5,
  "refine_cz": 0.15,
  "refine_mode": "inside",
  "refine_level": 4
}
```

### Surface Refinement

| Parameter | Description | Default |
|-----------|---|---|
| n | Refinement level (surface) | **6** |
| min_size | Minimum cell size at surface | auto (= T) |
| surface_size | Surface face size | auto (= surf_size) |

### Surface Feature Edges Refinement

Detects and refines edges (feature edges) from the STL geometry. Controlled by `featureAngle` — edges with angles greater than this value are extracted and refined.

| Parameter | Description | Default |
|------|---|-|
| featureAngle | Angle threshold to detect feature edges (degrees) | **30** |
| feature_min_size | Minimum cell size near feature edges | derived (same as min_size) |

> **Note:** `featureAngle` is in degrees. Lower values detect more edges (sharper angles extracted). Typical range: 10–40.

### Snapping

| Parameter | Description | Default |
|-----------|---|---|
| snapping | Enable snapping | true |
| snap_tolerance | Snap tolerance | 0.1 |
| snap_iter | Snap iterations | 50 |
| snap_patch_min | Min surface points for patch snap | 3 |
| implicitSnap | Enable implicit snapping (snap to nearest surface point) | **true** |

### Add Layers

| Parameter | Description | Default |
|-----------|---|---|
| add_layers | Enable layer addition | true |
| n_layers | Boundary layer count | **5** |
| thickness (h1) | First layer thickness | 0.0001 |
| growth | Growth ratio | 1.3524 |
| BASE_MINTHICKNESS | Total boundary layer thickness (JSON key) | auto (`n_layers × thickness × (growth^n-1)/(growth-1)`) |
| total_thickness | Total BL thickness (optional) | auto (same as BASE_MINTHICKNESS) |
| expand_field | Expand field ratio | 1.2 |
| final_area | Final face area ratio | 0.5 |
| nSmoothSurfaceNormals | Smooth surface normals iterations | 1 |
| nSmoothNormals | Smooth layer normals iterations | 3 |
| nSmoothPatch | Smooth patch normals iterations | 4 |
| nRelaxIter | Relaxation iterations | 5 |
| nRemoveTermDist | Remove terminated layers iteration | 8 |
| featureAngle | Feature angle for layer start | 70 |
| separationRatio | Separation ratio for stuck layers | 0.2 |
| hingeAngle | Hinge angle for layers | 180 |

---

## Script Layout

### scripts/calculate_mesh_params.py
Reads STL bounding box → computes all mesh parameters → writes `{filename}_mesh_args.json`

### scripts/block_mesh.py
Copies template case → modifies blockMeshDict from JSON params → **runs blockMesh** → copies mesh to 0/ and constant/

### scripts/snappy_mesh.py
Copies STL to case/constant/triSurface/ → converts STL to OBJ → modifies snappyHexMeshDict → gets boundary patches → updates 0/U and 0/p → updates decomposeParDict → runs decomposePar → runs snappyHexMesh in parallel → runs reconstructPar
### scripts/geometry.py (optional)
SALOME-based geometry processing (STL import → bounding box → far box → face groups)

**STL file placement in snappy_mesh.py:** Copies `{basename}.stl` → `{case}/constant/triSurface/{basename}_surface.stl`. snappyHexMeshDict geometry references `{basename}_surface.stl` (triSurfaceMesh).

---

## Parameters JSON Schema

```json
{
  "base_name": "filename",
  "base_dir": "/path/to/stl",
  "xl": 1.0,
  "yl": 0.5,
  "zl": 0.3,
  "cx": 0.5,
  "cy": 0.25,
  "cz": 0.15,
  "h1": 0.0001,
  "layers": 5,
  "growth": 1.3524,
  "T": 0.00047,
  "min_size": 0.00047,
  "surf_size": 0.0047,
  "max_size": 0.02,
  "n": 6,
  "box_dx": 10.0,
  "box_dy": 2.5,
  "box_dz": 3.0,
  "tx": -4.5,
  "ty": -0.75,
  "tz": -1.35,
  "far_box_center": [5.5, 1.5, 0.15],
  "locationinmesh": [5.5, 1.5, 0.15],
  "snap_tolerance": [0.1, 0.1],
  "snap_iter": 50,
  "snap_patch_min": 3,
  "implicitSnap": true,
  "stl_surface_name": "filename_surface"
}
```

---

## Boundaries

- `far` — far-field boundary (single patch, 6 faces from blockMesh)
- `{filename}_surface` — model wall (snappyHexMesh)

> **Note (2026-05-26):** Far field은 blockMesh 단계에서 단일 `far` patch로 생성됩니다. (이전: `far_xmin`, `far_xmax`, `far_ymin`, `far_ymax`, `far_zmin`, `far_zmax` 6개 → `far` 1개). snappy_mesh.py에서 far patch 병합 로직 제거됨.

---

## Execution

### Script Copy Step
**Always copy all scripts to the target directory first:**
```bash
cp scripts/calculate_mesh_params.py <dir>/
cp scripts/block_mesh.py <dir>/
cp scripts/snappy_mesh.py <dir>/
```

### Workflow Execution (run inside target directory)
```bash
cd <dir>
python3 calculate_mesh_params.py <filename>.stl
# → JSON 생성

python3 block_mesh.py <filename>_mesh_args.json
# → Template case copied → blockMeshDict generated → blockMesh executed

python3 snappy_mesh.py <filename>_mesh_args.json
# → STL copied to case/constant/triSurface/
# → OBJ generated for feature extraction
# → snappyHexMeshDict modified
# → boundary patches detected → 0/U and 0/p updated
# → decomposePar executed
# → snappyHexMesh executed in parallel
# → reconstructPar executed
```

**Note:** `block_mesh.py` copies the full template case to `{name}-case/` and runs blockMesh. `snappy_mesh.py` works on the already-existing case — modifies snappyHexMeshDict, copies STL, updates boundary files, and runs the full parallel workflow.

---

## Notes

- Batch mode only (no GUI needed)
- All meshes created in case directory under `constant/polyMesh/`
- **All STL units are meters (m).** No unit conversion — STL is assumed to be in meters.
- **case directory structure:**
  ```
  {name}-case/
  ├── system/
  │   ├── blockMeshDict        ← modified by block_mesh.py
  │   ├── snappyHexMeshDict    ← modified by snappy_mesh.py
  │   ├── controlDict
  │   ├── fvSchemes
  │   └── fvSolution
  └── constant/
      ├── triSurface/
      │   └── {name}_surface.stl   ← STL copied here by snappy_mesh.py
      └── polyMesh/
          └── polyMesh          ← blockMesh output
  ```
