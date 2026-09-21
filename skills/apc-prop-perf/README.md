# APC Propeller Performance Data

APC Propeller `.dat` 성능 데이터를 다운로드, 파싱, SQLite 저장, 보간하는 도구입니다.

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

## 모듈 구조

| 파일 | 역할 |
|------|------|
| `scripts/main.py` | 전체 파이프라인 (다운로드→파싱→DB), 상태/목록 명령어 |
| `scripts/downloader.py` | ZIP 아카이브에서 .dat 추출 + 웹 개별 다운로드 |
| `scripts/parser.py` | `.dat` → pandas DataFrame (고정폭 텍스트 파싱) |
| `scripts/database.py` | SQLite 저장/검색 (propellers + performance_data 테이블) |
| `scripts/interpolator.py` | RPM/Speed 보간 (LinearNDInterpolator + cross-prop 가중 평균) |
| `scripts/query.py` | CLI 쿼리 인터페이스 (exact + interpolated + JSON + scan) |

## 데이터 컬럼

- V (mph): 속도
- J: advance ratio (J = V/nD)
- Pe: propeller efficiency (Ct*J/Cp)
- Ct: thrust coefficient
- Cp: power coefficient
- PWR: 동력 (Hp / W)
- Torque: 토크 (in-lbf / N-m)
- Thrust: 추력 (lbf / N)
- Mach: 팁 마하수
- Reyn: 레이놀즈 수
- FOM: Figure of Merit

## DB 스키마

```sql
propellers (id, diameter, pitch, filename)
performance_data (id, prop_id, rpm, v, j, pe, ct, cp, pwr_hp, torque_lbft,
                   thrust_lbf, pwr_w, torque_nm, thrust_n, thr_pwr, mach, reyn, fom)
```

## 보간 방식

- **정확 매칭**: DB에 있는 프로펠러 → LinearNDInterpolator (convex hull)
- **교차 보간**: 가장 가까운 4개 프로펠러 → 거리 기반 가중 평균 (confidence 점수 제공)
- **fallback**: convex hull 외부 → NearestNDInterpolator

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
├── assets/sample.dat    ← 샘플 데이터
├── data/
│   ├── apc_prop.db      ← SQLite DB
│   ├── raw/             ← 다운로드 원본 .dat
│   └── perfiles.zipx    ← APC 공식 ZIP 아카이브
├── venv/                ← Python 환경
├── docs/design.md       ← 아키텍처 설계서
└── README.md
```
