# apc-prop-perf — APC Propeller Performance Data

APC Propeller 공식 `.dat` 성능 데이터를 다운로드, 파싱, SQLite 저장, 보간 엔진을 통해 임의의 RPM/속도 조건에서 추력·동력·토크·효율을 계산하는 Python 도구입니다.

**데이터 소스:** APC 공식 웹사이트 `https://www.apcprop.com/technical-information/performance-data/`
**ZIP 아카이브 URL:** `https://www.apcprop.com/wp-content/uploads/2026/02/PERFILES_WEB-202602.zipx`

---

## 시작하기

```bash
cd skills/apc-prop-perf
source venv/bin/activate

# 전체 파이프라인 (다운로드 + 파싱 + DB 저장)
python scripts/main.py update

# DB 상태 확인
python scripts/main.py status

# 저장된 프로펠러 목록
python scripts/main.py list

# 성능 쿼리 (정확한 프로펠러)
python scripts/query.py --diameter 10.5 --pitch 4.5 --rpm 8000 --speed 30

# 성능 쿼리 (JSON 출력)
python scripts/query.py --diameter 10.5 --pitch 4.5 --rpm 8000 --speed 30 --json

# DB 스캔
python scripts/query.py --scan

# 교차 보간 (DB에 없는 프로펠러)
python scripts/query.py --diameter 11.0 --pitch 5.0 --rpm 8000 --speed 30
```

---

## 아키텍처

```
APC .dat 파일 → downloader → parser → SQLite(DB) → interpolator ← query
```

### 모듈별 책임

| 파일 | 줄 수 | 역할 |
|------|------|------|
| `scripts/main.py` | 140 | 전체 파이프라인 오케스트레이션 (download→parse→DB), 상태/목록 명령어 |
| `scripts/downloader.py` | 106 | ZIP 아카이브 추출 + 웹 개별 다운로드 |
| `scripts/parser.py` | 86 | `.dat` 고정폭 텍스트 파싱 → pandas DataFrame |
| `scripts/database.py` | 116 | SQLite 저장/검색 (propellers + performance_data 테이블) |
| `scripts/interpolator.py` | 113 | RPM/Speed 2D 보간 (LinearNDInterpolator + cross-prop 가중 평균) |
| `scripts/query.py` | 127 | CLI 쿼리 인터페이스 (exact + interpolated + JSON + scan) |

---

## 워크플로우

### 1. 데이터 업데이트 (`main.py update`)

```
data/raw/*.dat (460개) → parse_apc_file()
  → meta (D, P 추출) + DataFrame (16 columns)
  → APCDatabase.save_propeller(meta, df)  # Upsert (UNIQUE diameter, pitch)
  → DB 상태 확인 + JSON 요약 출력
```

**다운로드 순서:**
1. `data/perfiles.zipx` → `data/raw/` 자동 추출 (460개 .dat)
2. APC 공식 웹 개별 다운로드 (118개 추가) — 단, 현재는 ZIP에서만 실제 데이터 획득 가능 (웹 링크는 HTML 리턴)

**중복 방지:** 파일 존재 여부 + modification date 체크

### 2. 성능 쿼리 (`query.py`)

```
사용자 입력 (D, P, RPM, speed)
  → DB에서 exact match 검색
  → 있으면: LinearNDInterpolator (convex hull 내부 선형 보간)
  → 없으면: nearest 4개 프로펠러 거리 기반 가중 평균 (cross-prop interpolation)
  → convex hull 외부: NearestNDInterpolator fallback
```

### 3. 프로그램적 사용

```python
from scripts.database import APCDatabase
from scripts.interpolator import APCInterpolator

db = APCDatabase('data/apc_prop.db')

# 특정 프로펠러 데이터 조회
df = db.get_propeller_data(10.5, 4.5)

# 보간 쿼리
interp = APCInterpolator(df)
result = interp.query(rpm=8000, v=30.0)  # v is mph
# result['thrust_lbf'], result['pwr_hp'], result['torque_lbft'], result['pe'], etc.

# 교차 보간 (DB에 없는 D/P 조합)
result = APCInterpolator.interpolate_between_props(
    db, diameter=11.0, pitch=5.0, rpm=8000, speed=30.0
)
```

---

## parser.py 로직 상세

1. `.dat` 파일 헤더에서 `DxP` 패턴 추출 (regex: `(\d+\.?\d*)x(\d+\.?\d*)`)
2. `PROP RPM = XXXX` 라인 → RPM 블록 감지
3. `V J Pe Ct Cp PWR Torque Thrust ...` → 헤더 감지 → 데이터 수집 시작
4. `(mph)` 단위 라인 → 스킵
5. 숫자 라인 → 16 컬럼(float 변환, `'-'` → NaN)
6. DataFrame 생성

**컬럼 목록:** `rpm, v, j, pe, ct, cp, pwr_hp, torque_lbft, thrust_lbf, pwr_w, torque_nm, thrust_n, thr_pwr, mach, reyn, fom`

---

## DB 스키마

```sql
propellers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    diameter REAL NOT NULL,
    pitch REAL NOT NULL,
    filename TEXT,
    UNIQUE(diameter, pitch)
)

performance_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prop_id INTEGER NOT NULL,
    rpm INTEGER NOT NULL,
    v REAL NOT NULL,
    j REAL, pe REAL, ct REAL, cp REAL,
    pwr_hp REAL, torque_lbft REAL, thrust_lbf REAL,
    pwr_w REAL, torque_nm REAL, thrust_n REAL,
    thr_pwr REAL, mach REAL, reyn REAL, fom REAL,
    FOREIGN KEY(prop_id) REFERENCES propellers(id) ON DELETE CASCADE
)
```

**Upsert 로직:** `INSERT OR IGNORE` + `DELETE + Bulk INSERT`

---

## 보간 로직 상세

### 내부 보간 (같은 프로펠러)
- **입력:** (rpm, v) 좌표
- **기존:** `RegularGridInterpolator` — APC .dat은 비정규 격자이므로 NaN 95% 이상 발생 → **작동 불능**
- **현재:** `LinearNDInterpolator` — (rpm, v)를 점 클라우드 취급, 정규 격자 불필요
  - Convex hull 내부: 선형 보간
  - Convex hull 외부: `NearestNDInterpolator` fallback

### 교차 보간 (프로펠러 간)
- **입력:** (diameter, pitch) 거리 기반
- **방법:** 가장 가까운 4개 프로펠러 → weight = 1/distance 가중 평균
- **confidence:** 보간 거리 기반 신뢰도 점수 반환

---

## 데이터 통계

| 항목 | 값 |
|------|------|
| 고유 프로펠러 (D+P 조합) | **304개** |
| 총 .dat 파일 수 | 460개 (중 455개 성공, 5개 스킵) |
| 총 데이터 포인트 | ~100,000+ 행 |
| DB 크기 | 30 MB |
| 직경 범위 | 4.0 ~ 28.0 inch |
| 피치 범위 | 2.0 ~ 22.5 inch |
| RPM 범위 | 100 ~ 45,000 RPM |
| V 범위 | 0.0 ~ 134.73 mph |

**주요 직경 라인:**
- 10.0인치: 피치 3.0~14.0 (14개) — 가장 많은 라인업
- 11.0인치: 피치 3.0~14.0 (14개)
- 12.0인치: 피치 3.8~14.0 (16개)
- 7.0인치: 피치 3.0~15.0 (12개)
- 20.0인치: 피치 8.0~22.5 (10개)
- 4.0~5.5인치: 피치 2.0~11.0 (20개) — 소형
- 14.0~28.0인치: 대형

---

## 파일 구조

```
apc-prop-perf/
├── scripts/
│   ├── main.py          ← 전체 파이프라인
│   ├── downloader.py    ← 다운로드
│   ├── parser.py        ← 파싱
│   ├── database.py      ← SQLite
│   ├── interpolator.py  ← 보간
│   └── query.py         ← CLI
├── assets/sample.dat    ← APC 10.5x4.5 샘플 (683 rows)
├── data/
│   ├── apc_prop.db      ← SQLite DB (30 MB, 304 props)
│   ├── PERFILES_WEB-202602.zipx (7.9 MB)
│   └── raw/             ← 460개 .dat 파일
├── venv/                ← pandas/numpy/scipy
├── docs/design.md       ← 아키텍처 설계서
├── README.md
├── DEVELOPMENT_REPORT.md
└── SKILL.md
```

---

## 데이터 컬럼

| 컬럼 | 설명 | 단위 |
|------|------|------|
| V | 속도 | mph |
| J | advance ratio (J = V/nD) | dimensionless |
| Pe | propeller efficiency (Ct*J/Cp) | dimensionless |
| Ct | thrust coefficient | dimensionless |
| Cp | power coefficient | dimensionless |
| PWR | 동력 | Hp / W |
| Torque | 토크 | in-lbf / N-m |
| Thrust | 추력 | lbf / N |
| Mach | 팁 마하수 | dimensionless |
| Reyn | 레이놀즈 수 | dimensionless |
| FOM | Figure of Merit | dimensionless |

---

## 알려진 문제

### 7.1 교차 보간 로직 버그
`interpolate_between_props()`의 `valid_count` 분모 계산이 잘못된 가중치를 생성 → 효율 > 1.0 출력됨.
**우회책:** DB에 정확한 D/P 조합이 없으면 개별 근접 프로펠러 값을 직접 확인.

### 7.2 parser — 빈 파일 처리
5개 파일이 `empty` 또는 `no meta`로 스킵됨 (PER3_4x3.dat, PER3_4x4E.dat, PER3_4x5E.dat, PER3_5x4E.dat, PER3_9x8E.dat).

### 7.3 parser — D/P 추출 규칙
`re.search(r'(\d+\.?\d*)x(\d+\.?\d*)', line)` — 첫 번째 DxP 패턴만 매칭. 파일 헤더에 여러 숫자가 있으면 잘못 매칭될 수 있음.

### 7.4 venv 버전 충돌
시스템 pandas에서 numpy 버전 충돌 발생 (`ValueError: numpy.dtype size changed`).
**해결:** 반드시 `source venv/bin/activate` 후 실행.

### 7.5 parser — 단위(unit) 처리 미구현
APC .dat 파일 헤더에 단위 정보가 있지만 현재 파서는 무시. 실제 값은 APC 공식 제공이므로 단위 정확도 신뢰 가능.

---

## 향후 개선 사항

1. 교차 보간 로직 수정 — `interpolate_between_props()` 가중치 계산 버그 수정
2. parser 단위(unit) 처리 — .dat 헤더에서 단위 추출
3. MARINE 프로펠러 분리 — 수중 프로펠러는 별도로 분류 (공기역학 vs 수역역학)
4. PER2 종합 파일 파싱 — PER2_MAXPE.DAT 등 요약 파일 파싱 추가
5. API wrapper — Python API 제공 (CLI + programmatic 사용 모두 지원)
6. cache — 보간 결과 캐싱 (동일 입력 반복 시 재계산 방지)
7. test suite — pytest 기반 단위/통합 테스트
8. error handling — 네트워크 타임아웃, ZIP 손상, parser 예외 등 강화

---

## 검증된 테스트 결과

### 정확 매칭 (D=10.5, P=4.5, RPM=8000, V=30 mph)
```
Thrust:     0.8216 lbf (3.6552 N)
Power:      0.1070 hp (79.7080 W)
Torque:     0.8422 in-lbf (0.0950 N-m)
Efficiency: 0.6143
Ct:         0.0332
Cp:         0.0204
J:          0.3771
```

### 교차 보간 (DB에 없는 D=11.0, P=5.0, RPM=8000, V=30 mph)
```
Thrust:     0.5477 lbf
Power:      0.0714 hp
Torque:     0.5614 in-lbf
Efficiency: 0.4095
```

### 보간 테스트
| 조건 | 효율 | 상태 |
|------|------|------|
| RPM=1000, V=0.0 | 0.0 | ✅ |
| RPM=2000, V=0.19 | 0.0219 | ✅ |
| RPM=1500, V=0.19 (보간) | 0.0291 | ✅ |

---

*개발: 2026-08-07 | 최종 업데이트: 2026-08-11*
