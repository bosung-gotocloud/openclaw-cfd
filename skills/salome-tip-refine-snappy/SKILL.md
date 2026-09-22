---
name: salome-tip-refine-snappy
description: SALOME-based mesh generation for snappyHexMesh with tip-wake line refinement. STEP import → Netgen mesh → snappyHexMesh case. Auto-discovers tip_points CSV for wake line refinement.
---

# salome-tip-refine-snappy Skill

SALOME-based two-step batch mesh generation for OpenFOAM's `snappyHexMesh`. Adds **tip-wake line refinement** on top of the original `salome-snappy` workflow - auto-discovers `{basename}_tip_points.csv` and generates X-direction wake lines from each tip point to the refine box xmax. Falls back to original refine-box-only mode if no tip CSV found.

**Last confirmed:** 2026-09-21 (BL-based sizing: surf_size=4*T, min_size=2*T, max_size=max(cube_dim)/50, refine_local_size=max_size/4, tip_wake_refine_size=2*surf_size; **addLayers: firstAndRelativeFinal, finalLayerThickness=0.5 (50% of local surface cell size), growth=1.3 is sizing-only not used by snappyHexMesh layer calc**; SetFineness commented; max_size syntax fixed)
**Location:** `~/.openclaw/workspace/skills/salome-tip-refine-snappy/`
**SALOME path:** `/home/bosung/opt/salome/salome`

---

## ⚠️ Critical: Surface Curvature Must Be Enabled

**2026-07-06 discovery:** `SetUseSurfaceCurvature(1)` (Limit size surface curvature) **MUST be enabled** for stable STEP mesh computation. When disabled, mesh computation may fail or hang indefinitely on complex STEP files.

---

## Batch Mode

```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```

**Always use `-t -b`** (terminal + batch) - no GUI, no server mode.

---

## Workflow Overview

```
STEP File + optional tip_points CSV
    │
    ▼
calculate_mesh_params.py   (Stage 1)
    ├─ STEP import + bbox
    ├─ Far-field box + tool solid
    ├─ **Refine box size calculation**
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ **Wake lines generated (before boolean cut, after refine box size, after surf_size)**
    ├─ Boolean Cut/Partition
    ├─ Face classification (far vs model)
    ├─ Calculate mesh params (h1, T, surf_size, etc.)
    ├─ Save {basename}_mesh_args.json
    └─ Save {basename}_geom.hdf
    │
    ▼  (user reviews & confirms)
    │
compute_mesh.py            (Stage 2)
    ├─ Rebuild geometry fresh from STEP
    ├─ **refineBox + volume group** (SetLocalSizeOnShape on shape) — refine_box_volume_group via UnionList
    ├─ Create wake lines BEFORE boolean cut (so they extend through domain boundary)
    ├─ **min_size auto-correction**: STEP에서 가장 작은 face edge length을 계산. `min_size > smallest_edge` 면 `args['min_size'] = smallest_edge`로 조정
    ├─ **refineBox local size only** (SetLocalSizeOnShape on shape)
    ├─ **Wake lines local size only** (SetLocalSizeOnShape on shape)
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
cp ~/.openclaw/workspace/skills/salome-tip-refine-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Auto-Discovery:** If `{basename}_tip_points.csv` exists in the same directory as the STEP file, it is automatically loaded. CSV format: `x,y,z` header + data rows. If no CSV found, workflow continues in refine-box-only mode (same as original salome-snappy).

**Outputs:**
- `{filename}_geom.hdf` - Geometry study
- `{filename}_mesh_args.json` - Mesh parameters (includes tip fields if CSV found)

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
  "layers": 10,
  "growth": 1.3,
  "fineness": "Custom",
  "T": 0.004262,
  "min_size": 0.008524,
  "surf_size": 0.017048,
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
  "tip_wake_refine_size": 0.034096
}
```

**Tip fields** (`tip_csv_path`, `tip_points_count`, `tip_wake_lines`, `tip_wake_refine_size`) are only populated when a tip CSV is found. All other fields work identically to the original salome-snappy skill.

## ⏱️ 실행 시간 가이드 (exec timeout)

SALOME Netgen 메쉬 + snappyHexMesh addLayers는 **수 분 ~ 수 시간** 소요. `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (Stage 1, 파라미터 계산) | `timeoutSeconds: 300` (STEP import 포함) |
| `compute_mesh.py` (Stage 2, meshing + addLayers) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지 (exec 기본 timeout ~2분 초과 시 SIGTERM)
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

### ⚠️ Golden Rule - Never recalculate parameters

**절대 유도 파라미터를 재계산하지 않습니다.**

1. `calculate_mesh_params.py` 실행 → 파라미터 표 표시 → 승인 받음
2. 승인 후 수정 요청 시 → **수정할 파라미터만 JSON에서 직접 수정**
3. 관련 유도 파라미터(예: `surf_size` 변경 시 `refine_local_size` 등) 재계산 **절대 금지**
4. 재계산이 필요하다면 → **사용자에게 명시적으로 "step1부터 새로 합니다"라고告知**
5. 실행 전 절대 JSON을 수정하거나 실행하지 않음

---

## Step 2: Compute Mesh (Auto-runs snappyHexMesh + checkMesh)

```bash
cp ~/.openclaw/workspace/skills/salome-tip-refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

### Key Features

1. **Geometry rebuild from STEP** - fresh import, no dependency on geom.hdf
2. **Tip-wake lines** - if tip CSV found, creates wake lines from each tip → refine_box_xmax (X-direction)
3. **Netgen local size** - refineBox volume + wake lines get different cell sizes
4. **NO viscous layers** - layers added later by snappyHexMesh
5. **Critical:** `SetUseSurfaceCurvature(1)` enabled for stable computation

### Mesh Setup Details (compute_mesh.py — 2026-09-03 기준)

```python
mesh = smesh.Mesh(domain, f"{base_name}_mesh")
netgen = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)

params = netgen.Parameters()
params.SetNbThreads(8)
params.SetMaxSize(max_size)
params.SetMinSize(min_size)
params.SetLocalSizeOnShape(group_model, surf_size)
params.SetUseSurfaceCurvature(1)   # ← CRITICAL: must be 1
# params.SetFineness(fineness)  # ← 주석 처리됨 (2026-09-03 이전 버전부터 비활성화)
# Custom mesh quality params (active):
params.SetGrowthRate(0.3)            # custom growth rate
params.SetNbSegPerEdge(1)            # segments per edge
params.SetNbSegPerRadius(3)          # segments per radius
params.SetOptimize(1)                  # 3D tet optimization (ENABLED)
# params.SetSecondOrder(0)             # Linear elements only
# NO volume group for refineBox - local size applied directly on shape
# refineBox local size
netgen.SetLocalSizeOnShape(refine_box_volume_group, refine_local_size)
# wake lines local size (if tip CSV found)
if wake_line_objects:
    for wake_line in wake_line_objects:
        netgen.SetLocalSizeOnShape(wake_line, tip_wake_refine_size)
```

### Output

- `{filename}_mesh_setup.hdf` - Mesh setup (for manual tuning in SALOME GUI)
- `{filename}_mesh.hdf` - Computed mesh
- `{filename}-case/` - OpenFOAM case:
  - `constant/polyMesh/` - Volume mesh (points, faces, owner, neighbour, boundary, cellZones)
  - `constant/triSurface/{filename}_surface.stl` - Surface for snappyHexMesh layers
  - `system/snappyHexMeshDict` - Pre-configured with BL params
  - `system/controlDict` - Auto-fixed (writeInterval ≥ 1)
  - `log.snappyHexMesh` - snappyHexMesh output
  - `log.reconstructParMesh` - reconstruction log
  - `checkMesh.log` - checkMesh results

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
| **tip_wake_refine_size** | **= surf_size × 2** (= 8T) | Wake line local cell size (8T) |
| **Line origin** | Tip point (x, y, z) | From CSV |
| **Line end** | `refine_box_xmax` | X-direction only |
| **Count** | Matches CSV row count | One line per tip point |

Wake lines extend from each tip point to the refine box xmax in the X direction. Cells along wake lines get `tip_wake_refine_size` (= surf_size × 2), intersecting with refine box cells gets `refine_local_size` (coarser). The smaller value wins in the intersection zone.---

## Mesh Sizing Logic (BL-based)

**BL 기반 sizing: 경계층 두께 T에서 유도.**

```
Step 1: max_size   = max(cube_dx, cube_dy, cube_dz) / 50.0           (배경 메쉬의 가장 큰 셀)
Step 2: surf_size  = 4 × T            (표면 cell size = 4 × BL thickness)
Step 3: min_size   = 2 × T            (최소 cell size = 2 × BL thickness)
Step 4: refine_size = max_size / 4    (refine box local size)
Step 5: tip_wake_refine_size = surf_size × 2  (tip wake line local size)
```

> `T` (BL total thickness)는 `h1 × (growth^n-1)/(growth-1)`
> `T`는 **sizing에 직접 사용** — `surf_size = 4T`, `min_size = 2T`

### ⚠️ Golden Rule — Never Recalculate Derived Params

Stage 1 (`calculate_mesh_params.py`) computes `T`, `surf_size`, `min_size`, `refine_local_size` and stores them in `{basename}_mesh_args.json`. Stage 2 (`compute_mesh.py`) **reads** these values and never recomputes them. If a parameter must change, the user must re-run Stage 1 — do not edit the JSON or re-derive in Stage 2.

### ⚠️ addLayers: `firstAndRelativeFinal` Mode (2026-09-21)

**Problem:** With `thicknessModel firstAndExpansion` (fixed `nLayers` + `expansionRatio`), coarse surface cells (e.g. surf_size ≈ 17 mm on a large body) cause snappyHexMesh to abort or skip layer creation entirely.

**Fix:** Use `thicknessModel firstAndRelativeFinal`. The final layer thickness is defined as a **fraction of the local surface cell size**, so it scales with each cell automatically:

```
firstLayerThickness  = h1              (absolute, m — from JSON)
finalLayerThickness  = 0.5             (= 50% of local surface cell size, per cell)
nSurfaceLayers       = layers          (from JSON, e.g. 10)
```

**Note:** `growth` (1.3) is still used for `T` → `surf_size` / `min_size` sizing in Stage 1. It is **not** read by snappyHexMesh in `firstAndRelativeFinal` mode. Do not remove `growth` from the JSON.

**Template placeholders** (`compute_mesh.py` replaces these):
- `BASE_FIRSTLAYER` → `f"{h1:.8f}"`
- `BASE_NLAYERS` → `str(layers)`
- `finalLayerThickness 0.5` is fixed in the template (no placeholder)


### Mesh Parameters

| Parameter | Description | Formula |
|------|------|------|
| h1 | First cell height (snappyHexMesh) | 0.0001 m |
| layers | BL layer count (snappyHexMesh) | **10** |
| growth | BL growth rate (snappyHexMesh) | **1.3** |
| fineness | Netgen density (Custom mesh quality) | **"Custom"** |
| T | Total BL thickness | `h1×(growth^n-1)/(growth-1)` |
| min_size | Minimum mesh size | **= 2×T** |
| surf_size | Surface mesh size | **= 4×T** |
| max_size | Max mesh size | = **max(cube_dx, cube_dy, cube_dz) / 50.0** |
| refine_local_size | Refine box local size | = max_size / 4 |
| tip_wake_refine_size | Wake line local size | **= surf_size × 2** |

---

## Parallel snappyHexMesh

compute_mesh.py runs snappyHexMesh in parallel using:
1. **Physical cores only** - `lscpu` → `Core(s) per socket × Socket(s)` (HyperThreading excluded)
2. numberOfSubdomains uses physical core count
3. **--oversubscribe** - mandatory in mpirun for hyperthreading systems

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

## OpenFOAM 환경변수 로딩

SALOME Python 내에서 OpenFOAM 명령어(decomposePar, snappyHexMesh, checkMesh 등) 호출 시:

### 필수 실행 방식 (compute_mesh.py 기준)

\`\`\`bash
bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc 2>/dev/null && cd {case_dir} && snappyHexMesh -parallel 2>&1 | tee log.snappyHexMesh'
\`\`\`

**절대 `subprocess.run(["snappyHexMesh"])` 형식으로 직접 호출하지 마세요.** 반드시 `bash -c 'source bashrc ...'\`로 감싸서 실행하세요. SALOME 9.15 이후 Python 환경이 bashrc를 자동으로 로드하지 않습니다.

---

## Monitoring Rules (2026-07-08)

### Monitoring Behavior

**compute_mesh.py 실행 후 — 사용자가 모니터링 요청 전까지 절대 확인하지 않음.**

1. `compute_mesh.py` 실행 → 즉시 "실행 중" 보고 + "완료되면 알려드립니다" 회신
2. **사용자가 모니터링을 요청하기 전까지** 로그 확인, 상태 확인, checkMesh 확인 절대 하지 않음
3. 사용자가 모니터링 요청 시: `log.snappyHexMesh`에서 `Running checkMesh...` 라인 확인 → 있으면 완료
4. 완료 시 `{basename}-case/checkMesh.log` 내용 프린트
5. checkMesh.log가 비어 있으면 수동 `checkMesh` 실행 → 결과 확인

### 최종 스크립트 (확정)

```bash
# Stage 1: Parameters
cp ~/.openclaw/workspace/skills/salome-tip-refine-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>

# Stage 2: Mesh (자동 실행 — 모니터링 안 함)
cp ~/.openclaw/workspace/skills/salome-tip-refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json

# Monitoring (사용자 요청 시만)
tail -30 <directory>/log.snappyHexMesh  # Running checkMesh 확인
# 완료 시:
cat <directory>/<basename>-case/checkMesh.log
# 비어 있으면 수동 실행:
source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd <directory>/<basename>-case && checkMesh 2>&1 | tee checkMesh.log
```

---

## Comparison: salome-tip_refine-snappy vs salome-snappy

| Feature | salome-snappy | salome-tip_refine-snappy |
|---------|---------------|--------------------------|
| Tip CSV auto-discovery | ✗ | ✓ |
| Wake line refinement | ✗ | ✓ (X-direction from tips) |
| `tip_wake_refine_size` | ✗ | = **surf_size × 2** (= 8T) |
| Mesh sizing logic | T-based (old) | **xl-based** (unified) |
| **addLayersControls** | template 기반 | **firstAndRelativeFinal, nSurfaceLayers=10, finalLayerThickness=0.5 (50% of local surface cell), firstLayerThickness=h1, maxFaceThicknessRatio=100.0, minFaceWeight=-1, minVolRatio=-1, nBufferCellsNoExtrude=3** |
| **meshQualityControls** | template 기반 | **maxNonOrtho=65, maxBoundarySkewness=20** |
| Backwards compat | - | Fallback to refine-box-only |
| `SetUseSurfaceCurvature` | 1 | 1 (both) |

---

## Skill Backup

- `skills/backups/2026-07-25/salome-tip-refine-snappy/` - Final confirmed version (2026-07-25)

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

## 경계층 (addLayers) 안정화 설정 — 2026-09-22

`snappyMesh-elliptic-tip-refine`과 동일하게 경계층이 잘 쌓이도록
`assets/.../snappyHexMeshDict` template을 동기화함 (backup: `snappyHexMeshDict.bak-20260922`).

### castellatedMeshControls
- `nCellsBetweenLevels 3 -> 5` — 급격한 배경 격자 해상도 변화로 인한 Layer Collapse 방지

### addLayersControls
- ⚠️ `thicknessModel firstAndRelativeFinal` + `finalLayerThickness 0.5` 구조 유지 (박사님 지정)
- `maxThicknessToMedialRatio 5.0 -> 100.0` (LE/곡면 국소 미세 셀 영역 두께 제약 해제)
- `maxFaceThicknessRatio 100.0 -> 1000.0` (배경 격자 크기 대비 두께 제약 대폭 완화)
- `nBufferCellsNoExtrude 3 -> 0` (실패 지점 인접 셀 동반 삭제 방지)
- 스무딩/완화: `featureAngle 75 -> 180`, `nRelaxIter 10 -> 50`, `nSmoothSurfaceNormals 1 -> 5`,
  `nSmoothThickness 10 -> 20`, `nSmoothNormals 3 -> 5`, `nMedialAxisIter 20 -> 50`,
  `nLayerIter 50 -> 200`, `nRelaxedIter 20 -> 50`
- relaxed: `maxNonOrtho 90 -> 95`, `minFaceWeight/minVolRatio 0.005 -> 0.0001`

### meshQualityControls
- `maxNonOrtho 80 -> 85`, `maxInternalSkewness 4 -> 20`, `minVol 1e-13 -> 1e-15`
- `minDeterminant 0.001 -> 1e-5`, `minTwist 0.02 -> -1`
- `minFaceWeight 0.05 -> 0.0001`, `minVolRatio 0.01 -> 0.0001` (핵심)
- `minTetQuality 1e-9 -> 1e-15`, relaxed `maxNonOrtho 85 -> 95`
