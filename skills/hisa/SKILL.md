---
name: hisa
description: HiSA 고속 공기역학 솔버 (compressible kOmegaSST)
---

# HiSA Solver Skill

## ✅ 필수 실행 절차 (매번 순서대로!)

### Step 1: 스크립트 복사
```bash
cp ~/.openclaw/workspace/skills/hisa/scripts/calculate_solve_params.py <실행 디렉토리>
cp ~/.openclaw/workspace/skills/hisa/scripts/run_hisa.py <실행 디렉토리>
```

### Step 2: 파라미터 계산 (interactive)
```bash
cd <실행 디렉토리>
python3 calculate_solve_params.py
# → mesh_path 입력 요청 → mesh 경로 입력
```

### Step 3: JSON 출력 및 승인 대기
- `solve_params.json`이 생성됨
- **파라미터 표시 후 승인 필수** — 승인 전 실행 절대 불가!

### Step 4: HISA 해석 실행 (승인 후)
```bash
cd <실행 디렉토리>
nohup python3 run_hisa.py solve_params.json > log.hisa 2>&1 &
```
- 로그 파일명: `log.hisa`

**⚠️ 절대 금지:** `| head`, `| tail -N` 등 출력 제한 명령어 — 솔버 죽임!

### mpirun 실행 방식 (2026-09-09 / 09-10 수정)
- **2026-09-09:** `mpirun ... 2>&1 | tee log.hisa` → `mpirun ... > log.hisa 2>&1` (pipe 제거, SIGKILL 방지)
- **2026-09-10:** `os.system()` → `subprocess.Popen` + `setsid nohup` + poll loop
  - **문제:** openclaw/python 세션 종료 시 mpirun이 SIGHUP으로 죽음
  - **해결:** `setsid`(새 session, PID 1에 재부착) + `nohup`(SIGHUP 무시) + `Popen(start_new_session=True)`
  - **중간 보고:** poll loop에서 5분마다 log.hisa 마지막 3줄 출력
  - **reconstructPar:** hisa 성공 시에만 실행 (실패 시 skip)
- **수정 위치:** `run_hisa.py` `run_parallel_hisa()` 함수

---

## ⏱️ 실행 시간 가이드 (exec timeout)

HiSA 해석은 **수 분 ~ 수 시간** 소요. `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_solve_params.py` (파라미터 계산) | `timeoutSeconds: 120` (빠름) |
| `run_hisa.py` (해석) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |
| `reconstructPar` (재구성) | `timeoutSeconds: 600` (메쉬 크기에 따라) |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

---

HiSA (High Speed Aerodynamic) 솔버용 OpenFOAM 워크플로우 스킬.

## 선택 규칙
- **HiSA solver**: 고속 공기역학 시뮬레이션 (compressible, kOmegaSST turbulence)
- **simpleFoam과 유사한 파라미터 구조** — `calculate_solve_params.py` → `run_hisa.py`

## 발산 방지 설정
- **kOmegaSST turbulence**: omegaMin 1e-10 포함
- **relaxationFactors**: `k|omega|nuTilda` → 0.5

## ⚠️ CRITICAL: No Output Limiting (반드시 준수)

**절대 장기 실행 프로세스의 stdout/stderr를 제한하는 명령어(head, tail -N 등)를 사용하지 않습니다.**

*   **금지:** `| head`, `| wc`, 파이프라인을 통한 상류 출력 제한
*   **원인:** 하류가 종료될 때 SIGPIPE 신호를 보내 솔버/스크립트를 조용히 죽게 만듭니다. 에러 없이 바로 종료됩니다.
*   **올바른 방식:** 무조건 `nohup ... > log.hisa 2>&1 &` 또는 전체 출력을 남겨야 합니다. 로그 확인은 완료 후 별도 실행하세요.

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

---

## ⚠️ mpirun 실행 방식 수정 (2026-09-09 / 09-10)

**2026-09-09 — pipe buffer SIGKILL:**

**수정 전:**
```bash
mpirun -np N hisa -parallel 2>&1 | tee log.hisa
```
**수정 후:**
```bash
mpirun -np N --oversubscribe hisa -parallel > log.hisa 2>&1
```
**원인:** `os.system()` + `tee` 파이프에서 Python이 pipe buffer를 읽지 않아 쌓임 → write blocked → hang → SIGKILL

**2026-09-10 — 세션 종결 시 mpirun 사망:**

**수정 전:** `os.system(cmd)` — python 프로세스가 mpirun의 부모. python 종료 시 SIGHUP → mpirun 사망

**수정 후:**
```python
import subprocess, time

cmd = (
    f"bash -c 'source /opt/OpenFOAM/OpenFOAM-v2512/etc/bashrc && "
    f"cd {case_dir} && "
    f"setsid nohup mpirun -np {n_procs} --oversubscribe hisa -parallel "
    f"> log.hisa 2>&1'"
)
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

**수정 파일:** `run_hisa.py` `run_parallel_hisa()` 함수
