# salome-tip_refine-snappy 스킬 상세 설명

> SALOME 기반 OpenFOAM snappyHexMesh 메쉬 생성 스킬
> tip-wake line refinement 기능 포함
> 최종 업데이트: 2026-07-06

---

## 1. 스킬 개요

### 1.1 목적
SALOME를 통해 STEP 파일에서 유체역학 전처리 메쉬를 생성하고, OpenFOAM의 `snappyHexMesh`가 사용할 case를 자동 생성합니다.

### 1.2 핵심 기능
- STEP 파일 import 및 geometry processing
- Netgen tetrahedral mesher를 통한 체적 메쉬 생성
- **Tip points CSV 자동 탐지 및 wake line refinement**
- refineBox volumetric refinement (wake capture)
- OpenFOAM case 자동 생성 (snappyHexMesh ready)
- parallel snappyHexMesh 자동 실행
- checkMesh 자동 실행 및 결과 출력

### 1.3 스킬 구성

```
skills/salome-tip_refine-snappy/
├── SKILL.md                          ← 스킬 사용 가이드
├── SKILL-DETAIL.md                  ← 상세 로직 문서 (이 파일)
├── scripts/
│   ├── calculate_mesh_params.py     ← Stage 1: 파라미터 계산
│   └── compute_mesh.py              ← Stage 2: 메쉬 생성 + snappyHexMesh
└── assets/
    └── snappyHexMesh-case-template/ ← OpenFOAM case 템플릿
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

## 2. calculate_mesh_params.py 상세 설명

### 2.1 스크립트 개요

- **역할:** STEP 파일에서 geometry processing → 파라미터 계산 → JSON 저장
- **명령줄 인자:** `args:<directory>:<filename.stp>`
- **출력 파일:**
  - `{basename}_geom.hdf` — SALOME geometry study
  - `{basename}_mesh_args.json` — 메쉬 파라미터 JSON
  - `{basename}.log` — 실행 로그 (stdout 리다이렉트)

### 2.2 실행 순서

#### Step 1: ARGUMENT PARSING

```
명령줄에서 STEP 파일 경로 추출
예: args:/home/bosung/test/LC62-50B.stp
→ directory=/home/bosung/test
→ filename=LC62-50B.stp
→ step_path=/home/bosung/test/LC62-50B.stp
```

#### Step 2: TIP POINTS CSV AUTO-DISCOVERY

```
{basename}_tip_points.csv 파일 자동 탐지

header 감지 로직:
1. 첫 행(first_row) 읽기
2. 첫 행의 첫 번째 요소를 float()로 변환 시도
   - 성공 → 첫 행은 데이터: tip_points에 추가
   - 실패 → 첫 행은 header: skip
3. 이후 행 모두: x,y,z 파싱하여 tip_points 추가
4. CSV 없음 → "Skipping tip wake refinement" 출력
```

**CSV 파일 구조:**
```
x,y,z
2.0324, 0.0000, 0.6942
...
```

#### Step 3: GEOMETRY PROCESSING

```python
# 1. STEP import
imported_shape = geompy.ImportSTEP(step_path)
geompy.addToStudy(imported_shape, "01_Imported_STEP")

# 2. Bounding box 계산
x_min, x_max, y_min, y_max, z_min, z_max = geompy.BoundingBox(imported_shape)
xl = x_max - x_min
yl = y_max - y_min
zl = z_max - z_min
cx, cy, cz = (x_min+x_max)/2, (y_min+y_max)/2, (z_min+z_max)/2

# 3. Solid creation 시도
try:
    tool_shape = geompy.MakeSolid([imported_shape])
except:
    tool_shape = imported_shape  # shell fallback

# 4. Farfield Box 생성
cube_dx = 10 * xl
cube_dy = 5 * yl
cube_dz = 10 * zl
cube = geompy.MakeBoxDXDYDZ(cube_dx, cube_dy, cube_dz)
tx = cx - 2.5 * xl
ty = cy - 2.5 * yl
tz = cz - 5.0 * zl
moved_cube = geompy.MakeTranslation(cube, tx, ty, tz)

# 5. Refine Box (wake capture) 생성
refine_dx = 5 * xl
refine_dy = 2 * yl
refine_dz = 2 * zl
refine_tx = cx - 1.25 * xl
refine_ty = cy - yl
refine_tz = cz - zl
```

#### Step 4: BOOLEAN OPERATION & FACE CLASSIFICATION

```python
# MakeCut 실행, 실패 시 MakePartition로 fallback
try:
    domain = geompy.MakeCut(moved_cube, tool_shape)
except:
    domain = geompy.MakePartition([moved_cube], [tool_shape])

# Face 분류 (far-field vs model surface)
tol = 1e-4
for face in all_faces:
    fb = geompy.BoundingBox(face)
    # far-box bounding box와 tol 이내로 일치하면 far-face
    # 아니면 model-face
```

#### Step 5: MESH PARAMETER CALCULATION

**Default values:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| h1 | 0.0001 | First cell height |
| layers | 5 | Boundary layer count |
| growth | 1.3524 | BL growth rate |
| fineness | 2 | Netgen density (2=mod/3=fine/4=vfine) |

**Derived values:**
```
T = h1 × (growth^layers - 1) / (growth - 1)
BASE_MINTHICKNESS = T × 0.5
min_size = T
surf_size = 10 × T
max_size = 10 × xl / 50
refine_local_size = max_size / 4
```

**tip_wake_refine_size:**
```
tip_wake_refine_size = 2 × surf_size  (if tip CSV found)
```

#### Step 6: WAKE LINE GENERATION (if tip CSV found)

```
for each tip point (tx, ty, tz):
    wake_line = (tx, ty, tz, rb_xmax, ty, tz)
    # rb_xmax = refine_cx + refine_dx / 2
    # tip → refine_box_xmax in X-direction
```

#### Step 7: JSON OUTPUT

**JSON 스키마:**
```json
{
  "step_path": "string",
  "base_dir": "string",
  "base_name": "string",
  "geom_hdf": "string",
  "xl": float,       // Model length (m)
  "yl": float,       // Model width (m)
  "zl": float,       // Model height (m)
  "h1": float,       // First cell height (m)
  "layers": int,     // BL count
  "growth": float,   // BL growth rate
  "fineness": int,   // 2=mod / 3=fine / 4=vfine
  "T": float,        // BL total thickness (m)
  "BASE_MINTHICKNESS": float, // T × 0.5
  "min_size": float, // = T
  "surf_size": float, // = 10 × T
  "max_size": float,  // = 10xl / 50
  "refine_local_size": float, // = max_size / 4
  "cube_dx/dy/dz": float, // Domain dimensions
  "refine_dx/dy/dz": float, // Wake capture box dimensions
  "refine_cx/y/z": float,   // Refine box center
  "refine_tx/y/z": float,   // Refine box translate offset
  "far_faces_count": int,
  "model_faces_count": int,
  "tip_csv_path": "string or null",
  "tip_points_count": int,
  "tip_wake_lines": [[x1,y1,z1,x2,y2,z2], ...],
  "tip_wake_refine_size": float or null
}
```

---

## 3. compute_mesh.py 상세 설명

### 3.1 스크립트 개요

- **역할:** 메쉬 생성 → OpenFOAM case export → snappyHexMesh → checkMesh
- **명령줄 인자:** `args:<directory>:<filename>_mesh_args.json`
- **출력 파일:**
  - `{basename}_mesh_setup.hdf` — 메쉬 설정 (SALOME GUI 편집용)
  - `{basename}_mesh.hdf` — 계산 완료 메쉬
  - `{basename}-case/` — OpenFOAM case directory
  - `log.snappyHexMesh`, `log.reconstructParMesh`, `checkMesh.log`

### 3.2 핵심 헬퍼 클래스/함수

#### MeshBuffer (메쉬 export용)

```python
class MeshBuffer:
    def __init__(self, mesh, volume_id):
        # volume의 face-nodes 매핑 추출
        # faces: face의 node indices list
        # keys: sorted(fnodes) as tuple
        # fL: face count
    
    @staticmethod
    def Key(fnodes): return tuple(sorted(fnodes))
```

#### exportToFoam(mesh, dirname, base_name)

```
polyMesh export 로직:

1. volume element 추출
2. free face extraction (external faces identification)
3. face adjacency graph construction:
   - interior faces: owner = neighbor
   - external faces: owner = volume_id, neighbour = -1
4. face sorting by shared nodes
5. boundary face identification
6. boundary group identification (far, surface)
7. write OpenFOAM polyMesh files:
   - points: node coordinates
   - faces: node index lists (0-based)
   - owner: neighbor for each face
   - neighbour: for interior faces
   - boundary: polyBoundaryMesh with face counts
   - cellZones: volume groups (if any)
```

#### setup_snappy_hex_mesh_case(base_dir, base_name, ...)

```
1. template case를 {basename}-case로 복사
2. snappyHexMeshDict placeholder 교체:
   - BASENAME_surface → {base_name}_surface
   - BASE_LAYERS → layers
   - BASE_GROWTH → growth
   - BASE_FIRSTLAYER → h1
   - BASE_MINTHICKNESS → base_minthickness
3. controlDict 자동 수정:
   - writeControl timeStep → adjustableRunTime
   - writeInterval 0 → 1
4. case_dir, stl_dir 반환
```

#### export_surface_stl(mesh, group_name, stl_path)

```
1. STL group에서 face ID 추출
2. 각 face에 대해:
   - 3개 node의 좌표 가져오기
   - cross product로 normal 계산
3. ASCII STL 형식으로 write:
   solid {name}
     facet normal nx ny nz
       outer loop
         vertex x1 y1 z1
         vertex x2 y2 z2
         vertex x3 y3 z3
       endloop
     endfacet
   endsolid {name}
```

### 3.3 워크플로우

#### Stage 1: ARGUMENT PARSING

```
JSON 파일에서 모든 파라미터 추출
tip_wake_lines가 존재하면 tip CSV 기반 데이터로 해석
```

#### Stage 2: SHOW PARAMETERS

```
user input 파라미터 표: h1, layers, growth, fineness
derived 파라미터 표: T, min_size, surf_size, max_size, refine_box info
tip_wake_lines가 있으면 추가 행 출력
```

#### Stage 3: REBUILD GEOMETRY

```python
# STEP 재import
imported_shape = geompy.ImportSTEP(step_path)
tool_shape = geompy.MakeSolid([imported_shape])
moved_cube = geompy.MakeBoxDXDYDZ(10xl, 5yl, 10zl) → translate

# Boolean
domain = geompy.MakeCut(moved_cube, tool_shape)
# ComputeTolerance 적용 (optional)
domain = geompy.ComputeTolerance(domain, 0.001)

# Face 분류
all_faces = geompy.SubShapeAll(domain, FACE)
far_faces, model_faces 분류

# Group 생성
group_far = CreateGroup(domain, FACE) → UnionList(far_faces)
group_model = CreateGroup(domain, FACE) → UnionList(model_faces)
```

#### Stage 4: CREATE REFINE BOX

```python
# Raw box at (0,0,0)
raw_refine_box = geompy.MakeBoxDXDYDZ(refine_dx, refine_dy, refine_dz)
refined_refine_box = geompy.MakeTranslation(raw_refine_box, refine_tx, refine_ty, refine_tz)

# Volume group
refine_box_volume_group = CreateGroup(refined_refine_box, SOLID)
refine_box_solids = SubShapeAll(refined_refine_box, SOLID)
UnionList(refine_box_volume_group, refine_box_solids)
```

#### Stage 5: CREATE WAKE LINES (if tip CSV found)

```python
for i, (x1, y1, z1, x2, y2, z2) in enumerate(tip_wake_lines):
    p1 = geompy.MakeVertex(x1, y1, z1)
    p2 = geompy.MakeVertex(x2, y2, z2)
    wake_line = geompy.MakeEdge(p1, p2)
    wake_line_objects.append(wake_line)
```

#### Stage 6: MESH SETUP

```python
mesh = smesh.Mesh(domain, f"{base_name}_mesh")
netgen = mesh.Tetrahedron(algo=NETGEN_1D2D3D)

params = netgen.Parameters()
params.SetNbThreads(8)
params.SetMaxSize(max_size)       // max_size (coarsest)
params.SetMinSize(min_size)       // min_size (finest)
params.SetLocalSizeOnShape(group_model, surf_size)  // surface
params.SetUseSurfaceCurvature(1)  // ← CRITICAL: must be 1
params.SetFineness(fineness)

// refineBox local size
netgen.SetLocalSizeOnShape(refine_box_volume_group, refine_local_size)

// wake lines local size (if tip CSV found)
if wake_line_objects:
    for wl in wake_line_objects:
        netgen.SetLocalSizeOnShape(wl, tip_wake_refine_size)

mesh.GroupOnGeom(group_far, 'far', FACE)
mesh.GroupOnGeom(group_model, f'{base_name}_surface', FACE)
```

#### Stage 7: MESH COMPUTE

```
success = mesh.Compute()  // no timeout
```

#### Stage 8: EXPORT (if success)

```
1. mesh → mesh.hdf 저장
2. surface mesh → STL export
3. exportToFoam() → OpenFOAM polyMesh
4. setup_snappy_hex_mesh_case() → case directory
```

#### Stage 9: PARALLEL snappyHexMesh

```
1. lscpu로 물리 코어 계산: cores × sockets
2. decomposeParDict 생성:
   method: scotch
   numberOfSubdomains: <num_cores>
   coeffs.n: (<num_cores>, 1, 1)
3. decomposePar -force
4. mpirun --oversubscribe -np <num_cores> snappyHexMesh -parallel
5. reconstructParMesh -constant
6. processor*/ 제거
```

#### Stage 10: CHECKMESH

```
1. checkMesh 자동 실행
2. 주요 행 추출 (cell/face quality, volume, skewness 등)
3. 콘솔 출력
```

---

## 4. 메쉬 파라미터 상세

### 4.1 기본값 및 계산식

| 파라미터 | 기본값 | 계산식 | 설명 |
|----------|--------|--------|------|
| **h1** | 0.0001 m | - | 첫 cell 두께 (BL) |
| **layers** | 5 | - | BL layer 수 |
| **growth** | 1.3524 | - | BL 성장률 |
| **fineness** | 2 | - | 메쉬 밀도 (2=mod/3=fine/4=vfine) |
| **T** | derived | `h1×(growth^n-1)/(growth-1)` | 총 BL 두께 |
| **min_size** | = T | - | 메쉬 min cell size |
| **surf_size** | = 10×T | - | surface mesh size |
| **max_size** | = 10xl/50 | - | max cell size |
| **refine_local_size** | = max_size/4 | - | refineBox internal size |
| **BASE_MINTHICKNESS** | = T×0.5 | - | BL min thickness |

### 4.2 tip_wake_refine_size

```
tip_csv_path가 존재할 때:
tip_wake_refine_size = 2 × surf_size

tip_csv_path가 없거나 null일 때:
tip_wake_refine_size = None
```

### 4.3 refineBox 위치 및 크기

```
refine_dx = 5 × xl
refine_dy = 2 × yl
refine_dz = 2 × zl
refine_cx = cx (object center)
refine_cy = cy
refine_cz = cz
refine_tx = cx - 1.25×xl
refine_ty = cy - yl
refine_tz = cz - zl
```

---

## 5. snappyHexMeshDict 생성 로직

### 5.1 템플릿 → 실제 case

```
template/snappyHexMeshDict:
  geometry {
    "BASENAME_surface.stl" {
      type triSurfaceMesh;
    }
  }
  layers {
    "BASENAME_surface" {
      nSurfaceLayers BASE_LAYERS;
      expansionRatio BASE_GROWTH;
      firstLayerThickness BASE_FIRSTLAYER;
      minThickness BASE_MINTHICKNESS;
    }
  }

→ {basename}_case/system/snappyHexMeshDict:
  geometry {
    "LC62-50B_surface.stl" {
      type triSurfaceMesh;
    }
  }
  layers {
    "LC62-50B_surface" {
      nSurfaceLayers 5;
      expansionRatio 1.3524;
      firstLayerThickness 0.0001;
      minThickness 0.00122;
    }
  }
```

### 5.2 controlDict 자동 수정

```
writeControl timeStep → adjustableRunTime
writeInterval 0 → 1
```

### 5.3 decomposeParDict 자동 생성

```foam
method scotch
numberOfSubdomains <physical_cores>
coeffs {
    n (<num_cores> 1 1)
}
```

---

## 6.tip_wake_line_refinement 상세

### 6.1 작동 원리

```
tip CSV → 각 tip point에서 wake downstream 방향(+)으로 line 생성
각 line에 Netgen local size 적용 → wake 영역 메쉬 refinement
```

### 6.2 tip_csv_path가 있을 때

```
Tip Point 1 (x1, y1, z1) → Wake Line → (refine_box_xmax, y1, z1)
Tip Point 2 (x2, y2, z2) → Wake Line → (refine_box_xmax, y2, z2)
...

refine_box_xmax = refine_cx + refine_dx / 2
```

### 6.3 메쉬 크기 중첩 로직

```
refineBox internal: refine_local_size (coarser, e.g. 0.1 m)
wake line internal: tip_wake_refine_size (finer, e.g. 0.02 m)
intersection zone: min(refine_local_size, tip_wake_refine_size) = tip_wake_refine_size
```

### 6.4 tip_csv_path가 없을 때

```
wake_line_objects = [] → wake line 생성 건너뜀
기존 salome-snappy와 동일한 behavior
```

---

## 7. OPENFOAM CASE OUTPUT 구조

```
{basename}-case/
├── constant/
│   ├── polyMesh/
│   │   ├── boundary      ← polyBoundaryMesh
│   │   ├── faces         ← faceList (all faces)
│   │   ├── neighbour     ← labelList (interior faces)
│   │   ├── owner         ← labelList (all faces)
│   │   ├── points        ← vectorField (all nodes)
│   │   └── cellZones     ← regIOobject (volume groups)
│   └── triSurface/
│       └── {basename}_surface.stl
├── system/
│   ├── controlDict       ← writeInterval 1
│   ├── decomposeParDict ← numberOfSubdomains set
│   ├── fvSchemes
│   ├── fvSolution
│   └── snappyHexMeshDict ← BL params filled
└── 0/                   ← template 기본 (대부분 비어있음)
```

---

## 8. 실행 명령어

### 8.1 Step 1: 파라미터 계산

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/calculate_mesh_params.py <work_dir>/
/home/bosung/opt/salome/salome -t -b <work_dir>/calculate_mesh_params.py args:<work_dir>:<filename.stp>
```

### 8.2 Step 2: 메쉬 계산

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine-snappy/scripts/compute_mesh.py <work_dir>/
/home/bosung/opt/salome/salome -t -b <work_dir>/compute_mesh.py args:<work_dir>:<filename>_mesh_args.json
```

### 8.3 SALOME BATCH MODE

```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```

`-t` = terminal mode
`-b` = batch mode (no GUI)

---

## 9. 중요한 설정 (Critical Settings)

### 9.1 SetUseSurfaceCurvature (반드시 1!)

```python
params.SetUseSurfaceCurvature(1)  // ← MUST BE 1
```

- **Enable (1):** STEP 메쉬 성공적으로 동작
- **Disable (0):** 메쉬 계산 실패 또는 무한 정지
- **발생일:** 2026-07-06 발견

### 9.2 mpirun --oversubscribe

```bash
mpirun --oversubscribe -np <num_cores> snappyHexMesh -parallel
```

`--oversubscribe`는 hyperthreading 시스템에서 필수입니다.

### 9.3 numberOfSubdomains

```foam
numberOfSubdomains <physical_cores>  // NOT nSubdomains!
```

OpenFOAM v2512는 `numberOfSubdomains`를 사용합니다.

---

## 10. BACKWARDS COMPATIBILITY

- **tip CSV 없음:** salome-snappy와 완전히 동일
- **tip CSV 있음:** tip wake line refinement 추가
- **원본 salome-snappy:** 수정 없음
- **JSON 필드:** tip CSV 없을 때 tip_* 필드 없음

---

## 11. KNOWN ISSUES & RESOLUTIONS

| Issue | Resolution |
|-------|------------|
| `surf_size` 미정의 (tip wake 계산 시) | tip wake calc을 surf_size 계산 이후로 이동 |
| `geompy.makeEdge` AttributeError | `geompy.MakeEdge` (PascalCase)로 변경 |
| template dir not found | compute_mesh.py에 hardcoded path |
| wake line end x = STEP max X (wrong) | end x = `refine_box_xmax`로 수정 |
| over-refinement timeout | tip_wake_refine_size sizing 조정 |
| **STEP mesh fail/hang** | **SetUseSurfaceCurvature(1) 필수** |

---

## 12. salome-tip_refine-snappy vs salome-snappy 비교

| 항목 | salome-snappy | salome-tip_refine-snappy |
|------|---------------|-------------------------|
| tip CSV 자동 탐지 | ✗ | ✓ |
| wake line refinement | ✗ | ✓ (X-direction) |
| tip_wake_refine_size | ✗ | `2 × surf_size` |
| backwards compat | — | tip CSV 없으면 동일 |
| SetUseSurfaceCurvature | 1 | 1 |
| fineness 기본값 | 3 | **2** |
| surf_size 공식 | `20×T` | **`10×T`** |
| 원본 파일 | untouched | untouched |
