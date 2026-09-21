# 아키텍처 설계서

## 전체 구조

```
APC .dat 파일 → downloader → parser → SQLite(DB) → interpolator ← query
```

## 모듈별 책임

### 1. downloader.py
- APC Propeller 웹사이트에서 모든 `.dat` 파일 다운로드
- 파일 목록은 APC 사이트의 performance data 페이지 또는 ZIP 아카이브에서 확인
- 다운로드된 파일은 `data/raw/`에 저장
- 중복 다운로드 방지 (파일 existence + modification date 체크)

### 2. parser.py
- 고정폭(fixed-width) 텍스트 포맷 파싱
- 헤더 정보 추출: 프로펠러 명칭, 직경(D), 피치(P), 버전, 시뮬레이션 날짜
- 각 RPM 블록별로 데이터 행렬을 pandas DataFrame으로 변환
- 모든 컬럼 float 변환, NaN/invalid 값 처리

### 3. database.py
- SQLite 기반 데이터베이스 (`data/apc_props.db`)
- 테이블 구조:
  - `propellers`: id, name, diameter_inch, pitch_inch, type, version, sim_date
  - `performance`: id, propeller_id, rpm, V_mph, J, Pe, Ct, Cp, PWR_Hp, Torque_InLbf, Thrust_Lbf, PWR_W, Torque_Nm, Thrust_N, THR_PWR_gW, Mach, Reyn, FOM
- 초기화: 테이블 생성 + 데이터 삽입/갱신
- 검색: propeller_id 기반 성능 데이터 조회

### 4. interpolator.py
- **1단계 보간** (같은 프로펠러 내): RPM과 V(mph)를 독립 변수로 선형 보간
  - 사용: `scipy.interpolate.interp2d` 또는 `LinearNDInterpolator`
- **2단계 보간** (프로펠러 간): 직경(D)과 피치(P) 차이를 고려한 다차원 보간
  - 근접한 N개 프로펠러를 찾아 가중 평균
- 신뢰도 지표: 보간 거리 기반 confidence score 반환

### 5. query.py
- CLI 인터페이스: `--diameter`, `--pitch`, `--rpm`, `--speed` 옵션
- 결과 출력: Thrust, Power, Torque, Efficiency, confidence
- JSON 출력 옵션 (`--json`)

### 6. main.py
- 전체 파이프라인 제어
- 명령: `update` (다운로드+파싱+DB 갱신), `query` (조건 입력 → 보간 결과)

## 데이터 타입

| 컬럼 | 타입 | 단위 |
|------|------|------|
| V | float | mph |
| J | float | dimensionless |
| Pe | float | dimensionless |
| Ct | float | dimensionless |
| Cp | float | dimensionless |
| PWR | float | Hp, W |
| Torque | float | In-Lbf, N-m |
| Thrust | float | Lbf, N |
| Mach | float | dimensionless |
| Reyn | float | dimensionless |
| FOM | float | dimensionless |
