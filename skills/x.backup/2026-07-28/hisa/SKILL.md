# HiSA Solver Skill

HiSA (High Speed Aerodynamic) 솔버용 OpenFOAM 워크플로우 스킬.

## 선택 규칙
- **HiSA solver**: 고속 공기역학 시뮬레이션 (compressible, kOmegaSST turbulence)
- **simpleFoam과 유사한 파라미터 구조** — `calculate_solve_params.py` → `run_hisa.py`

## 발산 방지 설정
- **kOmegaSST turbulence**: omegaMin 1e-10 포함
- **relaxationFactors**: `k|omega|nuTilda` → 0.5

## 워크플로우

### 1. 파라미터 계산
```bash
python3 calculate_solve_params.py
```
- **L_scale = 1.0** (고정)
- **mandatory**: `mesh_path` (하나만 — 실행 디렉토리는 AI가 대화로 판단해서 output_dir JSON 삽입)
- optional: flow, fluid, thermodynamic, turbulence, run, reference, CofR, boundary
- JSON → 출력 → 표시 → **승인 필수**
- `k`, `omega` 초기값 자동 계산 (kOmegaSST)

### 2. HiSA parallel 실행
```bash
python3 run_hisa.py solve_params.json
```
- JSON 자동 검색: `solve_params.json` (실행 디렉토리 기준)
- 무조건 parallel 실행 (decomposePar → mpirun → reconstructPar → processor* cleanup)
- 로그 파일명: `log.hisa`
- case 폴더 생성 후 `case.foam` 파일 자동 생성

## 워크플로우 규칙
- **스크립트 복사**: 실행 디렉토리(사용자가 말한 곳)에 `calculate_solve_params.py` + `run_hisa.py` 복사
- **output_dir**: 실행 디렉토리 (AI가 대화로 판단)
- **mesh_path**: 메쉬 polyMesh 디렉토리
- **mesh_path와 mesh_dir 통합**: 하나로 합침 (mesh_path만 사용)
- **파라미터 계산 후 승인 필수**: 승인 전에 실행하지 않음

## 파라미터

### calculate_solve_params.py
| 카테고리 | 필드 | 기본값 | 설명 |
|---------|------|-----|-----|
| flow | Uinf | **41.667** (150 km/h) | freestream velocity (m/s) |
| flow | AoA | 0.0 | angle of attack (deg) |
| flow | AoS | 0.0 | angle of sideslip (deg) |
| fluid | rho | 1.225 | density (kg/m3) |
| fluid | nu | 1.5e-5 | kinematic viscosity (m2/s) |
| thermodynamic | T | 293.15 | temperature (K) |
| thermodynamic | pInf | 101325 | freestream pressure (Pa) |
| turbulence | model | kOmegaSST | RAS model |
| turbulence | intensity | 0.01 | turbulence intensity |
| turbulence | viscosityRatio | 10 | mu_t/nu ratio |
| turbulence | lengthScale | **1.0** | length scale (고정) |
| run | endTime | 1000 | simulation time steps |
| run | deltaT | 1 | time step |
| run | writeInterval | 100 | write interval |
| run | pseudoCoNum | **1** | pseudo Courant number (시작값) |
| run | pseudoCoNumMax | **10000** | pseudo Courant number max |
| run | timeScheme | steadyState | time scheme |
| reference | L_ref | 1.0 | reference length (fixed) |
| reference | A_ref | 1.0 | reference area |
| CofR | CofR_x/y/z | 0.0 | center of rotation |

## Template 파일 목록
- `templates/0/U` — velocity (characteristicFarfieldVelocity)
- `templates/0/p` — pressure (characteristicFarfieldPressure)
- `templates/0/T` — temperature (characteristicFarfieldTemperature)
- `templates/0/k` — turbulent kinetic energy
- `templates/0/omega` — specific dissipation rate
- `templates/0/nut` — turbulent viscosity
- `templates/0/alphat` — turbulent thermal diffusivity
- `templates/0/include/freestreamConditions` — freestream include
- `templates/system/controlDict` — simulation control
- `templates/system/fvSchemes` — HiSA 전용 schemes (AUSMPlusUp)
- `templates/system/fvSolution` — flow solver + pseudoTime
- `templates/system/decomposeParDict` — parallel decomposition
- `templates/constant/turbulenceProperties` — RAS settings
- `templates/constant/thermophysicalProperties` — perfect gas
