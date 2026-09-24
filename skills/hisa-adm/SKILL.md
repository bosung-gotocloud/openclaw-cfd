---
name: hisa-adm
description: HiSA (compressible kOmegaSST, AUSMPlusUp, pseudoTime) Actuator Disk Model - 드론/비행기 프로펠러 추력 시뮬레이션
---

# HiSA ADM Skill

HiSA (High Speed Aerodynamic, compressible, kOmegaSST, AUSMPlusUp, pseudoTime) + **Actuator Disk Model (ADM)** 워크플로우 스킬.

**드론/비행기 프로펠러** 추력 시뮬레이션에 최적화. simpleFoam-adm의 ADM 개념을 HiSA(compressible)에 적용.

## 선택 규칙
- **ADM (Actuator Disk)**: 풍력 터빈/프로펠러의 distributed force source term 필요
- **HiSA**: compressible, pseudoTime (dualTimeStepping), AUSMPlusUp flux scheme
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
- **주의**: diskDir과 Uinf_vector가 수직이면 U_perp=0 → 추력 없음

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

> **주의**: diskDir과 Uinf_vector가 수직이면 U_perp=0 → 추력 없음. 프로펠러 disk 면이 유체 흐름과 수직이 되어야 함.

---

## ✅ 필수 실행 절차 (매번 순서대로!)

### Step 1: 스크립트 복사
```bash
cp ~/.openclaw/workspace/skills/hisa-adm/scripts/calculate_adm_params.py <실행 디렉토리>
cp ~/.openclaw/workspace/skills/hisa-adm/scripts/run_hisa_adm.py <실행 디렉토리>
```

### Step 2: 파라미터 계산 (interactive, ADM 포함)
```bash
cd <실행 디렉토리>
python3 calculate_adm_params.py
# → mesh_path 입력 요청 → mesh 경로 입력
```
- **mandatory**: `mesh_path`, `disk center(X,Y,Z)`, `disk radius`, `diskDir`
- **diskDir**: **user 직접 입력** (스크립트 자동 normalize)
- **Uinf, AoA, AoS**: user 직접 입력 → Uinf vector 자동 계산
- **upstreamPoint**: `diskCenter + diskDir×0.1×radius` (upstream: diskDir direction, incoming velocity 측정용)
- **프로펠러 정보 (선택)**: diameter(inch), pitch(inch), RPM → **APC DB 자동 조회** → Ct/Cp 자동 적용
- `adm_params.json` 생성

### Step 3: JSON 출력 및 승인 대기
- `adm_params.json`이 생성됨
- **파라미터 표시 후 승인 필수** — 승인 전 실행 절대 불가!

### Step 4: HiSA ADM parallel 해석 실행 (승인 후)
```bash
cd <실행 디렉토리>
nohup python3 run_hisa_adm.py > log.hisa 2>&1 &
```
- JSON 자동 검색: `adm_params.json` (실행 디렉토리 기준)
- 무조건 parallel 실행 (decomposePar → mpirun --oversubscribe hisa -parallel → reconstructPar → processor* cleanup)
- 로그 파일명: `log.hisa`
- case 폴더 생성 후 `case/` + `case.foam` 파일 자동 생성

**⚠️ 절대 금지:** `| head`, `| tail -N` 등 출력 제한 명령어 — 솔버 죽임!

## 워크플로우 규칙
- **reconstructPar / processor cleanup**: hisa exit=0일 때만 실행. background launch에서는 exit code를 직접 확인 후 수동 reconstructPar 필요
- **output_dir**: 실행 디렉토리 (AI가 대화로 판단)
- **mesh_path**: 메쉬 polyMesh 디렉토리
- **파라미터 계산 후 승인 필수**: 승인 전에 실행하지 않음

## ⏱️ 실행 시간 가이드 (exec timeout)

HiSA ADM 해석은 **수 분 ~ 수 시간** 소요. `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_adm_params.py` (파라미터 계산) | `timeoutSeconds: 120` (빠름) |
| `run_hisa_adm.py` (해석) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |
| `reconstructPar` (재구성) | `timeoutSeconds: 600` (메쉬 크기에 따라) |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

## 템플릿 구조
```
templates/
├── 0/
│   ├── U          (characteristicFarfieldVelocity, boundaryCorrectedFixedValue)
│   ├── p          (characteristicFarfieldPressure, characteristicWallPressure)
│   ├── T          (characteristicFarfieldTemperature, characteristicWallTemperature)
│   ├── k          (turbulentIntensityKineticEnergyInlet, kqRWallFunction)
│   ├── omega      (turbulentMixingLengthFrequencyInlet, omegaWallFunction)
│   ├── nut        (calculated, nutUSpaldingWallFunction)
│   ├── alphat     (calculated, compressible::alphatWallFunction)
│   └── include/
│       └── freestreamConditions  (U, p, T include file)
├── constant/
│   ├── thermophysicalProperties  (hePsiThermo, sutherland, perfectGas)
│   ├── turbulenceProperties      (kOmegaSST, omegaMin 1e-10)
│   └── fvOptions                 (actuationDisk ADM source term)
└── system/
    ├── controlDict       (application=hisa, forceCoeffs function object)
    ├── fvSchemes         (AUSMPlusUp, dualTime, wVanLeer)
    ├── fvSolution        (GMRES + LUSGS, pseudoTime)
    ├── topoSetDict       (cylinderToCell → actuatorDiskZone)
    └── decomposeParDict  (scotch)
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
| @ADM_upstreamPointX/Y/Z@ | derived | diskCenter + diskDir×0.1R + perp×0.75R |
| @ADM_centre2X/Y/Z@ | derived | center + diskDir × 0.05 × radius |
| @ADM_cylinderRadius@ | derived | radius × 1.05 |
| @Uvec@ | flow.Ux/Y/Z | freestream velocity vector |
| @Uinf@ | flow.Uinf | freestream velocity magnitude |
| @kIni@ | turbulence.k_ini | turbulent kinetic energy |
| @omegaIni@ | turbulence.omega_ini | specific dissipation rate |
| @intensity@ | turbulence.intensity | turbulence intensity |
| @mixingLength@ | turbulence.lengthScale | mixing length |
| @nu@ | fluid.nu | kinematic viscosity |
| @rhoInf@ / @rho@ | fluid.rho | density |
| @T@ | thermodynamic.T | temperature (K) |
| @pInf@ | thermodynamic.pInf | freestream pressure (Pa) |
| @endTime@ | run.endTime | simulation time steps |
| @deltaT@ | run.deltaT | time step |
| @writeInterval@ | run.writeInterval | write interval |
| @pseudoCoNum@ | run.pseudoCoNum | pseudo Courant number |
| @pseudoCoNumMax@ | run.pseudoCoNumMax | pseudo Courant number max |
| @timeScheme@ | run.timeScheme | time scheme |
| @CofRx/Y/Z@ | CofR.x/y/z | center of rotation |
| @lRef@ / @Aref@ | reference.L_ref/A_ref | reference length/area |
| @magUInf@ | flow.Uinf | freestream velocity magnitude |
| @surfaceName@ | auto-detect | surface patch name from polyMesh/boundary |
| @nSubdomains@ | num_procs | parallel cores |

---

## fvOptions - actuationDisk (cellZone 기반)


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
- **설명**: diskDir는 **thrust direction**이자 **upstream 방향**. diskDir이 upstream을 가리키므로 `+diskDir`로 계산. diskDir = (-1,0,0)이면 upstreamPoint는 diskCenter보다 -X 쪽.
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
            p2      (x y z);     // center + diskDir × 0.05 × radius
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
| **p2** | `diskCenter + diskDir × 0.05 × radius` | cylinder 끝점 (very short cylinder) |
| **radius** | `ADM.radius × 1.05` | 프로펠러 반지름의 105% |

### cylinder 두께 (0.05 × radius) 의미
- p1과 p2의 거리 = `0.05 × radius` (diskDir는 normalize됨)
- disk가 매우 얇은 원반임을 반영
- **반드시 p1 ≠ p2**: 동간이면 cylinder thickness=0 → cellZone cell 수 부족 → 오류

### workflow 순서
1. template 복사 → mesh 복사 → placeholder 치환
2. fvOptions **동적 생성** (cellZone mode, sink=true)
3. **topoSet 실행** → cylinder cellSet → cellZone 생성
4. decomposePar → mpirun hisa -parallel → reconstructPar → cleanup

---

## 발산 방지 설정
- **kOmegaSST turbulence**: omegaMin 1e-10 포함
- **relaxationFactors**: `(k|omega|nuTilda)` → 0.5
- **HiSA**: AUSMPlusUp flux scheme, pseudoTime (dualTimeStepping), GMRES + LUSGS

## 파라미터 테이블

### calculate_adm_params.py
| 카테고리 | 필드 | 기본값 | 설명 |
|---------|--|-----|---|
| **ADM** | centerX/Y/Z | 0, 0, 0 | disk 중심좌표 (m) |
| **ADM** | diskDirX/Y/Z | 1, 0, 0 | **disk normal vector (thrust direction, user 입력)** |
| **ADM** | radius | 1 | disk 반지름 (m) |
| **ADM** | Ct | 0.8 | 추력계수 (양수) |
| **ADM** | Cp | 0.4 | 동력계수 (양수) |
| flow | Uinf | 41.667 | freestream velocity (m/s) |
| flow | AoA | 0.0 | angle of attack (deg) |
| flow | AoS | 0.0 | angle of sideslip (deg) |
| flow | upstreamX/Y/Z | auto | diskCenter + diskDir×0.1R + perp×0.75R |
| fluid | rho | 1.225 | density (kg/m³) |
| fluid | nu | 1.5e-5 | kinematic viscosity (m²/s) |
| **thermodynamic** | T | 293.15 | temperature (K) |
| **thermodynamic** | pInf | 101325 | freestream pressure (Pa) |
| turbulence | model | kOmegaSST | RAS model |
| turbulence | intensity | 0.01 | turbulence intensity |
| turbulence | viscosityRatio | 10 | mu_t/nu ratio |
| turbulence | lengthScale | 1.0 | length scale (고정) |
| run | endTime | 1000 | simulation time steps |
| run | deltaT | 1 | time step |
| run | writeInterval | 100 | write interval |
| run | pseudoCoNum | 1 | pseudo Courant number |
| run | pseudoCoNumMax | 10000 | pseudo Courant number max |
| run | timeScheme | steadyState | time scheme |
| reference | L_ref | 1.0 | reference length (fixed) |
| reference | A_ref | 1.0 | reference area |
| CofR | x/y/z | 0.0 | center of rotation |
| boundary | patch | ["far", "surface"] | patch names |

---

## diskDir 설명

**diskDir is the direction of the thrust vector of the propeller.**

- **의미**: disk normal vector = propeller가 추력을 발생하는 방향
- **입력 방식**: user가 직접 입력 (normalize 필요, 스크립트가 자동)
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

## HiSA vs simpleFoam ADM 차이

| 항목 | simpleFoam-adm | hisa-adm |
|------|----------------|----------|
| **Solver** | simpleFoam (incompressible) | HiSA (compressible) |
| **Turbulence** | kOmegaSST | kOmegaSST (동일) |
| **Flux Scheme** | upwind | AUSMPlusUp |
| **Time Scheme** | steadyState (SIMPLE) | pseudoTime (dualTimeStepping) |
| **Pressure Solver** | GAMG | GMRES + LUSGS |
| **Thermodynamic** | 없음 | T, pInf, hePsiThermo |
| **fvOptions** | actuationDiskSource | actuationDiskSource (동일) |
| **topoSet** | cylinderToCell | cylinderToCell (동일) |
| **ADM** | distributed force | distributed force (동일) |

---

## 주요 특징
- **actuatorDisk** ADM source term: distributed force 모델링 (Drone/비행기 프로펠러용)
- **HiSA**: compressible, AUSMPlusUp, pseudoTime — 고속 공기역학
- **parallel execution**: decomposePar → mpirun --oversubscribe → reconstructPar → cleanup
- **kOmegaSST** turbulence: omegaMin 1e-10, relaxationFactors 자동 계산
- **placeholder 기반**: 30개 placeholder 자동 치환
- **diskDir**: user 직접 입력 (normalize 포함), propeller thrust direction
- **sink: true 강제**: Cp/Ct 양수 보장 (에러 방지)
- **cylinder thickness**: diskDir × 0.05 × radius (cellZone cell 수 보장)

## 사용 방법
```bash
# 1. 파라미터 계산
python3 calculate_adm_params.py

# 2. HiSA ADM 실행
python3 run_hisa_adm.py
```

## ⚠️ mpirun 실행 방식 수정 (2026-09-10)

**문제:** `mpirun ... 2>&1 | tee log.hisa` — pipe buffer(64KB)가 가득 차면 mpirun이 write blocked → hang → gateway SIGKILL

**수정 전:**
```bash
mpirun -np N hisa -parallel 2>&1 | tee log.hisa
```

**수정 후:**
```bash
mpirun -np N --oversubscribe hisa -parallel > log.hisa 2>&1
```

**원인:** `os.system()` + `tee` 파이프에서 Python이 pipe buffer를 읽지 않아 쌓임 → write blocked → hang → SIGKILL

**해결:** `tee` 파이프 제거, 파일에 직접 redirect → pipe 없음, buffer 축적 없음

**세션 종결 시 mpirun 사망 방지:**
```python
proc = subprocess.Popen(cmd, shell=True, start_new_session=True)
# poll loop: 5분마다 중간 보고, 종료까지 대기
while proc.poll() is None:
    time.sleep(1)
```

**원인:** openclaw/python 세션이 종료되면 mpirun이 SIGHUP 신호를 받아 에러 없이 조용히 종료

**해결:**
1. `setsid` — 새 session 생성, mpirun이 PID 1에 재부착 → 세션 종결과 독립
2. `nohup` — SIGHUP 무시
3. `Popen(start_new_session=True)` — python 프로세스도 새 session (중첩 안전장치)
4. **poll loop** — 프로세스 종료까지 대기, 5분마다 log.hisa 마지막 3줄 중간 보고

**수정 파일:** `run_hisa_adm.py` `run_parallel_hisa()` 함수
