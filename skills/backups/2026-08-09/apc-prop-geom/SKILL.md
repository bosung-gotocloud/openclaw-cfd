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
Y_3d = y_span                # +Y: 스팬 방향
Z_3d = z_rot + skew_sign × S_i  # +Z: chord + SWEEP 오프셋
```
LH 프로펠러: `skew_sign = -1.0`, RH: `skew_sign = +1.0`

### 6단계: 허브 트림ming 및 스팬 재매핑
- `eta_i = y_span / R`
- 필터링: `eta_i >= eta_trans`인 영역만 유지
- 선형 재매핑: `u = (y_span - y_min) / (y_max - y_min)`
- `y_remapped = [eta_trans + (1-eta_trans) × u] × R`

### 7단계: 출력
- **CSV**: `(r_over_R, X, Y, Z)` 미터 단위
- **STEP**: cadquery loft로 3D CAD 모델

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
r_over_R,X,Y,Z
```
- `r_over_R`: 무차원 반경 (y_span / R)
- `X`, `Y`, `Z`: 미터(m) 단위 좌표
- 에어포일 outline points (closed loop)

### STEP (`<pe0_filename>.step`)
- `cadquery` loft를 사용한 3D CAD 모델
- 각 station의 에어포일 outline을 spline으로 연결 후 loft
- 단일 블레이드 (rotation 없음)

---

## Implementation Details

### Files
| 파일 | 설명 |
|------|------|
| `prop_gen.py` | 메인 기하 생성 로직 (APCPropellerGeometry class) |
| `SKILL.md` | 이 파일 |
| `data/` | PE0 원본 데이터 파일 (*.PE0) |
| `test/` | 생성된 CSV 및 STEP 결과 파일 |

### Key Dependencies
- `numpy`: 배열 연산
- `cadquery`: STEP CAD export (loft)
- `pandas`: 데이터 파싱 및 CSV 저장
- `re`: PE0 헤더/테이블 파싱

### Class API
```python
geom = APCPropellerGeometry(data_dir="skills/apc-prop-geom/data")

# Generate geometry (single blade)
df, filename, metadata = geom.generate_geometry("10x4M-LH")

# Save outputs
geom.save_to_csv(df, filename)    # skills/apc-prop-geom/test/<filename>.csv
geom.save_to_step(df, filename)   # skills/apc-prop-geom/test/<filename>.step
```

### Parameters
- `prop_name`: "DiameterxPitch" 형식 (예: "10x4M-LH")
- `eta_start_override`: 선택적 스팬 시작점 (기본값: eta_trans)
- `is_lh`: True=좌회전, False=우회전 (skew_sign 결정)

---

## Last Modification
- **2026-08-09**: Final stable version
  - Coordinate system: +X=shaft, +Y=span, +Z=chord
  - Airfoil: CLARK-Y from UIUC actual coordinates (not formula)
  - Unit conversion: inch → meter applied at parsing stage
  - Airfoil scaling: `scale_factor = t_ratio / 0.117`, then `x_airfoil = thick_frac × scale_factor × c_i`
  - PE0 THICKNESS RATIO overrides CLARK-Y's default 11.7% thickness
  - Closed loop: LE/TE 명확히 연결
  - Single blade only (no 180° rotation)
  - Span re-mapping with eta_trans
  - SWEEP → Z offset, RAKE → X offset (absolute values)
