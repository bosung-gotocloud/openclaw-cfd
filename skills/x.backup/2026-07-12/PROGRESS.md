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

## 최종 확정 JSON 스키마
```json
{
  "mesh_path": "/path/to/constant/polyMesh",

  "boundary": {
    "patch": ["far", "surface"],
    "far_BC": "freeStream",
    "surface_BC": "wall"
  },

  "flow": {
    "Uinf": 10.0,
    "AoA": 0.0,
    "yaw": 0.0,
    "freestreamDirection": "[1 0 0]"
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
    "A_ref": 1.0,
    "rho": 1.225,
    "U": 10.0
  },

  "run": {
    "endTime": 10,
    "deltaT": 0.01,
    "writeInterval": 1
  }
}
```

## template 수정 계획
- `controlDict`: application=simpleFoam (이미 맞음), time params → placeholder
- `fvSchemes`: divSchemes에 freeStream 관련 추가 필요?
- `fvSolution`: pRefCell=0 (기본값 그대로 유지)
- `transportProperties`: nu → placeholder
- `turbulenceProperties`: RASModel → placeholder (kOmegaSST/SA)
- `forceCoeffs`: patches, magUInf, lRef, Aref → placeholder
- `0/`: initial fields → placeholder

## boundary patch 변경 필요사항
motorBike template의 `patches`는 `motorBikeGroup`으로 되어 있음 → 
사용자가 제공한 mesh의 far/surface patch명으로 변경해야 함
(해당 patch를 어떻게 매핑할지 결정 필요)
