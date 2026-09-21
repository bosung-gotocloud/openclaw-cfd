---
name: post
description: OpenFOAM post-processing (residual, force, coefficient)
---

# post

OpenFOAM 해석 결과(PostProcessing) 데이터 처리 스킬.

## 하위 스크립트

###_residual_gnuplot.py — Gnuplot 기반 residual plotting_
log.simpleFoam에서 residual 데이터를 파싱하여 Gnuplot PNG 그래프 생성.

- **usage**: `python3 residual_gnuplot.py <log_file> [--plot-type all|velocity|pressure]`
- **plot-type**
  - `all` (default): residual_velocity.png + residual_pressure.png + residual_all.png (2 panels)
  - `velocity`: residual_velocity.png (Ux, Uy, Uz)
  - `pressure`: residual_pressure.png (p, omega, k)
- **output**: case 디렉토리에 `.gnuplot` 스크립트 + `.png` + `_residual_velocity.dat`, `_residual_pressure.dat` 생성
- **해석 중간 모니터링**: 해석 도중 log.simpleFoam에 새 데이터가 추가되면 재실행 → 최신 residual 그래프 생성

### force.py — force/moment 데이터 추출_
`_forces` 디렉토리에서 force/moment (total_x/y/z) 데이터 추출 (평균 ± 표준편차). 마지막 N 스텝 기준.

- **usage**: `python3 force.py [base_dir] [N_last_steps]`

### coeff.py — coefficient 데이터 추출_
`coefficient.dat`에서 Cd, Cl, CmPitch 추출 (평균 ± 표준편차).

- **usage**: `python3 coeff.py [base_dir]`

### monitor_simplefoam_residual.py — 실시간 simpleFoam residual 모니터링_
해석이 running 중인 case 디렉토리를 지정하면 매 10초마다 log.simpleFoam를 파싱하여 Gnuplot으로 residual PNG 그래프를 자동 갱신.

- **usage**: `python3 monitor_simplefoam_residual.py <case_dir> [--interval 10]`
- **주의**: Gnuplot이 설치되어 있어야 함 (`gnuplot --version`)
- **주의**: PNG 파일 생성만 가능 — Gnuplot x11 interactive 환경에서 실시간 업데이트는 현재 불가
- **output**: case 디렉토리에 `residual_*.png` + `residual_*.gnuplot` + `_residual_*.dat` 파일 갱신
- **중단**: Ctrl+C
- **사용 시점**: 사용자가 "실시간 residual 그래프 보여줘"라고 요청할 때만 실행

## 사용 예시

```bash
# 해석 중간에 residual 그래프 요청
cd /home/bosung/WinD/0.cfd/1.AI-agent/simpleFoam/LC62-50H-150kph/case
python3 /home/bosung/.openclaw/workspace/skills/post/residual_gnuplot.py log.simpleFoam --plot-type all
```

```bash
# force/moment 추출
python3 /home/bosung/.openclaw/workspace/skills/post/force.py /home/bosung/WinD/0.cfd/2.kari-cabin-drone/02.no-prop-rounded 1500
```
