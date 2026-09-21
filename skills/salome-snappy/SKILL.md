---
name: salome-snappy
description: SALOME-based mesh generation for OpenFOAM snappyHexMesh (NOT snappyMesh). SALOME generates the volume mesh — no snappyHexMesh meshing (only addLayers). Use this for: STEP import → volume mesh → STL + snappyHexMeshDict setup. Triggers on: "SALOME mesh", "SALOME volume mesh", "mesh without snappyHexMesh meshing".
---

# Salome_with_snappyHexMesh Workflow

Two-step batch mesh generation for OpenFOAM's `snappyHexMesh`. No viscous layers in SALOME — layers are added later by snappyHexMesh. Auto-runs snappyHexMesh + checkMesh at the end of compute_mesh.py.

## /home/bosung/opt/salome/salome

## Batch Mode (Always)
```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```
**IMPORTANT:** Always use `-t -b` (terminal + batch) — no GUI, no server mode.

---

## Step 1: Calculate Parameters

```bash
cp ~/.openclaw/workspace/skills/salome-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Outputs:**
- `{filename}_geom.hdf` — Geometry study
- `{filename}_mesh_args.json` — Mesh parameters

**After Step 1:** Display all JSON values in the chat in a comprehensive table and ask the user to confirm before proceeding to Step 2.

⚠️ **REQUIRED: Show ALL parameters in the raise_table format, grouped by category:**
1. **Geometric Dimensions** (xl, yl, zl, cube_dx, cube_dy, cube_dz)
2. **Mesh Sizing** (min_size, surf_size, max_size, fineness)
3. **Boundary Layer** (h1, layers, growth, T, BASE_MINTHICKNESS)
4. **Refine Box** (refine_dx, refine_dy, refine_dz, refine_local_size, refine_cx/y/z, refine_tx/y/z)
5. **Mesh Statistics** (far_faces_count, model_faces_count)

Example format:

### 📊 All Mesh Parameters (Mesh Parameters)

#### 1. Geometric Dimensions
| Parameter | Value (m) | Description |
|-----------|-----------|-------------|
| xl | 0.34990 | Model Length |
| yl | 0.36183 | Model Width |
| zl | 0.18991 | Model Height |
| cube_dx | 3.49896 | Domain Length (xl × 10) |
| cube_dy | 1.80913 | Domain Width (yl × 5) |
| cube_dz | 1.89911 | Domain Height (zl × 10) |

#### 2. Mesh Sizing
| Parameter | Value (m) | Description |
|-----------|-----------|-------------|
| min_size | 0.00100 | Min mesh size (T) |
| surf_size | 0.01000 | Surface mesh size (10×T) |
| max_size | 0.06998 | Max mesh size (cube_dx/50) |
| fineness | 3 | Mesh density (2=mod/3=fine/4=vfine) |

#### 3. Boundary Layer (for snappyHexMesh)
| Parameter | Value (m) | Description |
|-----------|-----------|-------------|
| h1 | 0.00010 | First layer thickness |
| layers | 5 | BL count |
| growth | 1.3 | BL growth rate (snappyHexMesh) |
| T | 0.00100 | Total BL thickness |
| BASE_MINTHICKNESS | 0.00050 | Min layer thickness |

#### 4. Refine Box (Wake Capture)
| Parameter | Value (m) | Description |
|-----------|-----------|-------------|
| refine_dx | 1.74948 | X size (wake length) |
| refine_dy | 0.72365 | Y size (STEP yl × 2) |
| refine_dz | 0.37982 | Z size (STEP zl × 2) |
| refine_local_size | 0.02000 | Internal mesh size (surf_size × 2) |
| refine_cx | 0.44607 | Center X |
| refine_cy | 0.0 | Center Y |
| refine_cz | 0.01875 | Center Z |
| refine_tx | -0.42867 | Min corner X |
| refine_ty | -0.36183 | Min corner Y |
| refine_tz | -0.17116 | Min corner Z |

#### 5. Mesh Statistics
| Parameter | Value | Description |
|-----------|-------|-------------|
| far_faces_count | 6 | far_box face count |
| model_faces_count | 73 | STEP model face count |

All parameters displayed above. Confirm to proceed to Step 2.

---

## ⏱️ 실행 시간 가이드 (exec timeout)

SALOME 메쉬 + snappyHexMesh는 **수 분 ~ 수 시간** 소요. `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (Stage 1, 파라미터 계산) | `timeoutSeconds: 300` (STEP import 포함) |
| `compute_mesh.py` (Stage 2, meshing + snappyHexMesh) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지 (exec 기본 timeout ~2분 초과 시 SIGTERM)
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

---

## Step 2: Compute Mesh (Auto-runs snappyHexMesh + checkMesh)

```bash
cp ~/.openclaw/workspace/skills/salome-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

**Key Difference from Standard SALOME:** No `netgen.ViscousLayers()` configured.

**Outputs:**
- `{filename}_mesh_setup.hdf` — Mesh configuration
- `{filename}_mesh.hdf` — Computed mesh
- `{filename}-case/` — OpenFOAM case (snappyHexMesh ready)
  - `constant/polyMesh/` — Volume mesh
  - `constant/triSurface/{filename}_surface.stl` — Surface for snappyHexMesh
  - `system/snappyHexMeshDict` — Pre-configured
  - `system/controlDict` — Auto-fixed (writeInterval ≥ 1)
  - `addLayers.log` — snappyHexMesh output
  - `checkMesh.log` — checkMesh results

**Auto-execution:** compute_mesh.py automatically:
1. Copies template case to `{filename}-case/`
2. Modifies snappyHexMeshDict with parameters from JSON
3. Fixes controlDict writeInterval (must be ≥ 1)
4. Runs `snappyHexMesh -overwrite` and saves log
5. Runs `checkMesh` and prints key results
6. Prints key checkMesh metrics (cell quality, face quality, mesh statistics)

---

## snappyHexMeshDict Modifications

From JSON args → template case:
| Entry | Value |
|-------|-------|
| `firstLayerThickness` | `h1` |
| `expansionRatio` | `growth` |
| `nSurfaceLayers` | `layers` |
| geometry STL | `{filename}_surface.stl` |

---

## Mesh Parameters

| Parameter | Description | Default |
|-----------|---|---|
| h1 | First cell height (snappyHexMesh) | **0.0001** |
| layers | BL layer count (snappyHexMesh) | **10** |
| growth | BL growth rate (snappyHexMesh) | **1.3** |
| fineness | Netgen density (2=mod/3=fine/4=vfine) | **3** |
| **T** | Total BL thickness | derived |
| min_size | = T | T |
| surf_size | = 10×T | 10×T |
| max_size | = 10×xl/50 | derived |

---

## Refine Box (Wake Capture Volumetric Refinement)

Volumetric refinement of the wake region behind the STL object using **SALOME Netgen local size**. Same sizing rules as the `snappyMesh` skill, but implemented via SALOME's `SetLocalSizeOnShape()` instead of OpenFOAM's `refinementRegions`.

| Parameter | Formula | Description |
|------|------|------|
| **refine_dx** | `0.5 × far_box_dx` | Streamwise X size (wake length) |
| **refine_dy** | `2 × STEP_yl` | Spanwise Y size (STEP yl, NOT STL) |
| **refine_dz** | `2 × STEP_zl` | Vertical Z size (STEP zl, NOT STL) |
| **Center** | `= far_box_center` | Same center as far box domain |
| **Min corner** | `center - size/2` | SALOME cube min corner for translation |
| **Local size** | `surf_size × N` (N is JSON override, default 2) | Cell size inside refineBox (Netgen) |
| **Mode** | — | Refines ALL cells inside the box |
| **Multiplier override** | JSON `refine_local_multiplier` | Set to change multiplier (e.g., 8 for 0.04m) |
| **Size override** | JSON `refineBox_cell_size_override` | Direct override of local cell size |

### SALOME Implementation Steps

1. **Size calculation** (`calculate_mesh_params.py`):
   - `refine_dx = 0.5 × cube_dx` (cube_dx = far_box_dx = 10xl)
   - `refine_dy = 2 × STEP yl` (uses STEP dimensions, not STL)
   - `refine_dz = 2 × STEP zl` (uses STEP dimensions, not STL)
   - `refine_cx,y,z = far_box_center`
   - `refine_tx,y,z = center - size/2` (min corner)
   - JSON keys: `refine_dx`, `refine_dy`, `refine_dz`, `refine_cx/y/z`, `refine_tx/y/z`

2. **Create cube in SALOME** (`compute_mesh.py`):
   - `geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)` → always at (0,0,0)
   - `geompy.MakeTranslation(refined_box, refine_tx, refine_ty, refine_tz)` → move to correct position

3. **Volume Group**:
   - `geompy.CreateGroup(refined_box, ShapeType.SOLID)`
   - `geompy.UnionList(group, solids)` → add all solids inside

4. **Netgen Local Size**:
   - `netgen.SetLocalSizeOnShape(refine_box_volume_group, surf_size × 2)`
   - Cells inside refineBox get uniform cell size = `surf_size × 2`

### Why STEP yl/zl (not STL)?

The refine box Y/Z sizing is based on **STEP file bounding box** dimensions, not STL. This ensures consistent wake capture region sizing regardless of any STL tessellation artifacts or partial geometry exports.

### Tuning

- For bluff body drag prediction: increase `refine_dx` toward `0.85 × far_box_dx`
- For streamlined bodies: default is sufficient
- Increase `refine_level` equivalent by adjusting local size multiplier (default 2×)

---

## Parallel snappyHexMesh

compute_mesh.py runs snappyHexMesh in parallel using:
1. **Physical cores only** — `lscpu`에서 `Core(s) per socket × Socket(s)` 계산 (HyperThreading 제외)
2. **numberOfSubdomains** — decomposeParDict에서 `numberOfSubdomains` 사용 (OpenFOAM v2512)
3. **--oversubscribe** — mpirun에 `--oversubscribe` 옵션 필수 (hyperthreading 시스템에서도 에러 방지)

### decomposeParDict Key
```foam
numberOfSubdomains   <num_physical_cores>;
```
⚠️ **OpenFOAM v2512에서는 `nSubdomains`가 아닌 `numberOfSubdomains`를 사용해야 합니다.**

---

## Template Fixes

### snappyHexMeshDict maxGlobalCells
- Template `maxGlobalCells`는 **100,000,000**으로 설정 (대용량 메쉬 대응)

### 0/p, 0/U boundaryField
- Template `0/p`과 `0/U`는 `defaultFaces` patch만 포함
- compute_mesh.py가 polyMesh/boundary 기반으로 patch별 boundaryField를 자동 생성
- boundaryField 중첩 `{ }` 중복 에러 방지: 한 번만 적용

---

## Known Issues / Fixes

### controlDict writeInterval Error
Template `controlDict` has `writeInterval 0` which causes `FOAM FATAL IO ERROR`. compute_mesh.py now auto-fixes this:
```python
cd_content = cd_content.replace("writeControl    timeStep;", "writeControl    adjustableRunTime;")
cd_content = cd_content.replace("writeInterval   0;", "writeInterval   1;")
```

### Template Path
Script uses hardcoded path: `/home/bosung/.openclaw/workspace/skills/salome-snappy/assets/snappyHexMesh-case-template`

---

## ⚠️ mpirun 실행 방식 수정 (2026-09-09)

**문제:** `mpirun ... 2>&1 | tee log.snappyHexMesh` — pipe buffer(64KB)가 가득 차면 mpirun이 write blocked → hang → gateway SIGKILL

**수정 전:**
```bash
mpirun -np N snappyHexMesh -parallel 2>&1 | tee log.snappyHexMesh
```

**수정 후:**
```bash
mpirun -np N --oversubscribe snappyHexMesh -parallel > log.snappyHexMesh 2>&1
```

**원인:** `os.system()` + `tee` 파이프에서 Python이 pipe buffer를 읽지 않아 쌓임 → write blocked → hang → SIGKILL
**해결:** `tee` 파이프 제거, 파일에 직접 redirect → pipe 없음, buffer 축적 없음
**수정 파일:** `compute_mesh.py` (mpirun 호출 부분)
