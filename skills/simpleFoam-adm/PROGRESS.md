# simpleFoam-adm 스킬 구축 완료 (2026-08-14)

## 완료 상태
- [x] **STEP 1**: constant/fvOptions 생성 (actuatorDisk ADM source term)
- [x] **STEP 2**: calculate_adm_params.py 스크립트 생성
- [x] **STEP 3**: run_simpleFoam_adm.py 스크립트 생성
- [x] **STEP 4**: SKILL.md 작성 (최종 업데이트)
- [x] **STEP 5**: PROGRESS.md 최종 정리
- [x] **system/topoSetDict 템플릿 생성**: cylinder 기반 cellZone 생성 (OpenFOAM v2512 호환)
- [x] **fvOptions syntax fix**: `regionType` → `selectionMode cellZone` (v2512 필수)
- [x] **topoSetDict syntax fix**: top-level key → `actions (...)` list syntax (v2512 필수)
- [x] **fvOptions 동적 생성**: template → `run_simpleFoam_adm.py`에서 adm_params 기반 생성
- [x] **myShahed-salome-snappy test**: mesh bbox 분석, ADM center(2.5, 0, 0) + radius(0.9144) 적용
- [x] **parallel simpleFoam test**: 16 cores, Time=330까지 정상 수렴 ✅
- [x] **Cp/Ct 양수 보장**: `sink: true`로 설정하여 positive coefficient 유지
- [x] **프로펠러 추력 방향**: Uinf 방향 추력 (Drone/비행기 프로펠러용)

## upstreamPoint & diskDir 자동 계산 (2026-08-14 16:59)
- **upstreamPoint 수정**: disk center → disk upstream side (flow 들어오는 쪽)
  - `upstreamPoint = disk center - diskDir × epsilon`
  - `epsilon = radius × 0.01` (반지름의 1%, disk 바로 바깥)
- **diskDir 자동 계산**: user 수동 입력 → `-normalize(Uinf_vector)`
  - Uinf = Ux, Uy, Uz (AoA, AoS 보정)
  - `diskDir = -normalize(Ux, Uy, Uz)`
- **calculate_adm_params.py**: flow 먼저 입력 → diskDir 자동 계산 → Ct/Cp 조회
- **run_simpleFoam_adm.py**: upstreamPoint를 flow.get('upstreamX/Y/Z')에서 읽어서 fvOptions에 동적 생성
- **SKILL.md**: diskDir, upstreamPoint 설명 자동 계산 방식으로 업데이트
- **template fvOptions**: sink=true 고정, 주석 업데이트
- **SKILL.md 파라미터 테이블**: axisX/Y/Z → Uinf/AoA/AoS 기반으로 diskDir 자동 계산

---

## 전체 작업 기록

### 1. 스킬 구축 (2026-08-14 오전)
- **기반**: 기존 simpleFoam skill 복사하여 ADM 버전 생성
- **디렉토리**: `/home/bosung/.openclaw/workspace/skills/simpleFoam-adm/`
- **템플릿 디렉토리**: `assets/simpleFoam-adm-case-template/`
- **스크립트**: `scripts/calculate_adm_params.py`, `scripts/run_simpleFoam_adm.py`

### 2. 초기 topoSetDict 실패 (2026-08-14)
- **첫 실패**: `cylinderToCell` syntax 오류 (p1/p2 → point1/point2, source → sourceInfo)
- **원인**: OpenFOAM v2512의 `cylinderToCell` syntax mismatch
- **해결**: `sourceInfo { p1 ...; p2 ...; radius ...; }` 구조로 수정

### 3. simpleFoam Cp/Ct 음수 오류 (2026-08-14)
- **첫 실패**: `Cp = -0.0088` → `FatalError: Cp and Ct must be greater than zero`
- **원인**: `sink: false` → `sink_ = -1` → Cp/Ct에 음수 부호 적용
- **해결**: `sink: true`로 설정하여 positive coefficient 유지
- **물리적 의미**: 
  - `sink: true` = propeller/thrust generator (추력 발생기)
  - `sink: false` = brake/diffuser (저항/디퓨저)
  - Drone/비행기 프로펠러 → `sink: true` 필수

### 4. parallel simpleFoam 성공 테스트 (2026-08-14 오후)
- **환경**: 16 cores, 27x13 inch APC propeller, 7000 RPM, Uinf=41.667 m/s
- **결과**: Time=330까지 정상 수렴, residuals ~1e-7
- **추력**: Cd=0.0603, Cl=0.241 (양수 Cp/Ct 유지)
- **Froude scaling**: diskArea=2.627m²,.Ct=0.0877, Cp=0.0267

### 5. ADM 물리적 해석 (2026-08-14)
- **Drone/비행기 프로펠러 특성**:
  - 추력 방향 = Uinf 방향 (flow direction)
  - Disk normal = flow direction과 동일
  - 예: Uinf=(41.667, 0, 0) → diskDir=(-1, 0, 0) or (1, 0, 0)
- **actuatorDiskSource 로직**:
  - Disk에서 distributed force 발생
  - Force = thrust + power extraction
  - Froude scaling: `T = 0.5 * rho * A * U_local² * Ct`
  - Power: `P = 0.5 * rho * A * U_local³ * Cp`

---

## ADM 상세 매개변수 설명

### 1. disk center (X, Y, Z)
- **설명**: Actuator disk의 중심좌표 (m 단위)
- **물리적 의미**: 프로펠러 중심의 위치
- **예시**: `(2.5, 0, 0)` →机身에서 2.5m 떨어진 위치

### 2. disk direction (axis X, Y, Z)
- **설명**: disk normal vector (정규화됨)
- **물리적 의미**: disk가 수직인 방향, 추력 방향의 반대
- **중요**: Drone/비행기 프로펠러에서 disk direction은 flow direction과 반대
  - Uinf=(41.667, 0, 0) → diskDir=(-1, 0, 0) (추력은 +X 방향)
  - diskDir=(1, 0, 0) → 추력은 -X 방향
- **반드시**: `sink=true` (추력 발생기용)
- **주의**: `sink=false` → propeller가 브레이크/저항으로 동작

### 3. disk radius
- **설명**: actuator disk의 반지름 (m)
- **물리적 의미**: 프로펠러 반지름
- **예시**: `0.9144` → 27 inch propeller (half)

### 4. diskArea
- **계산**: `π × radius²`
- **물리적 의미**: actuator disk의 면적

### 5. Ct (Thrust Coefficient)
- **설명**: 추력계수
- **물리적 의미**: disk에서 발생하는 추력의 크기
- **부호**: **양수만 허용** (`sink=true`로 강제)
- **물리**: `T = 0.5 × ρ × A × U_local² × Ct`

### 6. Cp (Power Coefficient)
- **설명**: 동력계수 (추력 + 동력 추출)
- **물리적 의미**: disk에서 추출/전달되는 동력의 크기
- **부호**: **양수만 허용** (`sink=true`로 강제)
- **물리**: `P = 0.5 × ρ × A × U_local³ × Cp`

### 7. sink
- **설명**: disk의 물리적 성질
- **값**: `true` 또는 `false`
- **의미**:
  - `sink=true`: **추력 발생기** (propeller, drone propeller)
    - disk에서 flow 방향으로 추력 발생
    - Cp, Ct 양수 유지 ✅
  - `sink=false`: **저항/디퓨저** (brake, wind turbine with diffusion)
    - disk에서 flow 반대 방향으로 저항 발생
    - Cp, Ct 음수 → OpenFOAM에서 FatalError ❌
- **Drone/비행기 프로펠러 → 반드시 `sink: true`**

### 8. variant (Froude / variableScaling)
- **Froude**: 표준 Froude scaling (가장 일반적)
  - disk에서 uniform force distribution
  - Cp, Ct가 thrust와 power를 직접 결정
- **variableScaling**: 지역적 velocity에 따라 동적 scaling
  - 복잡한 cases (예: 다중 disk)

### 9. monitorMethod (points / cellZoneAverage)
- **points**: upstreamPoint에서 local velocity 측정
- **cellZoneAverage**: cellZone 내 평균 velocity 사용
- **기본**: `points` (upstreamPoint에서 측정)

### 10. upstreamPoint
- **설명**: incoming velocity를 측정할 위치 (m)
- **물리적 의미**: propeller upstream의 freestream velocity
- **예시**: `(2.5, 0, 0)` (disk center와 동일)

### 11. cylinder thickness (topoSet)
- **설명**: actuatorDiskZone을 생성하는 cylinder의 두께
- **계산**: `radius × 1.05` (프로펠러 반지름의 105%)
- **중요**: disk thickness가 너무 얇으면 → cellZone cell 수가 부족
- **원리**: cylinderToCell → disk 중심을 지나가는 cylinder로 cellZone 생성

---

## ADM 로직 흐름

```
[ADM Input]
├── disk center (X, Y, Z)
├── disk direction (normal vector)
├── disk radius
├── Ct (thrust coefficient)
├── Cp (power coefficient)
├── sink (true/false)
├── variant (Froude/variableScaling)
└── monitorMethod (points/cellZoneAverage)

[topoSet]
├── cylinderToCell (p1=center, p2=center+axis*0.005, radius=radius*1.05)
├── cellSet → actuatorDiskCellSet
└── cellZoneSet → actuatorDiskZone

[run_simpleFoam_adm.py]
├── fvOptions 생성 (cellZone mode)
│   ├── regionType: cellZone
│   ├── cellZone: actuatorDiskZone
│   ├── diskArea: πr²
│   ├── diskDir: normal vector
│   ├── diskCentre: center
│   ├── variant: Froude
│   ├── monitorMethod: points
│   ├── upstreamPoint: center
│   ├── Ct: constant Ct_value
│   ├── Cp: constant Cp_value
│   └── sink: true
├── decomposePar (parallel 분할)
└── mpirun simpleFoam -parallel
    ├── actuatorDiskSource 초기화
    ├── U_local = incoming velocity at upstreamPoint
    ├── T = 0.5 * rho * A * U_local² * Ct
    ├── P = 0.5 * rho * A * U_local³ * Cp
    └── sourceTerm = distributed force on cellZone
```

---

## 파일 구조
```
skills/simpleFoam-adm/
├── SKILL.md                              ✅ (최종 업데이트)
├── PROGRESS.md                           ✅ (최종 업데이트)
├── assets/
│   └── simpleFoam-adm-case-template/
│       ├── 0/
│       │   ├── p                         ✅ (freestreamPressure, zeroGradient)
│       │   ├── U                         ✅ (freestreamVelocity, noSlip)
│       │   ├── k                         ✅ (freestream, kqRWallFunction)
│       │   ├── omega                     ✅ (freestream, omegaWallFunction)
│       │   └── nut                       ✅ (freestream, nutUSpaldingWallFunction)
│       ├── constant/
│       │   ├── transportProperties       ✅ (Newtonian, nu)
│       │   ├── turbulenceProperties      ✅ (kOmegaSST, omegaMin 1e-10)
│       │   └── fvOptions                 ✅ (동적 생성, cellZone 기반)
│       └── system/
│           ├── controlDict               ✅ (application=simpleFoam)
│           ├── fvSchemes                 ✅ (steadyState, upwind, limited 0.333)
│           ├── fvSolution                ✅ (GAMG p, smoothSolver, SIMPLE)
│           ├── decomposeParDict          ✅ (scotch)
│           ├── forceCoeffs               ✅ (forceCoeffs1 + forces1)
│           └── topoSetDict               ✅ (cylinderToCell → cellZone)
└── scripts/
    ├── calculate_adm_params.py           ✅
    └── run_simpleFoam_adm.py             ✅
```

---

## 발산 방지 설정
- **kOmegaSST turbulence**: omegaMin 1e-10 포함
- **relaxationFactors**: U=0.7, k=0.5, omega=0.5
- **nNonOrthogonalCorrectors**: 3
- **mpirun**: `--oversubscribe` 옵션 필수 (hyperthreading 시스템 에러 방지)

## 파라미터 테이블

### calculate_adm_params.py
| 카테고리 | 필드 | 기본값 | 설명 |
|---------|------|-----|---|
| **ADM** | centerX/Y/Z | 0, 0, 0 | disk 중심좌표 (m) |
| **ADM** | axisX/Y/Z | 1, 0, 0 | disk normal 벡터 |
| **ADM** | radius | 1 | disk 반지름 (m) |
| **ADM** | Ct | 0.8 | 추력계수 (양수) |
| **ADM** | Cp | 0.4 | 동력계수 (양수) |
| **ADM** | sink | true | **추력 발생기** (Drone/비행기 프로펠러용) |
| flow | Uinf | 41.667 (150 km/h) | freestream velocity (m/s) |
| flow | AoA | 0.0 | angle of attack (deg) |
| flow | AoS | 0.0 | angle of sideslip (deg) |
| fluid | rho | 1.225 | density (kg/m³) |
| fluid | nu | 1.5e-5 | kinematic viscosity (m²/s) |
| turbulence | model | kOmegaSST | RAS model |
| turbulence | intensity | 0.01 | turbulence intensity |
| turbulence | viscosityRatio | 10 | mu_t/nu ratio |
| turbulence | lengthScale | 1.0 | length scale |
| run | endTime | 1000 | simulation time steps |
| run | deltaT | 1 | time step |
| run | writeInterval | 100 | write interval |
| reference | L_ref | 1.0 | reference length |
| reference | A_ref | 1.0 | reference area |
| CofR | CofR_x/y/z | 0.0 | center of rotation |
| boundary | patch | ["far", "surface"] | patch names |
| boundary | far_BC | freestream | far field BC |
| boundary | surface_BC | wall | surface BC |
| topoSet | enabled | true | cellZone 생성 활성화 |
| topoSet | name | actuatorDiskZone | cellZone 이름 |
| topoSet | radius_mult | 1.05 | cylinder 두께 (radius * 1.05) |

---

## 주요 특징
- **actuatorDisk** ADM source term: distributed force 모델링 (Drone/비행기 프로펠러용)
- **parallel execution**: decomposePar → mpirun --oversubscribe → reconstructPar → cleanup
- **kOmegaSST** turbulence: omegaMin 1e-10, relaxationFactors 자동 계산
- **placeholdor 기반**: 25개 플레이스홀더 자동 치환
- **adm_params.json** → run_simpleFoam_adm.py 단일 진입점
- **Drone/비행기 프로펠러용**: 항상 추력 방향 = Uinf 방향, diskDir = flow 방향 반대
- **sink: true 강제**: Cp/Ct 양수 보장 (에러 방지)
- **cylinder thickness**: radius * 1.05 (cellZone cell 수 보장)

## 사용 방법
```bash
# 1. 파라미터 계산
python3 calculate_adm_params.py

# 2. simpleFoam ADM 실행
python3 run_simpleFoam_adm.py
```

## 테스트 결과 (myShahed case)
- **mesh**: 1,446,478 cells (checkMesh OK)
- **topoSet**: actuatorDiskZone 10,876 cells
- **parallel**: 16 cores
- **Cp/Ct**: 양수 유지 (Cp=0.0267, Ct=0.0877)
- **수렴**: Time=330까지 안정적 (residuals ~1e-7)
- **추력 방향**: +X (Uinf direction)
