---
name: salome-tip_refine-snappy
description: SALOME-based mesh generation for snappyHexMesh with tip-wake line refinement. STEP import → Netgen mesh → snappyHexMesh case. Auto-discovers tip_points CSV for wake line refinement.
---

# salome-tip_refine-snappy Skill

SALOME-based two-step batch mesh generation for OpenFOAM's `snappyHexMesh`. Adds **tip-wake line refinement** on top of the original `salome-snappy` workflow - auto-discovers `{basename}_tip_points.csv` and generates X-direction wake lines from each tip point to the refine box xmax. Falls back to original refine-box-only mode if no tip CSV found.

**Last confirmed:** 2026-07-25 (BL-based sizing: surf_size=4*T, min_size=2*T, tip_wake_refine_size=2*s surf_size)
**Location:** `~/.openclaw/workspace/skills/salome-tip_refine-snappy/`
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
    ├─ **refineBox = shape only (no volume group)**
    ├─ Create wake lines (if tips found)
    ├─ **Wake line domain clipping**: `geompy.MakeCut(wake_line, domain)` 으로 domain 밖으로 뚫고 나가는 부분 clip
    ├─ **min_size auto-correction**: STEP에서 가장 작은 face bbox diagonal을 계산. `min_size > smallest_face_diag` 면 `args['min_size'] = smallest_face_diag`로 조정
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
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/calculate_mesh_params.py <directory>/
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
  "layers": 5,
  "growth": 1.3524,
  "fineness": 2,
  "T": 0.001220,
  "min_size": 0.001220,
  "surf_size": 0.021090,
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
  "tip_wake_refine_size": 0.021090
}
```

**Tip fields** (`tip_csv_path`, `tip_points_count`, `tip_wake_lines`, `tip_wake_refine_size`) are only populated when a tip CSV is found. All other fields work identically to the original salome-snappy skill.

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
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

### Key Features

1. **Geometry rebuild from STEP** - fresh import, no dependency on geom.hdf
2. **Tip-wake lines** - if tip CSV found, creates wake lines from each tip → refine_box_xmax (X-direction)
3. **Netgen local size** - refineBox volume + wake lines get different cell sizes
4. **NO viscous layers** - layers added later by snappyHexMesh
5. **Critical:** `SetUseSurfaceCurvature(1)` enabled for stable computation

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
# Custom mesh quality params (disabled - use fineness only):
# params.SetNbSurfOptSteps(3)
# params.SetNbVolOptSteps(3)
params.SetOptimize(1)                  # 3D tet optimization (ENABLED)
# params.SetSecondOrder(0)
# params.SetGrowthRate(1.3)
# NO volume group for refineBox - local size applied directly on shape
# refineBox local size
netgen.SetLocalSizeOnShape(refined_refine_box, refine_local_size)
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
| **tip_wake_refine_size** | **= surf_size × 2** (= 4T × 2 = 8T) | Wake line local cell size |
| **Line origin** | Tip point (x, y, z) | From CSV |
| **Line end** | `refine_box_xmax` | X-direction only |
| **Count** | Matches CSV row count | One line per tip point |

Wake lines extend from each tip point to the refine box xmax in the X direction. Cells along wake lines get `tip_wake_refine_size` (= surf_size), intersecting with refine box cells gets `refine_local_size` (coarser). The smaller value wins in the intersection zone.---

## Mesh Sizing Logic (BL-based)

**BL 기반 sizing: 경계층 두께 T에서 유도.**

```
Step 1: max_size   = xl / 5           (배경 메쉬의 가장 큰 셀)
Step 2: surf_size  = 4 × T            (표면 cell size = 4 × BL thickness)
Step 3: min_size   = 2 × T            (최소 cell size = 2 × BL thickness)
Step 4: refine_size = max_size / 4    (refine box local size)
Step 5: tip_wake_refine_size = surf_size × 2  (tip wake line local size)
```

> `T` (BL total thickness)는 `h1 × (growth^n-1)/(growth-1)`
> `T`는 **sizing에 직접 사용** — `surf_size = 4T`, `min_size = 2T`

### Mesh Parameters

| Parameter | Description | Formula |
|------|------|------|
| h1 | First cell height (snappyHexMesh) | 0.0001 m |
| layers | BL layer count (snappyHexMesh) | **10** |
| growth | BL growth rate (snappyHexMesh) | **1.2** |
| fineness | Netgen density (2=mod/3=fine/4=vfine) | **2** |
| T | Total BL thickness | `h1×(growth^n-1)/(growth-1)` |
| min_size | Minimum mesh size | **= 2×T** |
| surf_size | Surface mesh size | **= 4×T** |
| max_size | Max mesh size | = **xl / 5** |
| refine_local_size | Refine box local size | = max_size / 4 |
| tip_wake_refine_size | Wake line local size | **= surf_size × 2** |

---

## Parallel snappyHexMesh

compute_mesh.py runs snappyHexMesh in parallel using:
1. **Physical cores only** - `lscpu` → `Core(s) per socket × Socket(s)` (HyperThreading excluded)
2. **numberOfSubdomains** - `decomposeParDict` uses `numberOfSubdomains` (OpenFOAM v2512)
3. **--oversubscribe** - mandatory in `mpirun` for hyperthreading systems

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
| **Mesh compute silently fails / returns False** | **Remove `SetSizeLimit(0)` — SALOME 9.15 removed this method** |
| **Netgen surface mesh: "GIVING UP"** | **Normal message — Netgen surface meshing exceeded limit, volume meshing continues. Safe to ignore.** |
| **exportToFoam `c_xmin` not defined error** | **Replace bbox-based far face detection with group name-based detection (from salome-tip_refine) — 2026-07-13** |
| **checkMesh.log 비어 있음** | **`subprocess.run` → `os.system` + `source bashrc` + `tee`로 변경 — 2026-07-13** |
| **NETGEN quality options** | **fineness only + SetOptimize(1)** — custom params disabled — 2026-07-25 |
| **sizing unified** | **layers=10, growth=1.2, min_size=surf_size/2, tip_wake_refine_size=refine_local_size/2** — salome-tip_refine와 동일 — 2026-07-24 |
| **Wake lines position** | **After boolean cut** (same as salome-tip_refine) — 2026-07-24 |

---

## Backwards Compatibility

- If no `{basename}_tip_points.csv` exists → workflow proceeds exactly like original `salome-snappy`
- No tip-related JSON fields added if CSV not found
- `tip_wake_lines` check prevents errors in compute_mesh.py
- `skills/salome-snappy/` - **NOT MODIFIED**

---

## Workflow Rules

- **calculate_mesh_params.py 실행 후 반드시 모든 파라미터를 표로 보여주고 승인 받을 것**
- **사용자 승인 전에 compute_mesh.py 절대 실행 금지**
- 파라미터 계산 → 확인 → 승인 → 실행 (절대 순서 위반 금지)
- **Golden Rule:** JSON 직접 편집, 스크립트 수정 아님

---

## Comparison: salome-tip_refine-snappy vs salome-snappy

| Feature | salome-snappy | salome-tip_refine-snappy |
|---------|---------------|--------------------------|
| Tip CSV auto-discovery | ✗ | ✓ |
| Wake line refinement | ✗ | ✓ (X-direction from tips) |
| `tip_wake_refine_size` | ✗ | = **surf_size × 2** (= 8T) |
| Mesh sizing logic | T-based (old) | **xl-based** (unified) |
| **addLayersControls** | template 기반 | **firstAndExpansion, nLayers=5, expansionRatio=1.3524, maxFaceThicknessRatio=5.0, minFaceWeight=-1, minVolRatio=-1, nBufferCellsNoExtrude=3** |
| **meshQualityControls** | template 기반 | **maxNonOrtho=65, maxBoundarySkewness=20, relaxed.maxNonOrtho=75** |
| Backwards compat | - | Fallback to refine-box-only |
| `SetUseSurfaceCurvature` | 1 | 1 (both) |
| `SetSizeLimit` | ✗ | Removed (SALOME 9.15 incompatible) |
| Original file | Unchanged | Unchanged |

---

## Skill Backup

- `skills/backups/2026-07-25/salome-tip_refine-snappy/` - Final confirmed version (2026-07-25)

## Update Log

### **2026-07-25 - 최종 확정**

**sizing 로직 BL 기반 확정:**
- `h1=0.0001, layers=10, growth=1.2` (snappyHexMesh BL params)
- `T = h1 × (growth^10 - 1) / 0.2` (BL total thickness)
- `surf_size = 4 × T` (surface cell size)
- `min_size = 2 × T` (minimum cell size)
- `tip_wake_refine_size = surf_size × 2`

**Mesh Quality 확정:**
- **fineness** 파라미터로 mesh density 제어 (`SetFineness(2)` = mod)
- **SetOptimize(1)** — ENABLED
- custom params (`SetNbSurfOptSteps`, `SetNbVolOptSteps`, `SetSecondOrder`, `SetGrowthRate`) — 비활성화

**Workflow 확정:**
- `wake lines` → after boolean cut (same as salome-tip_refine)
- `mesh compute` → no timeout (unified with salome-tip_refine)
- `ViscousLayers` → DISABLED (snappyHexMesh handles BL)

---

### **2026-07-19 - addLayersControls Parameter Fixes**

**Template fix:** `snappyHexMeshDict`의 `addLayersControls`에 4개 파라미터 추가/수정 (snappyMesh-tip_refine template과 동기화):

| 파라미터 | 변경 전 | 변경 후 |
|------|------|------|
| `maxFaceThicknessRatio` | 0.5 | **5.0** |
| `minFaceWeight` (top-level) | ❌ 없음 | **-1** |
| `minVolRatio` (top-level) | ❌ 없음 | **-1** |
| `nBufferCellsNoExtrude` | ❌ 없음 | **3** |

**template path:** `assets/snappyHexMesh-case-template/system/snappyHexMeshDict`

**compute_mesh.py** — 스크립트 수정 없음 (template에서 값 관리)

**검증:** LC62-50B case에서 addLayersControls, meshQualityControls, snapControls를 snappyMesh-tip_refine template과 비교 — values 모두 동일 확인.

**compute_mesh.py 두 가지 수정:**

1. **exportToFoam — c_xmin 미정의 에러 해결**
   - bbox 기반 far face 분류(`c_xmin` 전역 변수 의존) 제거
   - salome-tip_refine의 group name 기반 분류로 교체 (`grpNames`, `grpStartFace`, `grpNrFaces`)
   - boundary patch: `"wall"` if "surface" in name else `"patch"` (group name 기준)

2. **checkMesh 실행 방식 변경**
   - `subprocess.run(["checkMesh"])` → `os.system` + `source bashrc` + `tee`
   - checkMesh.log가 더 이상 비어있지 않음
   - case.foam marker 생성은 정상 (기존과 동일)

**이전 백업:** `skills/backups/2026-07-04/salome-tip_refine-snappy/`

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
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>

# Stage 2: Mesh (자동 실행 — 모니터링 안 함)
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json

# Monitoring (사용자 요청 시만)
tail -30 <directory>/log.snappyHexMesh  # Running checkMesh 확인
# 완료 시:
cat <directory>/<basename>-case/checkMesh.log
# 비어 있으면 수동 실행:
source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd <directory>/<basename>-case && checkMesh 2>&1 | tee checkMesh.log
```
