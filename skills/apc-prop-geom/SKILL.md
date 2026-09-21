# APC Propeller Geometry Generation Skill

## Objective
Reconstruct a 3D propeller geometry from APC's PE0 performance data files, generating physically accurate blade geometry with CLARK-Y airfoil sections for CFD/CAD workflows.

---

## Coordinate System (Global)

| Axis | Direction | Physical Meaning |
|------|-----------|-----------------|
| **+X** | Rotation axis (shaft) | 프로펠러 회전축 방향 (Axial/Thrust) |
| **+Y** | Spanwise | 허브(Y=0) → 팁(Y=R) 방향 (반지름) |
| **+Z** | Chord direction | 전연(LE, Z=0) → 후연(TE, Z=c) 방향 |

**에어포일 단면**: X-Z 평면 (Y축에 수직)
- **X**: 에어포일 두께 방향 (thickness)
- **Z**: 에어포일 chord 방향 (chord length)

---

## Unit System

- **PE0 파일 내 모든 길이 파라미터**: 인치(inch)
- **변환 상수**: `INCH_TO_METER = 0.0254 m/in`
- **모든 내부 계산**: 미터(m) 단위
- **PE0 STATION**: 인치 → 미터 변환 후 Y 스팬으로 사용
- **PE0 CHORD**: 인치 → 미터 변환
- **PE0 SWEEP**: 인치 → 미터 변환 (Z 축 오프셋)
- **PE0 RAKE**: 인치 → 미터 변환 (X 축 오프셋)
- **PE0 THICKNESS RATIO**: 무차원 (t/c), 변환 없음

---

## PE0 File Parsing

### Header Metadata
PE0 파일 헤더에서 다음 값을 파싱:

| PE0 컬럼 | 원본 단위 | 미터 변환 | 변수명 |
|----------|-----------|-----------|--------|
| `RADIUS` | inch | `R = R_in × 0.0254` | 프로펠러 외경 반경 [m] |
| `HUBRAD` | inch | `r_hub = r_hub_in × 0.0254` | 허브 반경 [m] |
| `HUBTRA` | inch | `r_trans = r_trans_in × 0.0254` | 허브-유동 이행 반경 [m] |
| `BLADES` | - | 없음 | `N_blades` |

무차원 비율 계산:
- `eta_hub = r_hub / R`
- `eta_trans = r_trans / R`

### Station Table
PE0 테이블에서 각 station별 데이터 파싱:

| PE0 컬럼 | 원본 단위 | 미터 변환 | 변수명 | 물리적 의미 |
|----------|-----------|-----------|--------|------------|
| `STATION` | inch | `y_span = station_in × 0.0254` | +Y 스팬 위치 [m] |
| `CHORD` | inch | `c_i = chord_in × 0.0254` | 시위길이 [m] |
| `SWEEP(Y)` | inch | `S_i = sweep_in × 0.0254` | Z 축 오프셋 [m] |
| `RAKE(Z)` | inch | `K_i = rake_in × 0.0254` | X 축 오프셋 [m] |
| `THICKNESS RATIO` | - | 그대로 사용 | `t_ratio_i` | 두께비 (t/c) |
| `TWIST` | deg | 그대로 사용 | `beta_i` | 피치 비틀림 각도 |

**SWEEP와 RAKE는 절대값**(offest)이며, 비율이 아님.

---

## 기하체 생성 워크플로우 (스크립트 로직)

### 1단계: PE0 파일 파싱 및 단위 변환
PE0 파일 읽기 → 헤더 메타데이터(RADIUS, HUBRAD, HUBTRA, BLADES) 추출 → 모든 길이 값을 인치(in)에서 미터(m)로 변환 (`× 0.0254`) → station 테이블에서 각 스테이션별 데이터(STATION, CHORD, SWEEP, RAKE, THICKNESS RATIO, TWIST) 추출

### 2단계: CLARK-Y 에어포일 생성
UIUC Airfoil Database에서 CLARK-Y 실제 좌표 데이터 로드 (upper 61pts + lower 61pts) → `(chord_frac, thick_frac)` non-dimensional 배열 생성 → closed loop: `upper[::-1] + lower + LE repeat`

### 3단계: 에어포일 스케일링
- `max_clarky_thick = 0.117` (CLARK-Y 기본 최대 두께비 11.7%)
- `scale_factor = t_ratio_i / max_clarky_thick` (PE0 t/c 비율을 CLARK-Y 기준으로 비례 조정)
- `z_airfoil = chord_frac × c_i` → Z축(chord 방향) [m]
- `x_airfoil = thick_frac × scale_factor × c_i` → X축(thickness 방향) [m]

### 4단계: LE 피벗 비틀림 회전 (Y축 기준)
`beta_rad = β_i × π/180`
```
x_rot = x_airfoil × cos(β_rad) - z_airfoil × sin(β_rad)
z_rot = x_airfoil × sin(β_rad) + z_airfoil × cos(β_rad)
```
β > 0일 때 LE가 +X 방향(up)

### 5단계: 3D 좌표 합성
``` 
X_3d = x_rot + K_i           # +X: 회전축 + RAKE 오프셋
Y_3d = y_span                # +Y: 스팬 방향 (원본 STATION 값 그대로, 재매핑 X)
Z_3d = z_rot + skew_sign × S_i  # +Z: chord + SWEEP 오프셋
```
LH 프로펠러: `skew_sign = -1.0`, RH: `skew_sign = +1.0`

**중요**: station Y는 재매핑 없이 PE0 STATION 원본 값을 그대로 사용. station0(Y=0)에서 tip(R)까지 직선 loft.

### 6단계: aerodynamic 필터링 (eta_start)
- `eta_start` 기본값 0.0 → **모든 station을 aerodynamic region**으로 사용
- `eta_i = y_span / R`, `is_aero = (eta_i >= eta_start)`
- HUBTRA는 무시 — hub는 cylinder로 별도 처리

### 7단계: root airfoil 생성 (station_root)
- **station_root**: station_0 (station_idx=0)의 X, Z 좌표 그대로 복사
- Y 위치: `df_stations.iloc[0]['y_span']` → PE0 STATION=0 값 (예: 7x5에서는 0.08" ≈ 0.002m)
- **재매핑 없음**: PE0 원본 Y값 그대로 사용 (station_0를 0으로 변환하지 않음)

### 8단계: blade1 솔리드 생성 (ThruSections loft)
- **root airfoil**: Z span을 hub_diameter에 맞게 스케일 → hub와 match
  - `z_scale = hub_diameter / root_z_span`
  - `Z_scaled = (Z - Z_min) × z_scale + (Z_center - hub_radius)`
- **blade1**: `station_root(Y=STATION[0]) → aerodynamic stations(STATION[1]~R)` 전체 섹션을 loft
- **섹션 수**: root 1개 + aero stations N개 = 총 N+1개
- **로프트 알고리즘**: `BRepOffsetAPI_ThruSections` 사용 (메모리 효율적)
- **Y 범위**: `STATION[0] → R`

### 9단계: blade2 생성 (rotation)
- blade1을 **+X축 기준 180° 회전**하여 blade2 생성
- 두 블레이드는 Y=0 평면에서 맞닿음
- OCC API: `gp_Trsf.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(1,0,0)), π)`
- 2개 블레이드 (N_blades=2)

### 10단계: hub cylinder 생성
- **반지름**: `HUBRAD` (PE0 HUBRAD 직접 사용) — 0.1R 아님
- **방향**: **+X축** (회전축 방향)
- **Y 중심**: `0.0` (blade1 root Y = +root_y, blade2 root Y = -root_y의正中)
- **높이 결정**: **root airfoil X extent vs station_1 airfoil X extent** → 더 큰(넓은) 쪽 사용
  - `root_x_extent = root_x_max - root_x_min`
  - `s1_x_extent = station_1_x_max - station_1_x_min`
  - `s1_x_extent > root_x_extent` → station_1의 xmin, xmax 사용
  - `root_x_extent >= s1_x_extent` → root의 xmin, xmax 사용
  - **이유**: root airfoil이 극히 얕은 경우(예: 28x20-4에서 root X extent ≈ 0.07mm) hub cylinder가 지나치게 가늘어지는 문제 방지
- **Z alignment**: root airfoil Z center에 정렬
- **X 시작점**: 선택된 airfoil의 xmin에 cylinder 원점 설정

### 11단계: fuse + STEP export
- `blade1 ∪ blade2` → 먼저 fuse → 결과 + hub fuse (한 번에 하나씩)
- **degenerate edges fix**: `ShapeFix_Shape`로 정리
- **STEP export**: `STEPControl_Writer.Transfer(fixed, AsIs).Write()`
- **검증**: `BRepCheck_Analyzer`로 Valid 확인
- **출력 파일명**: `<pe0_filename>.step` (예: `7x5-PERF.step`)

### 12단계: CSV export
- **출력 파일명**: `<pe0_filename>.csv` (예: `7x5-PERF.csv`)
- **컬럼**: `station_idx, r_over_R, X, Y, Z`
- 모든 aerodynamic station의 3D 좌표 (미터 단위)

---

## Airfoil: CLARK-Y (from UIUC Airfoil Database)

CLARK-Y 에어포일 좌표는 UIUC Airfoil Coordinates Database에서 직접 가져온 비차원 데이터 사용.

- **형식**: `(x_chord, y_thickness)` non-dimensional
- `x_chord`: chord 방향 [0=LE, 1=TE]
- `y_thickness`: 두께 방향 (upper > 0, lower < 0)
- **Upper surface**: 61 points (LE→TE)
- **Lower surface**: 61 points (LE→TE)
- **Closed loop**: upper[::-1] + lower + LE repeat

### Scaling to Physical Dimensions
```python
# CLARK-Y: [chord_frac, thick_frac] non-dimensional
# CLARK-Y max thickness ratio = 0.117 (11.7% at 28% chord)
max_clarky_thick = 0.117
scale_factor = t_ratio_i / max_clarky_thick  # Relative to CLARK-Y default 11.7%

z_airfoil = chord_frac × c_i          # Z: chord direction [m]
x_airfoil = thick_frac × scale_factor × c_i  # X: thickness [m]
```

**중요**: `t_ratio`는 PE0에서 제공하는 **실제 t/c 비율**(예: 0.3113 = 31.13% chord). CLARK-Y의 기본 max thickness (11.7%)를 기준으로 **비례 조정**하여 PE0 비율에 맞게 두께를 변경.
- PE0 t_ratio > CLARK-Y 11.7% → 두께 증가
- PE0 t_ratio < CLARK-Y 11.7% → 두께 감소
- `thick_frac`는 CLARK-Y non-dimensional thickness coordinate (max ~0.0916)

---

## 3D Coordinate Transformation Pipeline

### Step 1: CLARK-Y Airfoil Scaling
```python
airfoil_base = [chord_frac, thick_frac]  # non-dimensional (chord=1, max thick ~0.117)
max_clarky_thick = 0.117
scale_factor = t_ratio_i / max_clarky_thick  # PE0 t_ratio relative to CLARK-Y default

x_airfoil = airfoil_base[:, 1] × scale_factor × c_i   # X: thickness [m]
z_airfoil = airfoil_base[:, 0] × c_i                   # Z: chord [m]
```

PE0의 `THICKNESS RATIO`는 **실제 t/c 비율**(예: 0.3113 = 31.13% chord). CLARK-Y의 기본 11.7%를 기준으로 비례 조정하여 PE0에 맞는 두께로 변경합니다.

### Step 2: LE(0,0) Pivot Twist Rotation (around Y axis)
피치각 β > 0이면 LE가 +X 방향으로 올라감 (pitch up):

```python
x_rot = x_airfoil × cos(β_rad) - z_airfoil × sin(β_rad)
z_rot = x_airfoil × sin(β_rad) + z_airfoil × cos(β_rad)
```

### Step 3: 3D Global Coordinates
```python
X_3d = x_rot + K_i                    # +X: Axial (shaft) + RAKE offset
Y_3d = y_span                         # +Y: Spanwise position
Z_3d = z_rot + (skew_sign × S_i)      # +Z: Chord + SWEEP/SKEW offset
```

- `skew_sign = -1.0` for LH (Left-Hand) propeller
- `skew_sign = +1.0` for RH (Right-Hand) propeller

### Step 4-A: Domain Filtering (Hub Trimming)
```python
eta_i = y_span / R
is_aerodynamic = (eta_i >= eta_trans)  # eta_trans = r_trans / R
```

### Step 4-B: Span Linear Re-mapping
유동 영역을 `[eta_trans × R, R]` 구간으로 선형 재배치:

```python
u = (y_span - y_min) / (y_max - y_min)
y_remapped = [eta_trans + (1.0 - eta_trans) × u] × R
```

---

## Output Files

### CSV (`<pe0_filename>.csv`)
```
station_idx, r_over_R, X, Y, Z
```
- `station_idx`: station 번호 (root=-1)
- `r_over_R`: 무차원 반경 (y_span / R)
- `X`, `Y`, `Z`: 미터(m) 단위 좌표
- 에어포일 outline points (closed loop)

### STEP (`<pe0_filename>.step`)
- **구성**: blade1 + blade2 + hub fuse → 단일 solid
- **blade1**: root airfoil(0.01R) → aerodynamic stations(eta_trans×R~R) loft by ThruSections
- **blade2**: blade1의 +X축 180° 회전 복사본
- **hub**: 원기둥 (반지름 0.1R, xmin→xmax of station_root, +X 방향)
- 검증: BRepCheck_Analyzer Valid=True

---

## Implementation Details

### Files
| 파일 | 설명 |
|------|------|
| `prop_gen.py` | 메인 기하 생성 로직 (APCPropellerGeometry class) |
| `web_viewer.py` | 웹 기반 3D propeller inspector (Flask + Plotly) |
| `SKILL.md` | 이 파일 |
| `data/` | PE0 원본 데이터 파일 (*.PE0) |
| `geom/` | 생성된 CSV 및 STEP 결과 파일 |

### Key Dependencies
- **OCP (OpenCASCADE)**: `BRepOffsetAPI_ThruSections` (loft), `BRepAlgoAPI_Fuse`, `STEPControl_Writer`, `ShapeFix_Shape`, `BRepCheck_Analyzer`
- **cadquery**: `cq.Vector`, `cq.Edge`, `cq.Wire` (wire 생성용)
- **numpy**: 배열 연산
- **pandas**: 데이터 파싱 및 CSV 저장
- **re**: PE0 헤더/테이블 파싱

### CLI Usage
```bash
# venv 활성화
source skills/apc-prop-geom/venv/bin/activate

# 프로펠러 생성 (기본 output: geom/ 디렉토리)
python skills/apc-prop-geom/prop_gen.py 7x5

# output directory 지정 가능
python skills/apc-prop-geom/prop_gen.py 10x4M-LH --output /path/to/output/
```

### Class API
```python
from skills.apc-prop-geom.prop_gen import APCPropellerGeometry

geom = APCPropellerGeometry(data_dir="skills/apc-prop-geom/data")

# 1. Generate geometry (station0 Y 원본, eta_start=0, 전체 aerodynamic)
df_aero, df_all, df_root, filename, metadata = geom.generate_geometry("10x4M-LH")

# 2. Save outputs (기본: geom/ 디렉토리)
csv_path = geom.save_to_csv(df_aero, filename)
# → geom/10x4M-LH-PERF.csv

step_path = geom.save_to_step(df_aero, df_all, df_root, filename, R, metadata)
# → geom/10x4M-LH-PERF.step

# output_dir override 가능
csv_path = geom.save_to_csv(df_aero, filename, output_dir="/custom/path/")
```

### CLI Parameters
- `prop_name`: "DiameterxPitch" 형식 (예: "7x5", "10x4M-LH")
- `--output, -o`: 출력 디렉토리 (기본값: `geom/` 디렉토리)
- `generate_geometry()`: `eta_start_override`, `is_lh`(True=LH) 파라미터 지원

### Important Implementation Notes
- **BRepOffsetAPI_ThruSections** 사용: `cq.Solid.makeLoft`는 50+ station에서 메모리 과부하(SIGKILL) 발생
- **wire.wrapped** 필요: ThruSections.AddWire()는 OCC TopoDS_Wire만 받음
- **Root Z 스케일링**: root airfoil Z span을 hub_diameter에 맞게 스케일 → hub와 geometry match
  - `z_scale = hub_diameter / root_z_span`
- **Y=0부터 loft**: station0 Y=STATION[0] 그대로 (재매핑 없음)
  - blade1 root Y = +root_y, blade2 root Y = -root_y (180° 회전)
  - hub cylinder Y_center = 0 (두 blade root의正中)
- **Hub cylinder 높이**: root airfoil X extent vs station_1 airfoil X extent → 더 큰 쪽 사용
  - root extent가 극히 얕은 경우(예: 28x20-4, ≈0.07mm) station_1(≈31mm)으로 자동 fallback
  - 두 airfoil의 X extent를 비교하여 hub cylinder 높이를 결정
- **HUBTRA 무시**: aerodynamic region filtering에 eta_trans 안 사용 (eta_start=0 전체 영역)
- **HUBTRA 무시**: aerodynamic region filtering에 eta_trans 안 사용 (eta_start=0 전체 영역)
- **fuse 순서**: blade1 + blade2 먼저 → 결과 + hub 나중에 (한 번에 하나씩)
- **output filename**: `<pe_name>.step`, `<pe_name>.csv`
- **`save_to_step` signature**: `metadata` 파라미터 추가 필요 (`hub_radius` 접근용)

---

## Web 3D Viewer (web_viewer.py)

Dash + Plotly 기반 웹 3D propeller geometry inspector.

### Usage
```bash
# venv 활성화 후 실행
source skills/apc-prop-geom/venv/bin/activate
python skills/apc-prop-geom/web_viewer.py
```
Server runs on `http://0.0.0.0:8054`

### Features
- **Drag & drop file upload**: STEP / CSV 파일 드래그 앤 드롭
- **STEP 로드**: `cadquery` tessellation (`tol=1e-4`) → `trimesh` mesh extraction
  - **Auto unit detection**: bbox diagonal > 100 → mm로 간주하여 m로 변환
  - **Double-sided mesh**: reverse face winding으로 양면 렌더링 (한 면만 보이는 문제 해결)
- **3D rendering**:
  - `go.Mesh3d` 단일 색 (rgb(180,180,180)), flatshading=False, opacity=1.0
  - **aspectmode=cube**: X/Y/Z 동일 range (bbox span 기준) — 축 비율 정확
  - **origin(0,0,0) 기준 축 화살표**: X=red, Y=green, Z=blue (길이 = 5% × max_range)
  - 카메라 위치: eye(1.5, 1.5, 1) — 3/4 측면 각도
- **CSV 로드**: airfoil sections 색상 구분 (r/R 기반 gradient)
- **Left panel**: 파일명, 메타정보 (Surface Area, BBox, CG, Watertight), 로드 상태
- **No sliders, no slice**: 단순 3D 뷰어만

### Layout
- **좌측 패널 (25%)**: 파일 드롭 영역, 파일명, STEP/CSV 메타정보, 로드 상태 메시지
- **우측 (75%)**: Plotly 3D viewer (rotate, zoom, pan 가능)

### Key Implementation Details
- **tessellation**: `val.tessellate(1e-4)` — 고밀도 mesh (tol 낮을수록 정밀)
- **double-sided**: vertex/face 배열 복사 → reverse winding faces 추가
  ```python
  verts2 = mesh.vertices.copy()
  faces2 = mesh.faces.copy()
  faces2[:, 1] = mesh.faces[:, 2]
  faces2[:, 2] = mesh.faces[:, 1]
  offset = len(verts2)
  mesh_double = trimesh.Trimesh(
      vertices=np.vstack([verts2, verts2]),
      faces=np.vstack([faces2, mesh.faces + offset]),
      process=False,
  )
  ```
- **axis range**: `aspectmode=cube` — 모든 축 동일한 range (bbox span 최대값 × 1.5)
  ```python
  s = max(span_y*0.5, dx*0.5, dz*0.5) * 1.5  # range half-width
  # 각 축: [center - s, center + s]
  ```
- **axis arrows**: origin(0,0,0) 기준 `go.Scatter3d` lines
  ```python
  axis_len = max(dx, dy, dz) * 0.05  # 5% of max range
  traces.append(go.Scatter3d(x=[0, axis_len], y=[0, 0], z=[0, 0],
      mode='lines', line={'color': 'red', 'width': 4}, showlegend=False))
  ```
- **mesh trace**: `go.Mesh3d` single solid, single color
  ```python
  go.Mesh3d(x=v_all[:,0], y=v_all[:,1], z=v_all[:,2],
      i=f_all[:,0], j=f_all[:,1], k=f_all[:,2],
      color='rgb(180,180,180)', flatshading=False, opacity=1.0,
      hoverinfo='skip', showlegend=False)
  ```

### Dependencies
- `cadquery` (OCP), `trimesh`, `plotly`, `dash`, `numpy`, `pandas`

### Input
- **STEP**: `geom/<filename>.step` (prop_gen.py 생성)
- **CSV**: `geom/<filename>.csv` (prop_gen.py 생성, 컬럼: station_idx, r_over_R, X, Y, Z)
- **Upload**: drag & drop 또는 click to browse

### Output
- Browser 3D visualization with axis arrows and metadata

---

## Change Log

### 2026-08-15 - Hub Cylinder Height Fallback + Output Directory Update
- **hub cylinder 높이 fallback 추가**: root airfoil X extent vs station_1 airfoil X extent → 더 큰(넓은) 쪽 사용
  - root extent가 극히 얕은 경우(예: 28x20-4, ≈0.07mm) station_1(≈31mm)으로 자동 선택
  - 두 airfoil의 X extent를 직접 비교하여 hub cylinder 높来决定
- **output_dir 기본값 변경**: 스킬 디렉토리 → `geom/` 디렉토리
  - `save_to_csv()`, `save_to_step()` 모두 기본 output을 `geom/`으로
  - `--output` CLI parameter로 override 가능
- **hub cylinder Y_center 명확화**: `0.0` (blade1 root Y = +root_y, blade2 root Y = -root_y正中)
- **SKILL.md의 hub cylinder xmin/xmax 설명**: root airfoil → root vs station_1 extent 비교로 변경
- **7x5, 12x6, 18x8, 28x20-4 재생성 완료**: geom/ 디렉토리에 저장

### 2026-08-14 - Final Stable Version (Corrected)
- **Station Y = STATION[0] 그대로 사용**: station0 재매핑 제거 — Y=0에서 Y=R까지 loft
- **HUBTRA 무시**: hub cylinder radius = HUBRAD 직접 사용 (0.1R 아님)
- **Root Z 스케일링 유지**: root airfoil Z span을 hub_diameter에 맞게 스케일 (튀어나는 것 방지)
- **Blade2 +X 180° 회전**: 두 블레이드 맞닿음
- **eta_start 기본값 0.0**: 전체 station 영역 aerodynamic으로 사용
- **`save_to_step` signature 변경**: `metadata` 파라미터 추가 (hub_radius 접근용)
- **7x5 테스트**: Valid=True, Volume=4.63e-06 m³ ✅
- **18x8 테스트**: Valid=True, Volume=7.06e-05 m³ ✅
- Coordinate system: +X=shaft, +Y=span, +Z=chord
- Airfoil: CLARK-Y from UIUC actual coordinates
- Unit conversion: inch → meter applied at parsing stage
- Airfoil scaling: `scale_factor = t_ratio / 0.117`
- PE0 THICKNESS RATIO overrides CLARK-Y default 11.7%
- L/R skew_sign for LH/RH propellers
