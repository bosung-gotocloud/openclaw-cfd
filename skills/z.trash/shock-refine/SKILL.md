# shock-refine — Shock-Based Mesh Refinement for HisA CFD Results

## Description

Hisa (압축성 k-omega SST) 해석 결과에서 충격파(shock wave)가 지나는 셀을 감지하고, 해당 셀을 기준으로 메쉬를 세분화(refine)하여 재해석을 준비하는 스킬입니다.

polyMesh 기반 tetrahedral / polyhedral cells 에 적용되며, AMR(Adaptive Mesh Refinement) 방식의 국부 mesh refinement 를 구현합니다.

**핵심 원칙: 원본 case 에는 읽기만 한다 — 쓰지 않고, 삭제하지 않고, 변경하지 않는다.**

## Workflow Overview

```
사용자가 case 디렉토리 제공 (his 해석결과 + polyMesh 포함)
    ↓
shock-sensor.py: 마지막 time step 의 해석결과 + polyMesh 분석 → shock 감지
    ↓
sensor 가 shock 이 지나는 cell ID 목록 반환
    ↓
cell 의 vertex 추출 → STL 작성 (시각화용, caseRoot/refined-case 에만 저장)
    ↓
edge 를 (0.5)^level 로 분할하여 cell 세분화 (level=1,2,3... 기본값 1)
    ↓
polyMesh 재구성 (refined mesh 만 refined-case 에 저장)
    ↓
case_root/refined-case/ 에 hisa 설정 파일 복사 (원본은 건드리지 않음)
    ↓
재해사 준비 완료
```

## Shock Detection Method

### Multi-Criteria Sensor (4-criterion weighted sum)

衝擊波는 압력, 밀도, 속도의 급격한 불연속성을 유발합니다. 이를 4 가지 criterion 으로 포착:

| # | Criterion | Weight | Normalization Threshold | Physics Basis |
|---|-----------|--------|------------------------|---------------|
| 1 | **Normalized pressure gradient** | α = 0.40 | 5.0 | `|∇p| × L_cell / p_ref` — shock 의 가장 직접적인 지표. Shock 는 Δp/p ~ O(1) over < cell size |
| 2 | **Density jump ratio** | β = 0.35 | 0.1 | `Δρ/ρ_avg across faces` — 압축성 shock: density 10-50% 변화 |
| 3 | **Vorticity spike** | γ = 0.15 | 1e3 | `\|∇×U\| magnitude` — shock-induced vorticity (baroclinic torque) |
| 4 | **Isentropic deviation** | δ = 0.10 | 0.5 | `gradient(p/ρ^γ)` — 비가역적 압축 확인 |

### Combined Shock Score

```
S_shock = α·S₁ + β·S₂ + γ·S₃ + δ·S₄
Shock detected where S_shock > threshold (default: 1.0)
```

### Algorithm Details

각 cell 에 대해:

1. **Cell faces 식별**: owner/neighbour array 로 cell 에 속하는 face indices 추출
2. **Cell vertices 추출**: face 의 vertex indices 에서 unique set 구성
3. **Bounding box 계산**: `char_length = max(bbox_max - bbox_min)` — characteristic length 로 사용
4. **Criterion 1: 압력 구배** — 각 face 에서 `(p[neigh] - p[own]) / dist` 의 magnitude 평균 → `dp_norm = avg_grad × char_len / p_ref`
5. **Criterion 2: 밀도 점프** — 각 face 에서 `Δρ/ρ_avg` 의 max 값 → `rho_jump_max`
6. **Criterion 3: 와도 스파이크** — U field 의 velocity gradient magnitude → `curl_U_mag`
7. **Criterion 4: 등엔트로피 편차** — `p/ρ^γ` field 생성, 그라디언트 계산 → `iso_grad_mag`
8. 모든 criterion 을 [0,1] 로 normalize 후 가중 합 → shock score
9. `shock_score > threshold` 인 cell IDs 추출

## Refinement Strategy

### Edge Subdivision by (0.5)^level

```
Level 1: subdivision ratio = 0.5 → 각 cell 이 8 개 sub-cell 로 분할
Level 2: subdivision ratio = 0.25 → 64 개 sub-cell
Level 3: subdivision ratio = 0.125 → 512 개 sub-cell

새로운 셀 수: N_new = N_original + N_shock_cells × ((2^level)^3 - 1)
  - Level 1: 각 shock cell 마다 7 개의 새 cell 추가
  - Level 2: 각 shock cell 마다 63 개의 새 cell 추가
  - Level 3: 각 shock cell 마다 511 개의 새 cell 추가
```

**Subdivision algorithm:**

1. Shock cell 의 bounding box 계산
2. `n_sub = 1 / (0.5^level)` 간격으로 interior vertices 생성
3. Bbox 내에서 structured grid 생성 (`(n_sub+1)^3` points)
4. Structured grid 에서 hexahedral cells 생성 → tetrahedral splitting 적용
5. polyMesh 의 points, cells, faces, owner, neighbour 배열 업데이트
6. Boundary 조건 원본과 동일하게 유지

## File Structure

```
shock-refine/
├── SKILL.md                          # 이 파일
├── README.md                         # 사용 가이드
└── scripts/
    ├── shock-sensor.py               # Shock wave detection (multi-criteria)
    ├── refine-mesh.py                # Edge subdivision mesh refinement
    └── setup-refined-case.py         # Configuration copy to refined-case
```

## Usage

### Step 1: shock-sensor.py 실행 — 읽기 전용

```bash
python3 scripts/shock-sensor.py --case /path/to/hisa-case [--threshold 1.0] [--level 1]
```

- **원본 case 에 아무것도 쓰지 않는다** — 해석결과와 polyMesh 를 **읽기만** 한다
- Latest time directory 의 `p`, `rho`, `U` field 읽음
- `polyMesh/points`, `polyMesh/faces`, `polyMesh/cells`, `polyMesh/owner`, `polyMesh/neighbour` 읽음
- Output: `refined-case/shock_cells.json` + `refined-case/shock_cells.stl` (case_root/refined-case 에만 저장)

### Step 2: refine-mesh.py 실행 — 메쉬 세분화

```bash
python3 scripts/refine-mesh.py \
    --case /path/to/hisa-case \
    --refined-case /path/to/case_root/refined-case \
    --shock-cells shock_cells.json \
    --level 1
```

- Shock cell 들을 `(0.5)^level` 로 edge subdivision
- Refine mesh 만 `refined-case/polyMesh/` 에 작성 (원본 case 는 건드리지 않음)

### Step 3: setup-refined-case.py 실행 — 설정 복사

```bash
python3 scripts/setup-refined-case.py \
    --case /path/to/hisa-case \
    --refined-case /path/to/case_root/refined-case
```

- Original case 에서 hisa 설정 파일 복사 (0/, constant/, system/)
- polyMesh 는 refined mesh 로 교체
- **원본 case 의 파일은 절대 변경하지 않는다**

## Output Structure

```
case_root/
├── original-case/              ← 원본 case (절대 변경 없음)
│   ├── 0/                      ← 초기 field (p, U, rho, k, omega)
│   ├── constant/
│   │   ├── transportProperties
│   │   ├── turbulenceProperties (kOmegaSST)
│   │   └── fvOptions
│   ├── system/
│   │   ├── controlDict
│   │   ├── fvSchemes
│   │   ├── fvSolution
│   │   ├── decomposeParDict
│   │   └── forceCoeffs
│   └── polyMesh/               ← 원본 mesh (절대 변경 없음)
│       ├── points
│       ├── faces
│       ├── cells
│       ├── owner
│       └── neighbour
│
└── refined-case/               ← 세분화된 메쉬 + hisa 설정
    ├── polyMesh/               ← REFINED mesh (새로 생성)
    │   ├── points              ← subdivided vertices 포함
    │   ├── faces               ← 새 face connectivity
    │   ├── cells               ← 새 cell 정의
    │   ├── owner               ← cell ownership
    │   └── neighbour           ← face neighbor 연결
    ├── 0/                      ← 초기 field (원본에서 복사)
    ├── constant/               ← original 에서 복사
    ├── system/                 ← original 에서 복사
    ├── shock_cells.json        ← detection 결과
    └── shock_cells.stl         ← shock 위치 시각화 STL
```

## Key Implementation Notes

### PolyMesh Parsing (비정형 메쉬 대응)

- **faces format**: OpenFOAM variable-length face format (`nVertices v0 v1 ... vn-1`) 지원
- **cells format**: `face_count` + `face_indices` for each cell →tetrahedral/polyhedral 모두 지원
- **Bounding box approximation**: polyhedron volume 는 `bbox_volume × correction_factor` (tet=0.15, poly=0.3) 로 근사
- **ConvexHull**: scipy.spatial.ConvexHull 로 shock cell region 의 STL 생성

### Hisa Compatibility

- kOmegaSST turbulence model → k, omega field interpolation 새 mesh 에 맞게
- Compressible solver → density, temperature field remapping 필요
- Wall function → y+ 값 post-refinement 확인 (벽면 BL cell 은 refine 하지 않아야 함)
- controlDict 의 endTime 은 mesh size 증가에 따라 조정 고려

### Mesh Quality Post-Refinement

- **Skewness**: subdivided cells 의 skewness < 0.85 유지
- **Aspect Ratio**: extreme aspect ratio 방지
- **Orthogonality**: face normal alignment 확인
- **Volume ratio**: 인접 cell volume 비 ≤ 3:1

### Performance

- Large cases: batch processing (`range(0, n_cells, 50)`) 로 성능 최적화
- Level > 3 과용 경고 → excessive cell count 발생 가능
- Cell count estimate: `N_refined = N_original + N_shock × ((2^level)^3 - 1)`

## Dependencies

- **numpy** ≥ 1.21 — array operations, gradients
- **scipy** ≥ 1.7 — ConvexHull (STL output), spatial queries
- Python ≥ 3.8

## Testing

테스트는 사용자가 요청하면 진행. 테스트 후 코드 수정 시:

1. `skills/shock-refine/scripts/` 아래 스크립트만 수정
2. 다시 테스트
3. **원본 case 에는 어떤 파일도 남기지 않고, 삭제하지 않고, 변경하지 않는다**
