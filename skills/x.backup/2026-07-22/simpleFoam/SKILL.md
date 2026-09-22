---
name: simpleFoam
description: OpenFOAM steady-state (simpleFoam) solver. Run CFD simulations on mesh-complete cases with kOmegaSST turbulence model.
---

# simpleFoam - 정류 해석 스킬

OpenFOAM 정류수 해석. STL/STEP 메쉬 기반 mesh completed case에서 simpleFoam으로 steady-state 해석.

## 선택 규칙
- **해석만 필요** → 이 스킬
- **메쉬 + 해석** → salome-snappy / snappyMesh 스킬

---

## 발산 방지 설정 (2026-07-12 검증 완료)

MQ9-Reaper 100m/s 해석으로 **모든 발산 문제 해결 검증 완료**.

### 1. turbulenceProperties — omegaMin 추가

kOmegaSST에서 omega 음수 방지:

```
RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
    omegaMin        1e-10;
}
```

### 2. turbulenceProperties — RASModel 고정

`RASModel`을 `kOmegaSST`로 고정 (`@turbModel@` 플레이스홀더 제거)

### 3. 0/U — far boundary: freestreamVelocity

```
far {
    type            freestreamVelocity;
    freestreamValue uniform @Uvec@;
    value           uniform @Uvec@;
}
```

### 4. 0/p — far boundary: freestreamPressure

```
far {
    type            freestreamPressure;
    freestreamValue $internalField;
    value           $internalField;
}
```

### 5. 0/k — wall: kqRWallFunction

```
@surfaceName@ {
    type            kqRWallFunction;
    value           uniform 1e-11;
}
far {
    type            freestream;
    freestreamValue @kIni@;
    value           @kIni@;
}
```

### 6. 0/omega — wall: omegaWallFunction

```
@surfaceName@ {
    type            omegaWallFunction;
    value           uniform 1e8;
}
far {
    type            freestream;
    freestreamValue @omegaIni@;
    value           @omegaIni@;
}
```

### 7. k/omega 초기값 계산식

**k (Turbulent KE):**
```
k = 1.5 × (I × Uinf)²
```
- I = turbulence intensity (소수 기반, e.g., 0.01 → 1%)
- DEFAULTS.turbulence.intensity = 0.01 (1%)
- `calculate_solve_params.py`의 `calculate_k()` 함수 구현:
  ```python
  def calculate_k(Uinf, I):
      return 1.5 * (I * Uinf) ** 2
  ```

**omega (Turbulent frequency):**
```
omega = √k / (Cμ^0.25 × L)
```
- L = **1.0 m** (reference length, hisa 스킬과 동일)
- Cμ = 0.09
- `calculate_solve_params.py`의 `calculate_omega()` 함수 구현:
  ```python
  def calculate_omega(k, L_ref):
      Cmu = 0.09
      return math.sqrt(k) / ((Cmu ** 0.25) * L_ref)
  ```
- main()에서:
  ```python
  omega_ini = calculate_omega(k_ini, L_ref)  # L_ref=1.0 m
  ```

### 8. fvSchemes — Limiting 및 안정화 (Skewness/Non-orthogonality 대응)

Mesh의 Skewness가 존재하면 Gradient와 Laplacian 항에서 오차가 증폭됩니다. 강력한 Limiter로 해의 튀는 현상을 억제.

**Gradient Schemes:**
비직교성이 높은 격자에서는 cellMDLimited가 방향성 오차 제어에 유리.
```
gradSchemes
{
    default         cellMDLimited Gauss linear 0.5;
    grad(U)         cellMDLimited Gauss linear 1.0;
    grad(p)         cellMDLimited Gauss linear 1.0;
}
```

**Divergence Schemes:**
발산이 심할 때 1차 upwind로 수렴성 확보 → linearUpwind 전환 전략. Bounding 옵션 필수.
```
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))) )) Gauss linear;
}
```

**Laplacian Schemes:**
Skewness/Non-orthogonality가 발산의 핵심. limited 계수를 낮춰 안정성 확보.
```
laplacianSchemes
{
    default         Gauss linear limited 0.333;
}
```

### 9. fvSolution — relaxationFactors + nNonOrthogonalCorrectors

**Under-Relaxation Factors (URF):**
발산 방지 검증 완료. 이 값으로 안정적 해석.
```
relaxationFactors
{
    fields
    {
        p               0.2;
    }
    equations
    {
        U               0.5;
        k               0.3;
        omega           0.3;
    }
}
```

**nNonOrthogonalCorrectors:**
비직교 격자에서 압력 방정식 충분히 보정. 2로 하면 발산하므로 3 필수.
```
SIMPLE
{
    nNonOrthogonalCorrectors 3;
    residualControl
    {
        p       1e-5;
        U       1e-5;
        k       1e-5;
        omega   1e-5;
    }
}
```

**p solver (GAMG):**
```
p {
    solver              GAMG;
    tolerance           1e-06;
    relTol              0.1;
    smoother            GaussSeidel;
    maxIter             1000;
    cacheAgglomeration  on;
    aggregator          subsets;
    nCellsInCoarsestSub 5000;
}
```
### 10. forceCoeffs — CofR 플레이스홀더

```
CofR (@CofRx@ @CofRy@ @CofRz@);
```

run_simpleFoam.py에서 `@CofRx@`, `@CofRy@`, `@CofRz@` 치환.

### 11. case.foam 생성

template + mesh 복사 후 빈 파일 생성 (메쉬 위치 인식용)

---

## template — 0/k 상세

```
/*----------------------------------------------...--- C++ -...---...----------------*\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  v2512                                 |
|   \\  /    A nd           | Website:  www.openfoam.com                      |
|    \\/     M anipulation  |                                                 |
\*------...-...-...--...-...-...------...-...-...--...-----...-...--...-...-...*/

FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      k;
}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform @kIni@;

boundaryField
{
    far
    {
        type            freestream;
        freestreamValue uniform @kIni@;
        value           uniform @kIni@;
    }

    @surfaceName@
    {
        type            kqRWallFunction;
        value           uniform 1e-11;
    }
}
```

- **far**: freestream (유입부 — 자유류 조건)
- **surface (wall)**: kqRWallFunction (벽면 함수 — 벽 근처 k 계산)
- **internalField**: `@kIni@` 치환 → `calculate_k(Uinf, I)` 결과
- **wall value**: `uniform 1e-11` (벽면에서 k ≈ 0)

## template — 0/omega 상세

```
/*----------------------------------------------...--- C++ -...---...----------------*\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  v2512                                 |
|   \\  /    A nd           | Website:  www.openfoam.com                      |
|    \\/     M anipulation  |                                                 |
\*------...-...-...--...-...-...------...-...-...--...-----...-...--...-...-...*/

FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      omega;
}

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform @omegaIni@;

boundaryField
{
    far
    {
        type            freestream;
        freestreamValue uniform @omegaIni@;
        value           uniform @omegaIni@;
    }

    @surfaceName@
    {
        type            omegaWallFunction;
        value           uniform 1e8;
    }
}
```

- **far**: freestream (유입부 — 자유류 조건)
- **surface (wall)**: omegaWallFunction (벽면 함수 — 벽 근처 omega 계산)
- **internalField**: `@omegaIni@` 치환 → `calculate_omega(k_ini, 1.0e-5)` 결과
- **wall value**: `uniform 1e8` (벽면에서 높은 omega — 벽 근처 회전율 증가)

---

## Workflow

### 필수 파라미터 (사용자 제공)
- `mesh_path` — 메쉬 경로
- `output_dir` — 실행 디렉토리

### Optional 파라미터 (default 자동 적용)
- Uinf=10 m/s, AoA=0°, AoS=0°
- nu=1.5e-5 m²/s, rho=1.225 kg/m³
- turbulence: kOmegaSST, intensity=1%, mu_t/nu=10, lengthScale=Uinf(m)
- L_ref=1.0m, A_ref=1.0m²
- CofR=(0,0,0)
- endTime=1000, deltaT=1, writeInterval=100

### 실행 단계

```
1. 스크립트 복사
2. calculate_solve_params.py 실행 → 파라미터 계산
3. 파라미터 표 + JSON 표시 → 승인
4. 승인 후 run_simpleFoam.py 실행
5. simpleFoam 해석
6. 에러 발생 시 로그 표시
```

---

## 실행 규칙
1. **원본 수정 금지:** 스킬 디렉토리 절대 수정 안 함
2. **파라미터 확인 필수:** 표로 표시 후 승인
3. **에러 처리:** 로그 그대로 표시, 자동 재시도 금지

---

## Parameter Calculation

### Step 1: 스크립트 복사 및 계산

```bash
cp <skill_scripts_path>/calculate_solve_params.py .
cp <skill_scripts_path>/run_simpleFoam.py .
python3 calculate_solve_params.py [input.json]
```

#### 입력 JSON 스키마
```json
{
  "mesh_path": "/path/to/constant/polyMesh",
  "boundary": {
    "patch": ["far", "surface"],
    "far_BC": "freestream",
    "surface_BC": "wall"
  },
  "flow": {
    "Uinf": 10.0,
    "AoA": 0.0,
    "AoS": 0.0
  },
  "fluid": {
    "rho": 1.225,
    "nu": 1.5e-5
  },
  "turbulence": {
    "model": "kOmegaSST",
    "intensity": 0.01,
    "viscosityRatio": 10,
    "lengthScale": 10.0
  },
  "reference": {
    "L_ref": 1.0,
    "A_ref": 1.0
  },
  "CofR": {
    "CofR_x": 0.0,
    "CofR_y": 0.0,
    "CofR_z": 0.0
  },
  "run": {
    "endTime": 1000,
    "deltaT": 1,
    "writeInterval": 100
  }
}
```

#### 계산식

**유동 조건 (AoA/AoS → Ux, Uy, Uz):**
```
Ux = Uinf × cos(AoS) × cos(AoA)
Uy = Uinf × cos(AoS) × sin(AoA)
Uz = Uinf × sin(AoS)
```

**난류 초기값:**
```
k = 1.5 × (I × Uinf)²
omega = √k / (Cμ^0.25 × L)   (L=1.0e-5, Cμ=0.09)
```

- k 계산: `calculate_k(Uinf, I)` → `1.5 * (I * Uinf) ** 2`
- omega 계산: `calculate_omega(k_ini, 1.0e-5)` → `sqrt(k) / (0.09^0.25 * 1.0e-5)`
- **L은 고정 1.0e-5** (mixing length) — JSON의 lengthScale은 turbulence length scale과 혼동하지 않음

#### 출력 파일
`<input>_solve_params.json` (예: `input.json` → `input_solve_params.json`)

### Step 2: 해석 실행

```bash
# 명시적 JSON
python3 run_simpleFoam.py <json> <case_name> [procs]

# JSON omission → auto fallback: solve_params.json → input_solve_params.json → input.json
python3 run_simpleFoam.py <case_name> [procs]
```

### Step 3: 결과

- `case/0/postProcessing/forceCoeffs1/` — Cd, Cl, Cm
- `case/0/postProcessing/forces1/` — raw 힘/모멘트

---

## template 파일 목록

### assets/simpleFoam-case-template/
| 파일 | 설명 |
|------|------|
| `0/U` | freestreamVelocity / noSlip |
| `0/p` | freestreamPressure / zeroGradient |
| `0/k` | freestream / kqRWallFunction, k_ini, wall=1e-11 |
| `0/omega` | freestream / omegaWallFunction, omega_ini, wall=1e8 |
| `0/nut` | freestream / nutUSpalding |
| `constant/turbulenceProperties` | kOmegaSST (omegaMin=1e-10) |
| `constant/transportProperties` | Newtonian, nu placeholder |
| `system/controlDict` | simpleFoam (solve) |
| `system/fvSchemes` | kOmegaSST pre-configured |
| `system/fvSolution` | GAMG p, smoothSolver U/k/omega |
| `system/decomposeParDict` | scotch |
| `system/forceCoeffs` | Cd/Cl/Cm + forces |

### scripts/
| 파일 | 설명 |
|------|------|
| `calculate_solve_params.py` | 파라미터 계산 + JSON 생성 |
| `run_simpleFoam.py` | template 복사 → placeholder → 실행 |
