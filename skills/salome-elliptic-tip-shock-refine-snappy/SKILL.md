# salome-elliptic-tip-shock-refine-snappy Skill

SALOME Netgen 기반 볼륨 메쉬 + **snappyHexMesh addLayers**로 경계층 추가하는 파이프라인입니다.

**핵심 구성:**
- **Far-field:** Ellipsoid (원기둥 형태, elliptic 스킬에서 가져옴)
- **Viscous layers:** snappyHexMesh addLayers (snappy 스킬에서 가져옴)
- **Tip-wake refinement:** tip_points CSV 자동 탐색 → wake line local size
- **Shock refinement:** shock CSV 자동 탐색 → vertex-based local size

## Workflow Overview

```
STEP File + tip_points CSV (optional) + shock CSV (optional)
    │
    ▼ Stage 1: calculate_mesh_params.py
    ├─ STEP import + bbox calculation
    ├─ Ellipsoid far-field 생성 (SALOME geompy)
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ Auto-discover {basename}-shock-wave*.csv
    ├─ Tip wake lines 생성 (if CSV found)
    ├─ Shock vertices 생성 (if CSV found)
    └─ Output: {basename}_mesh_args.json + {basename}_geom.hdf
    │
    ▼ Stage 2: compute_mesh.py
    ├─ SALOME Netgen mesh generation (BASE mesh)
    │   ├─ Refine box volumetric refinement
    │   ├─ Tip wake line local size (if tip CSV found)
    │   └─ Shock vertex local size (if shock CSV found)
    ├─ Export surface STL for snappyHexMesh
    ├─ snappyHexMesh case setup + addLayers (viscous BL)
    ├─ Parallel decomposePar + snappyHexMesh + reconstructParMesh
    └─ checkMesh execution + log output
```

## Parameters

### Mesh Sizing Logic

| Parameter | Formula | Description |
|-----------|---------|-------------|
| `max_size` | `max(cube_dx, cube_dy, cube_dz) / 50` | Background mesh cell size (far-field) |
| **`T`** | **`h1 * (growth^layers - 1) / (growth - 1)`** | BL total thickness |
| **`surf_size`** | **`4 × T`** | Surface mesh cell size (BL-based) |
| **`min_size`** | **`2 × T`** | Minimum allowed cell size (auto-corrected) |
| `refine_local_size` | `max_size / 4` | Refine box local cell size |
| `tip_wake_refine_size` | `surf_size * 2` | Wake line refinement cell size |
| **`shock_refine_size`** | **`surf_size * 2`** | Shock point local cell size |

### Ellipsoid Far-Field

```python
cube_dx = 10 * xl    # x-extent
cube_dy = 5 * yl     # y-extent
cube_dz = 10 * zl    # z-extent

# Ellipsoid semi-axes
half_x = cube_dx / 2.0
half_yz = max(cube_dy, cube_dz) / 2.0

# Position: STEP center at 25% of x-extent (upstream 25% / downstream 75%)
far_x_extent = 2.0 * half_x
far_x_offset = +0.25 * far_x_extent
```

## Batch Execution

```bash
# Stage 1: Calculate parameters (always use -t -b for batch mode)
/home/bosung/opt/salome/salome -t -b scripts/calculate_mesh_params.py args:<case_dir>:<step_file.stp>

# Stage 2: Compute mesh + snappyHexMesh
/home/bosung/opt/salome/salome -t -b scripts/compute_mesh.py args:<case_dir>:<basename>_mesh_args.json
```

## Tip Points CSV Format

Tip positions for wake line refinement:

```csv
cellID,x,y,z,SI,h
1,0.5,0.0,0.0,1.0,0.001
2,0.6,0.0,0.0,1.0,0.001
...
```

## Shock CSV Format

Shock wave positions for vertex-based local refinement:

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
Viscous boundary layers are handled **by snappyHexMesh addLayers** (NOT Netgen ViscousLayers).

### No Netgen ViscousLayers
The base mesh (without BL) is generated entirely by SALOME Netgen. Boundary layers are added by snappyHexMesh on top of the pre-computed mesh.

## File Structure (Output)

```
{case_dir}/
├── {basename}_geom.hdf       - Geometry study file
├── {basename}_mesh_args.json - Computed mesh parameters
├── {basename}_mesh.hdf       - Final computed mesh (base, without BL)
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
~/.openclaw/workspace/skills/salome-elliptic-tip-shock-refine-snappy/
├── SKILL.md                  - This file
├── assets/
│   └── snappyHexMesh-case-template/  - OpenFOAM case template
└── scripts/
    ├── calculate_mesh_params.py  - Stage 1: parameter calculation
    └── compute_mesh.py           - Stage 2: mesh computation + snappyHexMesh
```

## ⏱️ 실행 시간 가이드 (exec timeout)

SALOME Netgen 메쉬 + snappyHexMesh addLayers는 **수 분 ~ 수 시간** 소요. `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (Stage 1, 파라미터 계산) | `timeoutSeconds: 300` (STEP import 포함) |
| `compute_mesh.py` (Stage 2, meshing + addLayers) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지 (exec 기본 timeout ~2분 초과 시 SIGTERM)
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

## Workflow Rules

### Golden Rule - Edit JSON directly, not scripts

파라미터 변경 시 `{filename}_mesh_args.json`을 **직접 편집**. 스크립트 재실행 금지.

### Workflow Steps

1. `calculate_mesh_params.py` 실행 → 파라미터 표 표시 → 승인 받음
2. 승인 후 수정 요청 시 → **수정할 파라미터만 JSON에서 직접 수정**
3. 관련 유도 파라미터 재계산 **절대 금지**
4. 재계산 필요하다면 → **사용자에게 명시적으로 알려줌**
5. 실행 전 절대 JSON을 수정하거나 실행하지 않음

## Monitoring Rules

**compute_mesh.py 실행 후 - 사용자가 모니터링 요청 전까지 절대 확인하지 않음.**

1. `compute_mesh.py` 실행 → 즉시 "실행 중" 보고 + "완료되면 알려드립니다" 회신
2. **사용자가 모니터링을 요청하기 전까지** 로그 확인, 상태 확인, checkMesh 확인 절대 하지 않음
3. 사용자가 모니터링 요청 시: `log.snappyHexMesh`에서 `Running checkMesh...` 라인 확인 → 있으면 완료
4. 완료 시 `{basename}-case/checkMesh.log` 내용 프린트
5. checkMesh.log가 비어 있으면 수동 `checkMesh` 실행 → 결과 확인

### 최종 스크립트 (확정)

```bash
# Stage 1: Parameters
cp ~/.openclaw/workspace/skills/salome-elliptic-tip-shock-refine-snappy/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>

# Stage 2: Mesh + snappyHexMesh (자동 실행 — 모니터링 안 함)
cp ~/.openclaw/workspace/skills/salome-elliptic-tip-shock-refine-snappy/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json

# Monitoring (사용자 요청 시만)
tail -30 <directory>/log.snappyHexMesh  # Running checkMesh 확인
# 완료 시:
cat <directory>/<basename>-case/checkMesh.log
# 비어 있으면 수동 실행:
source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && cd <directory>/<basename>-case && checkMesh 2>&1 | tee checkMesh.log
```

## 경계층 (addLayers) 안정화 설정 — 2026-09-21

`snappyMesh-elliptic-tip-refine`과 동일하게 경계층이 잘 쌓이도록
`assets/.../snappyHexMeshDict` template을 동기화함 (backup: `snappyHexMeshDict.bak-20260921`).

### castellatedMeshControls
- `nCellsBetweenLevels 3 -> 5` — 급격한 배경 격자 해상도 변화로 인한 Layer Collapse 방지

### addLayersControls
- `maxThicknessToMedialRatio 5.0 -> 100.0` (LE/곡면 국소 미세 셀 영역 두께 제약 해제)
- `maxFaceThicknessRatio 100.0 -> 1000.0` (배경 격자 크기 대비 두께 제약 대폭 완화)
- `nBufferCellsNoExtrude 3 -> 0` (실패 지점 인접 셀 동반 삭제 방지)
- 스무딩/완화: `featureAngle 75 -> 180`, `nRelaxIter 20 -> 50`, `nSmoothSurfaceNormals 1 -> 5`,
  `nSmoothThickness 10 -> 20`, `nSmoothNormals 3 -> 5`, `nMedialAxisIter 30 -> 50`,
  `nLayerIter 100 -> 200`, `nRelaxedIter 20 -> 50`
- relaxed: `maxNonOrtho 90 -> 95`, `minFaceWeight/minVolRatio 0.005 -> 0.0001`

### meshQualityControls
- `maxNonOrtho 80 -> 85`, `maxInternalSkewness 4 -> 20`, `minVol 1e-13 -> 1e-15`
- `minDeterminant 0.001 -> 1e-5`, `minTwist 0.02 -> -1`
- `minFaceWeight 0.05 -> 0.0001`, `minVolRatio 0.01 -> 0.0001` (핵심)
- `minTetQuality 1e-9 -> 1e-15`, relaxed `maxNonOrtho 85 -> 95`

### 유의사항
- `expansionRatio`는 반드시 수치 (placeholder가 그대로 들어가면
  `FOAM FATAL IO ERROR: expected scalar value, found 'BASE_EXPANSION_RATIO'`)
- `relativeSizes false` + `thicknessModel firstAndExpansion`이면
  `firstLayerThickness`가 절대 길이(mm)로 적용됨
