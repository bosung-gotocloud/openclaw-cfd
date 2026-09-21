# simpleFoam 스킬 — 풀어서 쓰는 요약

---

## 1. 이 스킬은 무언가?

simpleFoam 스킬은 **OpenFOAM의 정상해석(steady-state) 솔버**를 자동 실행하는 도구입니다. STL 또는 STEP에서 생성한 메쉬가 완성된 케이스에서 simpleFoam을 돌려 **Cd(항력계수), Cl(양력계수), Cm(모멘트계수)** 등을 계산합니다.

메쉬를 생성하려면 salome-snappy나 snappyMesh 스킬을 먼저 쓰고, 메쉬가 완성된 후에 해석만 돌리려면 이 스킬을 씁니다.

---

## 2. 워크플로우 — 5단계

### 2-1. 스크립트 복사

현재 작업 디렉토리에 두 스크립트를 복사합니다:

```bash
cp skills/simpleFoam/scripts/calculate_solve_params.py .
cp skills/simpleFoam/scripts/run_simpleFoam.py .
```

이 스크립트들이 모든 계산과 실행의 핵심입니다.

### 2-2. 파라미터 계산

입력 JSON 파일을 만들어 파라미터를 계산합니다:

```bash
python3 calculate_solve_params.py input.json
```

**입력 JSON에 넣는 값들:**

| 항목 | 설명 | default |
|------|------|------|
| `mesh_path` | 메쉬가 있는 곳 (`constant/polyMesh`) | — |
| `output_dir` | 실행할 디렉토리 | — |
| `flow.Uinf` | 자유류 속도 (m/s) | 10 |
| `flow.AoA` | 공격각 (degree) | 0 |
| `flow.AoS` | 병진각 (degree) | 0 |
| `fluid.rho` | 공기 밀도 (kg/m³) | 1.225 |
| `fluid.nu` | 동점성계수 (m²/s) | 1.5e-5 |
| `turbulence.model` | 난류 모형 | kOmegaSST |
| `turbulence.intensity` | 난류 강도 (소수, 1%=0.01) | 0.01 |
| `turbulence.viscosityRatio` | 점성비 (μt/ν) | 10 |
| `turbulence.lengthScale` | 혼합 길이 scale (m) | 1.0 |
| `reference.L_ref` | 특성 길이 (m) | 1.0 |
| `reference.A_ref` | 특성 면적 (m²) | 1.0 |
| `CofR_x/y/z` | 기준점 좌표 (m) | 0, 0, 0 |
| `run.endTime` | 해석 시간 | 1000 |
| `run.deltaT` | 시간간격 | 1 |
| `run.writeInterval` | 출력간격 | 100 |

### 2-3. 계산된 파라미터 확인 및 승인

`calculate_solve_params.py`가 `<input>_solve_params.json`을 생성합니다. 계산된 값들을 **표로 보여드리고 승인**을 받아야 합니다. 승인 없이 해석을 절대 돌리지 않습니다.

**주요 계산 결과:**
- `Uvec`: Ux, Uy, Uz (AoA/AoS에서 변환된 속도 벡터)
- `k_ini`: 난류 운동에너지 초기값
- `omega_ini`: 난류 주파수 초기값
- `nu`, `rho`: 유동 조건
- `k`, `omega` 경계조건 값들

### 2-4. 해석 실행

승인 후 `run_simpleFoam.py`를 돌립니다:

```bash
python3 run_simpleFoam.py input_solve_params.json case_name 4
```

넷째 인자(4)는 parallel 코어 수입니다. 생략하면 serial로 돌립니다.

**run_simpleFoam.py가 하는 일 (자동으로):**
1. template 디렉토리를 복사
2. 플레이스홀더(`@Uvec@`, `@kIni@` 등)를 실제 값으로 치환
3. `case.foam` 빈 파일 생성 (메쉬 위치 인식용)
4. simpleFoam 실행 (parallel 시 decomposePar → mpirun → reconstructPar)
5. 에러 발생 시 로그 표시

### 2-5. 결과 확인

해석 완료 후 결과를 확인합니다:

- `case/0/postProcessing/forceCoeffs1/` → Cd, Cl, Cm (계수)
- `case/0/postProcessing/forces1/` → Cd, Cl, Cm (힘/모멘트)
- `case/0/` → 최종 유동장 (p, U, k, omega 등)

---

## 3. 발산 방지 10항목

simpleFoam 해석에서 가장 중요한 것이 **발산(divergence) 방지**입니다. MQ9-Reaper 100m/s 해석으로 모두 검증 완료했습니다.

### 3-1. turbulenceProperties — omegaMin

kOmegaSST 모델에서 omega가 음수로 떨어지면 발산합니다. `omegaMin 1e-10`으로 음수 하한을 지정합니다:

```
RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
    omegaMin        1e-10;
}
```

### 3-2. RASModel 고정

`RASModel`을 `kOmegaSST`로 고정했습니다. 플레이스홀더로 두면 실수할 수 있어서입니다.

### 3-3. 0/U far boundary — freestreamVelocity

유입면(far boundary)에서 `freestreamVelocity` 타입을 씁니다. 자유류 속도를 그대로 유입조건으로 지정합니다:

```
far {
    type            freestreamVelocity;
    freestreamValue uniform @Uvec@;
    value           uniform @Uvec@;
}
```

### 3-4. 0/p far boundary — freestreamPressure

압력의 유입면에서 `freestreamPressure`를 씁니다. 내부장과 동일한 초기값을 사용하고, 경계에서 특별한 조건 없이 유동이 자연스럽게 유입되게 합니다:

```
far {
    type            freestreamPressure;
    freestreamValue $internalField;
    value           $internalField;
}
```

### 3-5. 0/k — 벽면에 kqRWallFunction

벽면에서 난류 운동에너지 k는 0에 가까워야 합니다. `kqRWallFunction`이 벽 근처의 k를 물리적으로 계산합니다:

```
far {
    type            freestream;
    freestreamValue @kIni@;
    value           @kIni@;
}

@surfaceName@ {
    type            kqRWallFunction;
    value           uniform 1e-11;
}
```

- `far`: 자유류에서 k_ini로 초기화
- `surface`(벽): kqRWallFunction, wall value는 1e-11 (거의 0)

### 3-6. 0/omega — 벽면에 omegaWallFunction

벽면에서 난류 주파수 omega는 매우 높아야 합니다. `omegaWallFunction`이 벽 근처의 omega를 계산합니다:

```
far {
    type            freestream;
    freestreamValue @omegaIni@;
    value           @omegaIni@;
}

@surfaceName@ {
    type            omegaWallFunction;
    value           uniform 1e8;
}
```

- `far`: 자유류에서 omega_ini로 초기화
- `surface`(벽): omegaWallFunction, wall value는 1e8

### 3-7. 난류 초기값 계산식

**k (Turbulent Kinetic Energy):**
```
k = 1.5 × (I × Uinf)²
```
I는 난류 강도입니다. 1%이면 I=0.01. Uinf가 10 m/s이면:
```
k = 1.5 × (0.01 × 10)² = 1.5 × 0.01 = 0.15
```

**omega (Turbulent Frequency):**
```
ω = √k / (Cμ⁰·²⁵ × L)
```
- Cμ = 0.09 (kOmegaSST 고정 상수)
- L = mixing length = 0.07 × L_scale (L_scale = 1.0 고정 → L = 0.07m)

```
ω = √0.15 / (0.09⁰·²⁵ × 0.07)
  = 0.387 / (0.523 × 0.07)
  ≈ 10.58
```

### 3-8. fvSchemes — 제한적 limiter

메쉬가 완벽하지 않으면(비직교성, skewness가 있으면) 오차가 증폭됩니다. 이를 억제하기 위해 limiter를 강력하게 설정합니다:

**Gradient:**
```
gradSchemes
{
    default         cellMDLimited Gauss linear 0.5;
    grad(U)         cellMDLimited Gauss linear 1.0;
    grad(p)         cellMDLimited Gauss linear 1.0;
}
```
`cellMDLimited`는 다차원 제한자로 방향성 오차를 잘 제어합니다.

**Divergence:**
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
발산항은 **upwind**(1차 정확도)로 수렴성을 확보합니다. bounded 옵션이 필수.

**Laplacian:**
```
laplacianSchemes
{
    default         Gauss linear limited 0.333;
}
```
limited 계수 0.333으로 제한합니다. 너무 낮으면 정확도 나쁘고, 너무 높으면 발산합니다.

### 3-9. fvSolution — relaxationFactors + solver 설정

**Under-Relaxation Factors (URF):**
과도한 dampening은 오히려 발산의 원인이 됩니다. myShahed 케이스에서 검증된 값:

```
relaxationFactors
{
    fields
    {
        p   0.3;
    }
    equations
    {
        U     0.7;
        k     0.5;
        omega 0.5;
    }
}
```
- p: 0.3 (압력 — 가장 강력하게 dampening)
- U: 0.7 (속도 — 덜 dampening)
- k, omega: 0.5 (난류 변수 — 중간)

**nNonOrthogonalCorrectors:**
메쉬 quality가 좋으면(non-ortho avg ~16°) 3으로 충분합니다:

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

**p solver — GAMG:**
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

### 3-10. forceCoeffs — CofR 플레이스홀더

`forceCoeffs` 함수물에서 기준점(Center of Rotation, CofR)을 반드시 지정해야 합니다:

```
CofR (@CofRx@ @CofRy@ @CofRz@);
```

JSON의 CofR_x, CofR_y, CofR_z가 이 위치에 자동으로 치환됩니다.

---

## 4. 템플릿 파일 구조

```
assets/simpleFoam-case-template/
│
├── 0/                          ← 초기장 파일들
│   ├── p                       ← 압력 (freestreamPressure)
│   ├── U                       ← 속도 (freestreamVelocity)
│   ├── k                       ← 난류 KE (freestream + kqRWallFunction)
│   ├── omega                   ← 난류 freq (freestream + omegaWallFunction)
│   └── nut                     ← 난류 점성 (freestream + nutUSpalding)
│
├── constant/                   ← 상수 파일들
│   ├── transportProperties     ← 뉴토늄 유체, nu
│   └── turbulenceProperties  ← kOmegaSST, omegaMin
│
└── system/                     ← 해석 설정
    ├── controlDict             ← simpleFoam, 시간 설정
    ├── fvSchemes               ← 이산화 방식 (limited)
    ├── fvSolution              ← 솔버 + relaxation
    ├── decomposeParDict        ← scotch 병렬 분해
    └── forceCoeffs             ← Cd/Cl/Cm 계산 설정
```

### template의 플레이스홀더

template 파일에 `@이름@` 형식으로 플레이스홀더가 있습니다. run_simpleFoam.py가 JSON 값을 자동으로 치환합니다:

| 플레이스홀더 | 치환 값 |
|------|------|
| `@Uvec@` | [Ux, Uy, Uz] 속도 벡터 |
| `@kIni@` | 계산된 k_ini |
| `@omegaIni@` | 계산된 omega_ini |
| `@nu@` | 동점성계수 |
| `@rho@` | 밀도 |
| `@surfaceName@` | 표면 패치 이름 |
| `@CofRx/Y/Z@` | CofR 좌표 |
| `@endTime@`, `@deltaT@`, `@writeInterval@` | 해석 시간 설정 |
| `@lRef@`, `@Aref@`, `@rhoInf@` | forceCoeffs 참조 값 |

---

## 5. 결과 파일

### forceCoeffs1 (계수)
```
case/0/postProcessing/forceCoeffs1/forceCoeffs.dat
```

시간별 Cd, Cl, Cm 출력. 파일 헤더에 기준값(L_ref, A_ref, CofR 등)이 기록됩니다.

### forces1 (힘/모멘트)
```
case/0/postProcessing/forces1/forces.dat
```

Cd, Cl, Cm에 더하여 raw 힘(Fx, Fy, Fz)과 모멘트(Mx, My, Mz) 출력.

### 유동장
```
case/0/
├── p      ← 압력장
├── U      ← 속도장
├── k      ← 난류 KE
├── omega  ← 난류 주파수
└── nut    ← 난류 점성계수
```

Post-processing로 시각화 가능합니다.

---

## 6. 실행 규칙 — 반드시 지켜야 할 것

### 규칙 1: 원본 수정 금지
skills/simpleFoam 디렉토리의 원본 파일을 절대 수정하지 않습니다. 모든 작업은 복사한 스크립트에서 합니다.

### 규칙 2: 파라미터 확인 및 승인 필수
`calculate_solve_params.py`로 계산한 파라미터를 표로 보여드리고, 박사님의 **명시적 승인**을 받아야 해석을 돌립니다. 승인 없이 실행하면 안 됩니다.

### 규칙 3: 에러 처리
해석 중 에러가 발생하면 로그를 그대로 표시합니다. 자동 재시도나 자동 파라미터 수정은 하지 않습니다.

### 규칙 4: parallel 실행
```bash
python3 run_simpleFoam.py case_name 8
```
넷째 인자로 코어 수를 지정합니다. oversubscribe 옵션이 자동 포함됩니다.

---

## 7. 입출력 JSON 스키마

### 입력 JSON (예시)
```json
{
  "mesh_path": "/home/bosung/case/constant/polyMesh",
  "output_dir": "/home/bosung/case",
  "boundary": {
    "patch": ["far", "surface"],
    "far_BC": "freestream",
    "surface_BC": "wall"
  },
  "flow": {
    "Uinf": 41.667,
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

### 출력 JSON (계산 결과)
```json
{
  "Uvec": [41.667, 0.0, 0.0],
  "k_ini": 0.15,
  "omega_ini": 10.58,
  "nu": 1.5e-5,
  "rho": 1.225,
  "reynolds": 625000.0,
  "dt": 1,
  "endTime": 1000,
  "writeInterval": 100
}
```

---

## 8. 디렉토리 구조

```
skills/simpleFoam/
├── SKILL.md                    ← 원본 스킬 문서
├── SKILL_SUMMARY.md            ← 이 파일 (풀어서 쓰는 요약)
├── assets/
│   └── simpleFoam-case-template/
│       ├── 0/                  ← 초기장 template
│       ├── constant/           ← 상수 template
│       └── system/             ← 해석설정 template
└── scripts/
    ├── calculate_solve_params.py  ← 파라미터 계산
    └── run_simpleFoam.py          ← 해석 실행
```

---

## 9. 간단한 플로우 차트

```
사용자가 메쉬 경로 + 유동 조건 제공
        │
        ▼
calculate_solve_params.py 실행
        │
        ▼
파라미터 표로 보여줌 + 승인 요청  ← 박사님 승인 필요!
        │ (승인)
        ▼
run_simpleFoam.py 실행
        │
        ├── template 복사 + placeholder 치환
        ├── case.foam 생성
        ├── decomposePar (parallel 시)
        ├── mpirun simpleFoam -parallel
        ├── reconstructPar (parallel 시)
        └── 해석 완료
        │
        ▼
forceCoeffs → Cd, Cl, Cm 확인
```
