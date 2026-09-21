---
name: salome
description: Salome geometry and mesh processing for CFD. Use when user wants to import STEP/IGES files, create CFD domains, perform boolean operations, or generate meshes for OpenFOAM cases. Includes refineBox for wake capture volumetric refinement.
---

# Salome Geometry & Mesh Processing

## Salome Command

Use `/home/bosung/opt/salome/salome` (not in default PATH)

### Batch Mode (Primary - No GUI)
```bash
/home/bosung/opt/salome/salome withsession -t /full/path/to/script.py args:<directory>:<args>
```

All workflows run in batch mode. Scripts are passed arguments after `args:` as `directory:filename`.

### GUI Mode (Verification Only)
```bash
DISPLAY=:1 /home/bosung/opt/salome/salome withsession -g /full/path/to/study.hdf
```

Use GUI only to inspect results after batch processing.

---

## ⏱️ 실행 시간 가이드 (exec timeout)

SALOME 메쉬 생성은 **수 분 ~ 수 시간** 소요 (geometr size, fineness에 따라). `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (파라미터 계산) | `timeoutSeconds: 300` (STEP import 포함) |
| `compute_mesh.py` (메쉬 생성) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |
| `export_airfoil_sections.py` (airfoil export) | `timeoutSeconds: 300` |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

---

## Mesh Workflow (Two-Step Batch)

### Workflow Rules

1. **Copy template scripts to directory** — Copy both `calculate_mesh_params.py` and `compute_mesh.py` to the directory containing the STEP file.
2. **Calculate parameters** — Run `calculate_mesh_params.py` to analyze geometry, derive mesh sizes, and create the `{filename}_mesh_args.json` file.
3. **Show variables as table** — Present the calculated variables in a table including descriptions (e.g., `min_size = T`, `surf_size = 10xT`).
4. **Ask for confirmation** — Stop and explicitly ask the user to confirm before proceeding to Step 2. Display all calculated parameters and wait for "proceed", "go", "yes", or explicit approval.
5. **Iterate on changes** — If any variables are changed, repeat from Step 2 (run calculate and show the updated table).
6. **Compute mesh** — Once confirmed, run `compute_mesh.py` using the JSON args.

**Important:** Do not modify the default values in the template scripts located in the skill directory. If the user requests a change to default values, edit the scripts *after* they have been copied to the STEP file directory.

Both steps run in **batch mode** (no GUI).

### Step 1: Calculate Parameters

```bash
cp ~/.openclaw/workspace/skills/salome/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome withsession -t <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Outputs:**
- `{filename}_geom.hdf` — Geometry study
- `{filename}_mesh_args.json` — Mesh parameters (editable)

### Step 2: Compute Mesh

```bash
cp ~/.openclaw/workspace/skills/salome/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome withsession -t <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

**Outputs:**
- `{filename}_mesh_setup.hdf` — Mesh configuration
- `{filename}_mesh.hdf` — Computed mesh
- `{filename}-constant/polyMesh/` — OpenFOAM export

### Mesh Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| h1 | First cell height | **0.0001** |
| layers | BL layer count | 5 |
| growth | BL growth rate | 1.3524 |
| fineness | Netgen density (2=mod/3=fine/4=vfine) | 3 |
| **T** | h1×(growth^layers-1)/(growth-1) | derived |
| min_size | = T | T |
| surf_size | = 10×T | 10×T |
| max_size | = max(cube_dx,cube_dy,cube_dz)/50 | derived |

### Refine Box (Wake Capture Volumetric Refinement)

Volumetric refinement of the wake region behind the STEP object using **SALOME Netgen local size**. Same sizing rules as the `salome-snappy` skill.

| Parameter | Formula | Description |
|-----------|---------|-------------|
| **refine_dx** | `0.5 × far_box_dx` | Streamwise X size (wake length) |
| **refine_dy** | `2 × STEP_yl` | Spanwise Y size (STEP yl, NOT STL) |
| **refine_dz** | `2 × STEP_zl` | Vertical Z size (STEP zl, NOT STL) |
| **Center** | `= far_box_center` | Same center as far box domain |
| **Local size** | `surf_size × 2` (default) | Cell size inside refineBox (Netgen) |
| **Multiplier override** | JSON `refine_local_multiplier` | Set to change multiplier |
| **Size override** | JSON `refineBox_cell_size_override` | Direct override of local cell size |

SALOME Implementation:
1. Cube created at (0,0,0) with `MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)`
2. Translated to position using `refine_tx, refine_ty, refine_tz`
3. Volume group created (`refineBox_volume`)
4. Netgen `SetLocalSizeOnShape` applied with local size

### Quick Workflow

```bash
# Step 1: Copy both scripts to step directory
cp calculate_mesh_params.py <dir>/
cp compute_mesh.py <dir>/

# Step 2: Calculate parameters (shows all values, stops before mesh)
salome withsession -t <dir>/calculate_mesh_params.py args:<dir>:<file.stp>

# Step 3: Review output, edit <dir>/<file>_mesh_args.json if needed

# Step 4: Compute mesh
salome withsession -t <dir>/compute_mesh.py args:<dir>:<file>_mesh_args.json
```

### Change Mesh Parameters

Edit the JSON file before running compute_mesh:

```json
{
  "h1": 0.0002,
  "layers": 8,
  "growth": 1.3,
  "fineness": 4,
  "refine_local_size": 0.04
}
```

### Boundaries

- `far` — far-field patch
- `{filename}_surface` — model wall

---

## APC Propeller Airfoil Export

Use `export_airfoil_sections.py` to generate airfoil cross-section wires from APC .PE0 data.

### Execution

```bash
cp ~/.openclaw/workspace/skills/apc-prop-geom/export_airfoil_sections.py <directory>/
/home/bosung/opt/salome/salome withsession -t <directory>/export_airfoil_sections.py args:<directory>:<pe0_file.PE0>
```

**Outputs:**
- `{base_name}_sections.hdf` — Salome Study containing wire sections (one per station)

Each station → one closed wire loop (airfoil cross-section line). No hub, no blades, no loft.

### Verification

```bash
DISPLAY=:1 /home/bosung/opt/salome/salome withsession -g <directory>/<base_name>_sections.hdf
```

### Notes

- PE0 file path can be absolute or relative to work_dir
- Airfoil: symmetric Clark-Y formula with PE0 t/c ratio
- Twist applied around Y axis (propeller rotation axis)
- Points generated with 0→2π full loop (upper + lower surface) → proper closed wire

---

## Geometry Workflow

### Standard Steps

1. **Import STEP/IGES file**
2. **Get bounding box** → calculate dimensions (xl, yl, zl)
3. **Create domain cube** → 10xl × 5yl × 10zl
4. **Translate cube** → position at (cx-2.5xl, cy-2.5yl, cz-5zl)
5. **Boolean operation** → Cut (Partition fallback)
6. **Create face groups** → `far` + `<filename>_surface`
7. **Save as HDF**

### Key Functions

| Function | Description |
|----------|-------------|
| `geompy.ImportSTEP(path)` | Import STEP file |
| `geompy.BoundingBox(shape)` | Get (x_min, x_max, y_min, y_max, z_min, z_max) |
| `geompy.MakeBoxDXDYDZ(dx, dy, dz)` | Create box by dimensions |
| `geompy.MakeTranslation(obj, tx, ty, tz)` | Translate object |
| `geompy.MakeCut(main, tool)` | Boolean cut: main - tool |
| `geompy.MakePartition(objs, tools)` | Partition with tools |
| `geompy.addToStudy(obj, name)` | Add object to study tree |
| `salome.myStudy.SaveAs(path, ...)` | Save study to HDF |

---

## Domain Sizing

| Config | yl | Notes |
|--------|-----|-------|
| **Half-span** (default) | 0.5 × (y_max - y_min) | Aircraft symmetry |
| Full-span | y_max - y_min | No symmetry |

**Cube:** 10xl × 5yl × 10zl
**Translation:** (cx - 2.5xl, cy - 2.5yl, cz - 5zl)

---

## Notes

- **Batch mode**: All processing runs via `salome withsession -t` — no GUI needed
- **GUI for verification only**: Use `DISPLAY=:1 salome withsession -g study.hdf` after batch completes
- **STEP units**: Assumed to be meters (m)
- **Args format**: `<directory>:<step_file.stp>` or `<directory>:<filename>.json`
- Use `geompy.MakePartition` as fallback if `geompy.MakeCut` fails
