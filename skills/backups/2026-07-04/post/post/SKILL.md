# post

OpenFOAM 해석 결과(PostProcessing) 데이터 처리 스킬.

## 하위 스크립트

- **force.py** — `_forces` 디렉토리에서 force/moment (total_x/y/z) 데이터 추출 (평균 ± 표준편차). 마지막 N 스텝 기준.  
  `python3 force.py [base_dir] [N_last_steps]`
- **coeff.py** — `coefficient.dat`에서 Cd, Cl, CmPitch 추출 (평균 ± 표준편차).
  `python3 coeff.py [base_dir]`
