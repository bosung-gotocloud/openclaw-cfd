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
k = 1.5 * (I * Uinf)^2
```
- I = turbulence intensity (소수 기반, e.g., 0.01 → 1%)
- DEFAULTS.turbulence.intensity = 0.01 (1%)

**omega (Turbulent frequency):**
```
omega = sqrt(k) / (Cmu^0.25 * L)
```
- L = mixing length = 1.0e-5
- Cmu = 0.09

### 8. fvSolution — k, omega solver + residualControl

**solver entries:**
```
k {
    solver          smoothSolver;
    smoother        GaussSeidel;
    nSweeps         2;
    tolerance       1e-08;
    relTol          0.1;
}

omega {
    solver          smoothSolver;
    smoother        GaussSeidel;
    nSweeps         2;
    tolerance       1e-08;
    relTol          0.1;
}
```

**residualControl:**
```
SIMPLE {
    residualControl {
        p       1e-5;
        U       1e-5;
        k       1e-5;
        omega   1e-5;
    }
}
```

**relaxationFactors:**
```
relaxationFactors {
    fields { p 0.3; }
    equations {
        U       0.7;
        k       0.6;
        omega   0.6;
    }
}
```

### 9. fvSchemes — kOmegaSST용

```
divSchemes {
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      Gauss upwind;
    div(phi,omega)  Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
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
5. 에러 발생 시 로그 표시
```

### 실행 규칙
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
k = 1.5 * (I * Uinf)^2
omega = sqrt(k) / (Cmu^0.25 * L)   (L=1.0e-5, Cmu=0.09)
```

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
| `0/k` | freestream / kqRWallFunction |
| `0/omega` | freestream / omegaWallFunction |
| `0/nut` | freestream / nutUSpalding |
| `constant/turbulenceProperties` | kOmegaSST (omegaMin=1e-10) |
| `constant/transportProperties` | Newtonian, nu placeholder |
| `system/controlDict` | simpleFoam, time |
| `system/fvSchemes` | kOmegaSST pre-configured |
| `system/fvSolution` | GAMG p, smoothSolver U/k/omega |
| `system/decomposeParDict` | scotch |
| `system/forceCoeffs` | Cd/Cl/Cm + forces |

### scripts/
| 파일 | 설명 |
|------|------|
| `calculate_solve_params.py` | 파라미터 계산 + JSON 생성 |
| `run_simpleFoam.py` | template 복사 → placeholder → 실행 |
