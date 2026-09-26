---
name: salome-tip-shock-refine
description: SALOME Netgen-based mesh generation with shock-wave point-based local sizing and tip-wake line refinement. STEP import → Netgen mesh → OpenFOAM case. No snappyHexMesh.
---

# salome-tip-shock-refine Skill

SALOME Netgen 기반 **충격파(Shock) 포인트 로컬 사이즈 정밀화**와 팁(Tip) 와이크 라인 리파인먼트를 추가한 OpenFOAM 메쉬 생성 스킬입니다.

**기존 `salome-tip_refine`에 다음 기능 추가:**
- **충격파 CSV 자동 탐색 및 적용**: `*shock*.csv` 패턴으로 포인트 기반 local cell size 적용
- **shock_refine_size = surf_size × 2** (tip-wake와 동일한 정밀화 레벨)

---

## ⚠️ Critical Notes

### Surface Curvature Must Be Enabled
`SetUseSurfaceCurvature(1)` **MUST be enabled** for stable STEP mesh computation.

### Viscous Layers in SALOME
Viscous layers are configured **inside** `compute_mesh.py` via `netgen.ViscousLayers(T, layers, growth, far_faces, 1, smeshBuilder.FACE_OFFSET) — 1st arg is total BL thickness T = h1×(growth^layers-1)/(growth-1), not first-layer height`.
No separate snappyHexMesh layer config needed.

### min_size Auto-Correction
**compute_mesh.py** — min_size auto-correction 로직 내장:
- STEP 파일에서 가장 작은 face edge length 계산
- `min_size > smallest_edge` 면 `args['min_size'] = smallest_edge`로 자동 조정
- **이유**: Netgen은 min_size보다 작은 face를 meshing할 수 없음

---

## Batch Mode

```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```

**Always use `-t -b`** (terminal + batch) - no GUI, no server mode.

---

## Workflow Overview

```
STEP File + optional tip_points CSV + optional shock CSV
    │
    ▼
calculate_mesh_params.py   (Stage 1)
    ├─ STEP import + bbox
    ├─ Far-field box + tool solid
    ├─ Refine box size calculation
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ **Auto-discover *shock*.csv** ← NEW
    ├─ Wake lines generated (after boolean cut)
    ├─ **Shock points local sizing** ← NEW
    ├─ Boolean Cut/Partition
    ├─ Face classification (far vs model)
    ├─ Calculate mesh params
    ├─ Save {basename}_mesh_args.json (includes shock fields if CSV found)
    └─ Save {basename}_geom.hdf
    │
    ▼  (user reviews & confirms)
    │
compute_mesh.py            (Stage 2)
    ├─ Rebuild geometry fresh from STEP
    ├─ refineBox (shape only)
    ├─ Create wake lines (if tips found)
    ├─ **Shock point → vertex creation** ← NEW (after wake line)
    ├─ **Apply local size to shock vertices** ← NEW
    ├─ **min_size auto-correction** ← NEW
    ├─ Netgen mesh: SetUseSurfaceCurvature(1)
    ├─ **ViscousLayers(T, layers=10, growth=1.3)** — BOUNDARY LAYERS (1st arg = total BL thickness)
    ├─ Mesh compute (no timeout)
    ├─ **exportToFoam: generates complete case structure**
    │   ├─ constant/polyMesh/  (points, faces, owner, neighbour, boundary, cellZones)
    │   ├─ 0/                  (p, U)
    │   ├─ system/             (controlDict, fvSchemes, fvSolution)
    │   └─ case.foam marker
    └─ Save mesh HDF + auto checkMesh
```

---

## Mesh Sizing Logic (BL-based + Shock)

**BL 기반 sizing: 경계층 두께 T에서 유도.**

### 계산 단계

```
Step 1: max_size       = max(cube_dx,cube_dy,cube_dz)/50   (far-field coarsest cell)
Step 2: surf_size      = 4 × T            (surface cell size)
Step 3: min_size       = 2 × T            (minimum cell size)
Step 4: refine_size    = max_size / 4     (refine box local size)
Step 5: tip_wake_refine_size = surf_size × 2      (tip wake line local size)
Step 6: **shock_refine_size = surf_size × 2**            (shock point local size) ← NEW

경계층 (Boundary Layer):
h1 = 0.0001  (first cell height, m)
growth = 1.3   (growth rate)
layers = 10    (boundary layer count)

T = h1 × (growth^layers - 1) / (growth - 1)  (total BL thickness)
```

---

## Shock CSV 포맷

충격파 위치를 정의하는 CSV 파일입니다. **자동 탐색 패턴:** `*shock*.csv`

```csv
cellID,x,y,z,SI,h
1,0.5,0.0,0.0,1.0,0.001
2,0.6,0.0,0.0,1.0,0.001
...
```

- **x, y, z**: 충격파 지점 좌표
- **SI, h**: 추가 메쉬 파라미터 (선택 사항)

---

## Step 1: Calculate Parameters

```bash
cp ~/.openclaw/workspace/skills/salome-tip-shock-refine/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Auto-Discovery:**
- `{basename}_tip_points.csv` → 기존 tip-wake 정밀화용
- **`*shock*.csv`** → **충격파 포인트 기반 로컬 사이즈용 (NEW)**

**Outputs:**
- `{filename}_geom.hdf` - Geometry study
- `{filename}_mesh_args.json` - Mesh parameters (includes shock fields if CSV found)

---

## Step 2: Compute Mesh

```bash
cp ~/.openclaw/workspace/skills/salome-tip-shock-refine/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<basename>_mesh_args.json
```

---

## Script Differences from salome-tip_refine

| Aspect | salome-tip_refine | salome-tip-shock-refine |
|--------|--|------|
| **Shock CSV 탐색** | 없음 | **`*shock*.csv` 자동 탐색 (NEW)** |
| **충격파 포인트 로컬 사이즈** | 없음 | **충격파 지점 주변에 local cell size 적용 (NEW)** |
| shock_refine_size | — | **surf_size × 2 (= 8T) (NEW)** |
| tip_wake 정밀화 | 있음 | 있음 (유지) |
| 경계층 | SALOME 내장 | SALOME 내장 (유지) |
| snappyHexMesh 필요 | 아니요 | 아니요 |

---

## Important Notes

1. **SALOME path:** `/home/bosung/opt/salome/salome`
2. **Always use `-t -b`** (terminal + batch mode)
3. **Viscous layers** are fully configured inside `compute_mesh.py` via `netgen.ViscousLayers()`
4. **No snappyHexMesh dependency** - boundary layers, meshing, and export all handled in SALOME
5. **Tip-wake refinement** works via SALOME line geometry with local cell size
6. Wake lines are **clipped to domain** using `geompy.MakeCut(wake_line, domain)` before meshing
7. **No parallel meshing** - single-process Netgen mesh computation
8. **exportToFoam**이 complete OpenFOAM case 구조 (polyMesh + 0/p + 0/U + system/ + case.foam) 자동 생성
9. **fvSchemes/fvSolution**은 simpleFoam 호환 default 설정 포함

---

## ⏱️ 실행 시간 가이드 (exec timeout)

SALOME Netgen 메쉬 생성은 **수 분 ~ 수 시간** 소요 (cell 수, shock/tip refine에 따라). `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (Stage 1, 파라미터 계산) | `timeoutSeconds: 300` (STEP import 포함) |
| `compute_mesh.py` (Stage 2, meshing) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지 (exec 기본 timeout ~2분 초과 시 SIGTERM)
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

## Workflow Rules

### Golden Rule - Edit JSON directly, not scripts

파라미터 변경 시 `{filename}_mesh_args.json`을 **직접 편집**. 스크립트 재실행 금지.

### Workflow Steps

1. `calculate_mesh_params.py` 실행 → 파라미터 표 표시 → 승인 받음
2. 승인 후 수정 요청 시 → **수정할 파라미터만 JSON에서 직접 수정**
3. 관련 유도 파라미터 재계산 **절대 금지**
4. 재계산 필요하다면 → **사용자에게 명시적으로告知**
5. 실행 전 절대 JSON을 수정하거나 실행하지 않음

---

## Monitoring Rules

**compute_mesh.py 실행 후 - 사용자가 모니터링 요청 전까지 절대 확인하지 않음.**

1. `compute_mesh.py` 실행 → 즉시 "실행 중" 보고 + "완료되면 알려드립니다" 회신
2. **사용자가 모니터링을 요청하기 전까지** 로그 확인, 상태 확인 절대 하지 않음
3. 사용자가 모니터링 요청 시: `compute_mesh.py` 결과 확인
4. 완료 시: `{basename}-case/` 전체 구조 확인 (polyMesh + 0/ + system/) + checkMesh 결과

---

## Final Script (Confirmed 2026-09-02)

### SALOME Batch 실행법

```bash
/home/bosung/opt/salome/salome -t -b compute_mesh.py args:.:myShahed_mesh_args.json
```

**Always use `-t -b`** (terminal + batch) - no GUI, no server mode.

### SALOME Binary Path
`/home/bosung/opt/salome/salome`

---

## Test Execution: myShahed-salome (2026-09-02 18:34 기준)

### 준비된 파일들 (`/home/bosung/WinD/0.cfd/1.AI-agent/shock-refine-mesh/myShahed-salome/`)
- `myShahed.stp` — STEP/STL 기하 파일 (원본)
- `myShahed_tip_points.csv` — 팁 포인트 CSV (와이크 라인용, 6개 point)
- `myShahed-shock-1000_P99.csv` — 충격파 포인트 CSV (shock refine용, 31,315개 point)

### 테스트 결과 ✅

**Stage 1 완료:**
- `myShahed_geom.hdf` 생성 ✅
- `myShahed_mesh_args.json` 생성 ✅
- 파라미터 계산: max_size=0.4728m, surf_size=0.0170m, min_size=0.0085m

**Stage 2 완료:**
- myShahed-case/ 디렉토리 생성 ✅
- 31,315개 shock points vertex 생성 → local size 적용 (shock_refine_size=0.0341m) ✅
- 6개 wake lines 생성 → tip_wake_refine_size 적용 ✅
- 경계층: h1=0.0001m, layers=10, growth=1.3 ✅
- exportToFoam 완료 (polyMesh + 0/p + 0/U + system/ + case.foam) ✅

### 최종 메쉬 구조

```
myShahed-case/
├── constant/
│   └── polyMesh/
│       ├── boundary
│       ├── cellZones
│       ├── faces
│       ├── neighbour
│       ├── owner
│       └── points
├── 0/
│   ├── p           (압력)
│   └── U           (속도)
├── system/
│   ├── controlDict
│   ├── fvSchemes
│   └── fvSolution
└── case.foam       (메커니즘 marker)
```

---

## 수정된 compute_mesh.py 주요 변경사항 (2026-09-02 확정)

### NEW 1: Shock Point → Vertex → Local Size 적용 (wake line 처리 직후)
```python
# wake line local size 적용 후, mesh compute 전에
if len(shock_vertex_objects) > 0:
    print(f'\n  Creating {len(shock_vertex_objects)} shock vertices and applying local size...')
    shock_vtx_geom_list = []
    for i, (sx, sy, sz) in enumerate(shock_vertex_objects):
        v = geompy.MakeVertex(sx, sy, sz)
        geompy.addToStudy(v, f'shock_vtx_{i}')
        shock_vtx_geom_list.append(v)
    
    # 각 vertex에 local size 적용
    for sv in shock_vtx_geom_list:
        netgen.SetLocalSizeOnShape(sv, shock_refine_size)
    print(f'  > Shock vertex local size applied: {shock_refine_size:.6f} m')
```

### NEW 2: min_size 자동 보정 로직 (Netgen 호환성)
- STEP 파일에서 가장 작은 face edge length 계산 → `min_size`보다 작으면 `args['min_size'] = smallest_edge`로 자동 조정

### NEW 3: shock_refine_size = surf_size × 2
- 충격파 포인트 주변에 tip-wake와 동일한 정밀화 레벨 적용 (0.0341m)

---

## WORKFLOW COMPLETE ✅