# simpleFoam Skill - 진행 상태

## 현재까지 완료
- [x] 스킬 디렉토리 생성: `skills/simpleFoam/scripts/` + `skills/simpleFoam/assets/`
- [x] motorBike template 복사 → 해석 전용으로 정리 (메쉬 생성 관련 파일 제거)
- [x] template 파일 확인 완료
- [x] `0/` 디렉토리 초기장 파일 5개 생성 (U, p, k, omega, nut) — placeholder 기반
- [x] template 파일들 placeholder 교체 완료
  - `controlDict`: time params → placeholder
  - `fvSolution`: solver config (변경 없음, 기본값 사용)
  - `transportProperties`: nu → placeholder
  - `turbulenceProperties`: RASModel → placeholder
  - `forceCoeffs`: patches, magUInf, lRef, Aref → placeholder
- [x] `calculate_solve_params.py` 생성 (Step1: JSON 생성 + 난류 초기값 계산)
- [x] `run_simpleFoam.py` 생성 (Step2: 승인 → template 복사 → placeholder 교체 → simpleFoam 실행)
- [x] `SKILL.md` 작성

## 완료
- [x] 모든 작업 완료 (2026-07-11)

## 최종 확정 파라미터 (2026-07-12)

### 난류 초기값 계산식

**k (Turbulent KE):**
```
k = 1.5 × (I × Uinf)²
```
- I = turbulence intensity (소수 기반, e.g., 0.01 → 1%)
- DEFAULTS.turbulence.intensity = 0.01 (1%)

**omega (Turbulent frequency):**
```
omega = √k / (Cμ^0.25 × L)
```
- L = mixing length = **1.0e-5**
- Cμ = 0.09

### template — 0/k

```
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

### template — 0/omega

```
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

---

## 최종 확정 JSON 스키마
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
    "lengthScale": 0.1
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

## 발산 방지 설정 (2026-07-12 검증 완료)
- MQ9-Reaper 100m/s 해석으로 모든 발산 문제 해결 검증 완료
- **10개 항목**: turbulenceProperties (omegaMin, RASModel 고정), far boundary (freestreamVelocity/Pressure), k/omega boundary (kqRWallFunction/omegaWallFunction), residualControl, relaxationFactors, upwind divSchemes
- L=1.0e-5 사용 (mixing length)

## 완료
- [x] 모든 작업 완료 (2026-07-12)

## boundary patch 변경 필요사항
motorBike template의 `patches`는 `motorBikeGroup`으로 되어 있음 → 
사용자가 제공한 mesh의 far/surface patch명으로 변경해야 함
(해당 patch를 어떻게 매핑할지 결정 필요)
