---
name: simpleFoam-adm
description: simpleFoam Actuator Disk Model (ADM) - 드론/비행기 프로펠러 추력 시뮬레이션
---

# simpleFoam ADM Skill

simpleFoam (비압축성) 기반 Actuator Disk Model (ADM) 워크플로우 스킬. **드론/비행기 프로펠러** 추력 시뮬레이션에 최적화.

## 선택 규칙
- **ADM (Actuator Disk)**: 풍력 터빈/프로펠러의 distributed force source term 필요
- **simpleFoam**: 비압축성, 정류류 (steady-state)
- **kOmegaSST**: RAS turbulence model (omegaMin 1e-10 포함)
- **APC 프로펠러 데이터**: `apc-prop-perf` 스킬 연동으로 Ct/Cp 자동 조회 가능

## ⚠️ 핵심 원칙: Drone/비행기 프로펠러용
- **diskDir**: **user 직접 입력** — disk normal vector = propeller thrust vector direction
- **Uinf, AoA, AoS**: 사용자가 직접 입력 → Uinf vector 자동 계산
- **sink = true** (반드시, Cp/Ct 양수 보장)
- propeller는 유체를 밀어내는 **추력 발생기** → `sink: true`

### user 입력 파라미터

| 파라미터 | 설명 | 입력 단위 | 예시 |
|--|--|--|--|
| **disk center (X, Y, Z)** | disk 중심좌표 | m | (0, 0, 0) |
| **diskDir (X, Y, Z)** | **disk normal vector — propeller thrust vector direction** | 무차원 벡터 | (1, 0, 0) |
| **disk radius** | disk 반지름 | m | 0.5 |
| **Uinf** | 자유류 속도 (freestream velocity magnitude) | m/s | 41.667 (150 km/h) |
| **AoA** | angle of attack — 유체 흐름의 수직 각도 | deg | 0.0 |
| **AoS** | angle of sideslip — 유체 흐름의 수평 각도 | deg | 0.0 |

### diskDir — propeller thrust direction
- **의미**: `diskDir is the direction of the thrust vector of the propeller`
- **입력**: user가 직접 입력 (normalize 필요, 스크립트가 자동 normalize)
- **물리적 의미**: disk에 수직인 방향 (프로펠러 회전축 방향)
- **thrust 발생 방향**: diskDir 방향으로 추력 발생
- **sink=true일 때**: Cp, Ct 양수 → 추력 = diskDir 방향

### Uinf 벡터 자동 계산
```
Ux = Uinf × cos(AoS) × cos(AoA)
Uy = Uinf × sin(AoS)
Uz = Uinf × sin(AoA)
```

### U_perp (APC Ct/Cp lookup용)
```
U_perp = Uinf_vector · diskDir = Ux·nx + Uy·ny + Uz·nz
|U_perp| → mph → APC DB에서 Ct/Cp 보간
```
- 프로펠러는 disk 면에 **수직인 속도**로만 추력 발생
- **주의**: diskDir와 Uinf_vector가 수직이면 U_perp=0 → 추력 없음

**예시: diskDir=(1,0,0), Uinf=50, AoA=5°, AoS=0°**
```
diskDir = (1, 0, 0)   ← user 입력
Ux = 50 × cos(0°) × cos(5°) = 49.81
Uy = 0
Uz = 50 × sin(5°) = 4.36
Uinf_vector = (49.81, 0, 4.36)

U_perp = (49.81, 0, 4.36) · (1, 0, 0) = 49.81 m/s
speed_mph = 49.81 / 0.44704 = 111.4 mph → APC DB lookup
```

> **주의**: diskDir와 Uinf_vector가 수직이면 U_perp=0 → 추력 없음. 프로펠러 disk 면이 유체 흐름과 수직이 되어야 함.

---

## 워크플로우

### 1. 파라미터 계산
```bash
python3 calculate_adm_params.py
```
- **mandatory**: `mesh_path`, `disk center(X,Y,Z)`, `disk radius`
- **diskDir**: **user 직접 입력** (normalize 포함)
- **upstreamPoint**: `diskCenter + diskDir×0.1×radius + perp×0.75×radius` (perp = cross(diskDir, (0,1,0)) if not parallel, else cross(diskDir, (1,0,0)))
- **프로펠러 정보 (선택)**: diameter(inch), pitch(inch), RPM → **APC DB 자동 조회** → Ct/Cp 자동 적용
- JSON → 출력 → 표시 → **승인 필수**

### 2. simpleFoam parallel 실행
```bash
```
- JSON 자동 검색: `adm_params.json` (실행 디렉토리 기준)
- 무조건 parallel 실행 (decomposePar → mpirun --oversubscribe simpleFoam -parallel → reconstructPar → processor* cleanup)
- 로그 파일명: `log.simpleFoam`
- case 폴더 생성 후 `case/` + `case.foam` 파일 자동 생성

## 워크플로우 규칙
- **output_dir**: 실행 디렉토리 (AI가 대화로 판단)
- **mesh_path**: 메쉬 polyMesh 디렉토리
- **파라미터 계산 후 승인 필수**: 승인 전에 실행하지 않음

## 템플릿 구조
```
assets/simpleFoam-adm-case-template/
├── 0/
│   ├── p          (freestreamPressure, zeroGradient)
│   ├── U          (freestreamVelocity, noSlip)
│   ├── k          (freestream, kqRWallFunction)
│   ├── omega      (freestream, omegaWallFunction)
│   └── nut        (freestream, nutUSpaldingWallFunction)
├── constant/
│   ├── transportProperties      (Newtonian, nu)
│   ├── turbulenceProperties    (kOmegaSST, omegaMin 1e-10)
│   └── fvOptions               (actuatorDisk ADM source term)
└── system/
    ├── controlDict       (application=simpleFoam)
    ├── fvSchemes         (steadyState, upwind, limited 0.333)
    ├── fvSolution        (GAMG p, smoothSolver, SIMPLE)
    ├── decomposeParDict  (scotch)
    └── forceCoeffs       (forceCoeffs1 + forces1)
```

## 플레이스홀더
| 플레이스홀더 | 파라미터 | 설명 |
|---|---|---|
| @ADM_centerX/Y/Z@ | ADM.centerX/Y/Z | disk 중심좌표 (m) |
| @ADM_diskDirX/Y/Z@ | ADM.diskDirX/Y/Z | disk normal vector (thrust 방향, normalize) |
| @ADM_radius@ | ADM.radius | disk 반지름 (m) |
| @ADM_diskArea@ | derived | π × radius² |
| @ADM_Ct@ | ADM.Ct | 추력계수 |
| @ADM_Cp@ | ADM.Cp | 동력계수 |
| @ADM_upstreamPointX/Y/Z@ | derived | diskCenter + diskDir×0.1×radius + perp×0.75×radius (upstream: diskDir) |
| @ADM_centre2X/Y/Z@ | derived | center + diskDir × 0.005 |
| @ADM_cylinderRadius@ | derived | radius × 1.05 |
| @Uvec@ | flow.Ux/Y/Z | freestream velocity vector |
| @Uinf@ | flow.Uinf | freestream velocity magnitude |
| @kIni@ | turbulence.k_ini | turbulent kinetic energy |
| @omegaIni@ | turbulence.omega_ini | specific dissipation rate |
| @nu@ | fluid.nu | kinematic viscosity |
| @rhoInf@ / @rho@ | fluid.rho | density |
| @endTime@ | run.endTime | simulation time steps |
| @deltaT@ | run.deltaT | time step |
| @writeInterval@ | run.writeInterval | write interval |
| @CofRx/Y/Z@ | CofR.x/y/z | center of rotation |
| @lRef@ / @Aref@ | reference.L_ref/A_ref | reference length/area |
| @magUInf@ | flow.Uinf | freestream velocity magnitude |
| @surfaceName@ | auto-detect | surface patch name from polyMesh/boundary |
| @nSubdomains@ | num_procs | parallel cores |

---

## fvOptions - actuatorDisk (cellZone 기반)


### OpenFOAM v2512 - actuationDiskSource 상세 매개변수

```
actuatorDisk
{
    type            actuationDiskSource;
    active          on;

    // ===== Selection =====
    selectionMode     cellZone;
    cellZone          actuatorDiskZone;

    // ===== Actuator disk geometric properties =====
    diskArea        <value>;           // π × radius²

    // disk normal vector (thrust direction, user input + normalize)
    diskDir         (x y z);

    // disk 중심좌표
    diskCentre      (x y z);

    // ===== Force method =====
    variant         Froude;

    // ===== Incoming velocity monitoring =====
    monitorMethod   points;
    upstreamPoint   (x y z);  // incoming velocity 측정 위치

    // ===== Thrust and Power Coefficients =====
    Ct              constant <value>;
    Cp              constant <value>;

    // ===== Sink/Source Flag (중요!) =====
    sink            true;  // propeller thrust generator
}
```

### upstreamPoint — incoming velocity monitoring (upstream: diskDir direction)
- **의미**: incoming velocity를 측정할 위치 (m)
- **계산**: `upstreamPoint = diskCenter + diskDir × 0.1 × radius + perpDir × 0.75 × radius`
- **위치**: disk 바깥 upstream (flow 들어오는 쪽)
- **설명**: diskDir는 **thrust direction**이자 **upstream 방향**. diskDir가 upstream을 가리키므로 `+diskDir`로 계산. diskDir = (-1,0,0)이면 upstreamPoint는 diskCenter보다 -X 쪽.
- **disk center가 아님** — disk 바로 바깥에 위치해야 정확한 incoming velocity 측정

### U_perp (APC Ct/Cp lookup용)
- **계산**: `U_perp = Uinf_vector · diskDir`
- **물리적 의미**: 프로펠러는 disk 면에 수직인 속도로만 추력 발생
- **APC DB**: `|U_perp| → mph → Ct/Cp 보간`

### ⚠️ sink = true 필수!
`actuationDiskSource` 소스 코드에서 `sink_ = sink ? 1 : -1`
- `sink=true`: `sink_ = +1` → Cp×sink_ = 양수 ✅
- `sink=false`: `sink_ = -1` → Cp×sink_ = 음수 → **FatalError**

**Drone/비행기 프로펠러는 반드시 `sink: true`**

---

## cellZone 생성 (topoSetDict) — ADM 영역 정의


### cylinder 기반 cellZone 생성 로직
```
actions
(
    {
        name        actuatorDiskCellSet;
        type        cellSet;
        action      new;
        source      cylinderToCell;
        sourceInfo
        {
            p1      (x y z);     // disk center
            p2      (x y z);     // center + diskDir × 0.005
            radius  <value>;      // radius × 1.05
        }
    }
    {
        name        actuatorDiskZone;
        type        cellZoneSet;
        action      new;
        source      setToCellZone;
        sourceInfo
        {
            set     actuatorDiskCellSet;
        }
    }
);
```

### topoSet 파라미터
| 파라미터 | 값 | 설명 |
|--|--|--|
| **p1** | `diskCenter (X, Y, Z)` | cylinder 시작점 = disk 중심 |
| **p2** | `diskCenter + diskDir × 0.005` | cylinder 끝점 (very short cylinder) |
| **radius** | `ADM.radius × 1.05` | 프로펠러 반지름의 105% |

### cylinder 두께 0.005m 의미
- p1과 p2의 거리 = `|diskDir| × 0.005 = 0.005m` (diskDir는 normalize됨)
- disk가 매우 얇은 원반임을 반영
- **반드시 p1 ≠ p2**: 동간이면 cylinder thickness=0 → cellZone cell 수 부족 → 오류

### workflow 순서
1. template 복사 → mesh 복사 → placeholder 치환
2. fvOptions **동적 생성** (cellZone mode, sink=true)
3. **topoSet 실행** → cylinder cellSet → cellZone 생성
4. decomposePar → mpirun simpleFoam -parallel → reconstructPar → cleanup

---

## 발산 방지 설정
- **kOmegaSST turbulence**: omegaMin 1e-10 포함
- **relaxationFactors**: U=0.7, k=0.5, omega=0.5
- **nNonOrthogonalCorrectors**: 3
- **mpirun**: `--oversubscribe` 옵션 필수

## 파라미터 테이블

### calculate_adm_params.py
| 카테고리 | 필드 | 기본값 | 설명 |
|---------|--|-----|---|
| **ADM** | centerX/Y/Z | 0, 0, 0 | disk 중심좌표 (m) |
| **ADM** | diskDirX/Y/Z | 1, 0, 0 | **disk normal vector (thrust direction, user 입력)** |
| **ADM** | radius | 1 | disk 반지름 (m) |
| **ADM** | Ct | 0.8 | 추력계수 (양수) |
| **ADM** | Cp | 0.4 | 동력계수 (양수) |
| **flow** | Uinf | 41.667 | freestream velocity (m/s) |
| **flow** | AoA | 0.0 | angle of attack (deg) |
| **flow** | AoS | 0.0 | angle of sideslip (deg) |
| **flow** | upstreamX/Y/Z | auto | diskCenter + diskDir×0.1×radius + perp×0.75×radius (upstream: diskDir) |
| fluid | rho | 1.225 | density (kg/m³) |
| fluid | nu | 1.5e-5 | kinematic viscosity (m²/s) |
| turbulence | model | kOmegaSST | RAS model |
| turbulence | intensity | 0.01 | turbulence intensity |
| turbulence | viscosityRatio | 10 | mu_t/nu ratio |
| turbulence | lengthScale | 1.0 | length scale |
| run | endTime | 1000 | simulation time steps |
| run | deltaT | 1 | time step |
| run | writeInterval | 100 | write interval |
| reference | L_ref | 1.0 | reference length (omega = √k/(Cμ^0.25·L), hisa 스킬과 동일) |
| reference | A_ref | 1.0 | reference area |
| CofR | x/y/z | 0.0 | center of rotation |
| boundary | patch | ["far", "surface"] | patch names |

---

## diskDir 설명

**diskDir is the direction of the thrust vector of the propeller.**

- **의미**: disk normal vector = propeller가 추력을 발생하는 방향
- **입력 방식**: user가 직접 입력 (normalize 필요)
- **fvOptions**: `actuationDiskSource.diskDir`로 직접 전달
- **thrust 방향**: sink=true일 때 diskDir 방향으로 추력 발생
- **U_perp**: `Uinf_vector · diskDir` — 프로펠러가 실제로 느끼는 속도 (Ct/Cp lookup용)

### 설정 예시
```
diskDir = (1, 0, 0)   ← user 입력 (propeller thrust direction)
Uinf = 50 m/s, AoA = 0°, AoS = 0°
Uinf_vector = (50, 0, 0) m/s
U_perp = (50, 0, 0) · (1, 0, 0) = 50 m/s
sink = true
Ct = 0.0877 (양수)
Cp = 0.0267 (양수)
```

---

## 주요 특징
- **actuatorDisk** ADM source term: distributed force 모델링 (Drone/비행기 프로펠러용)
- **parallel execution**: decomposePar → mpirun --oversubscribe → reconstructPar → cleanup
- **kOmegaSST** turbulence: omegaMin 1e-10, relaxationFactors 자동 계산
- **placeholder 기반**: 24개 placeholder 자동 치환
- **diskDir**: user 직접 입력 (normalize 포함), propeller thrust direction
- **sink: true 강제**: Cp/Ct 양수 보장 (에러 방지)
- **cylinder thickness**: diskDir × 0.005 (cellZone cell 수 보장)

## 사용 방법
```bash
# 1. 파라미터 계산
python3 calculate_adm_params.py

# 2. simpleFoam ADM 실행
```

## 테스트 결과 (myShahed case, 2026-08-14)
- **mesh**: 1,446,478 cells (checkMesh OK)
- **topoSet**: actuatorDiskZone 10,876 cells
- **parallel**: 16 cores (scotch decomposition)
- **Cp/Ct**: 양수 유지 (Cp=0.0267, Ct=0.0877)
- **sink**: true (추력 발생기)
- **수렴**: Time=330까지 안정적 (residuals ~1e-7)
- **추력 방향**: +X (Uinf direction)
- **Cd/CmPitch**: Cd=0.0603, Cl=0.241, CmPitch=0.144

---

## ⚠️ mpirun 실행 방식 수정 (2026-09-09)

**문제:** `mpirun ... 2>&1 | tee log.simpleFoam` — pipe buffer(64KB)가 가득 차면 mpirun이 write blocked → hang → gateway SIGKILL

**수정 전:**
```bash
mpirun -np N simpleFoam -parallel 2>&1 | tee log.simpleFoam
```

**수정 후:**
```bash
mpirun -np N --oversubscribe simpleFoam -parallel > log.simpleFoam 2>&1
```

**원인:** `os.system()` + `tee` 파이프에서 Python이 pipe buffer를 읽지 않아 쌓임 → write blocked → hang → SIGKILL
**해결:** `tee` 파이프 제거, 파일에 직접 redirect → pipe 없음, buffer 축적 없음
**수정 파일:** `run_simpleFoam_adm.py` (mpirun 호출 부분)
