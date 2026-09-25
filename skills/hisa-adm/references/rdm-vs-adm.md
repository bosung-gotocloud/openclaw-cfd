# RDM vs ADM (OpenFOAM v2512 fvOptions 내장)

## 핵심 차이
| 항목 | ADM (actuationDiskSource) | RDM (rotorDiskSource) |
|---|---|---|
| 모델 | 평균력 sink (Ct, Cp) | Blade Element (Cl/Cd 곡선) |
| 회전 | 없음 — 추력 방향만 | `rpm`, `nBlades`, `twist` |
| 기하학 | `diskCentre`, `diskDir`, `diskArea` | `origin`, `axis`, `tipEffect` |
| 날개 | 없음 | `blade { data: (r, chord, twist) }` |
| airfoil | 없음 — Ct/Cp 직접 입력 | `profileModel` (lookup table: AOA vs Cl/Cd) |
| sink flag | **sink=true 필수** (propeller) | 없음 — `rpm` 부호로 방향 결정 |

## RDM fvOptions 예시 (ADM diskCentre/diskDir 매핑)
```
rotorDisk
{
    type            rotorDiskSource;
    active          on;

    fields          (U);

    // ADM diskCentre ↔ RDM origin
    origin          (3.2 0.0 0.0);

    // ADM diskDir ↔ RDM axis (thrust 방향)
    axis            (-1 0 0);

    // diskDir과 thrust가 수직 → rpm 양수 = diskDir 반대방향 유동
    rpm             1500;

    nBlades         2;

    // ADM diskArea = π×R² ↔ RDM은 tipEffect로 반경 비율
    tipEffect       0.96;    // [0,1] — 팁에서 lift=0

    // 날개 형상 (반경 증가순)
    blade
    {
        data
        (
            (radius  chord   twistDeg)
            (0.10    0.050   0.0)
            (0.20    0.060   10.0)
            (0.30    0.070   15.0)
            (0.35    0.050   20.0)
        );
    }

    profileModel
    {
        type        lookup;
        // (AoA[deg]  Cl  Cd) — AOA 증가순
        data
        (
            (-5  0.00  0.02)
            ( 0  0.10  0.01)
            ( 5  0.18  0.015)
            (10  0.25  0.025)
            (15  0.30  0.045)
        );
    }
}
```

## ADM → RDM 파라미터 변환 규칙
1. **rpm 단위**: ADM의 `Ct/Cp constant` → RDM은 `rpm`을 rad/s 직접 입력
   (ADM: 1500 rpm = 157.08 rad/s)
2. **기하학**: `diskCentre` → `origin`, `diskDir` → `axis`
3. **tipEffect**: ADM `diskArea` (반지름²) → RDM `tipEffect` (반경 비율)
4. **날개 형상**: ADM 없음 → RDM `blade.data` (chord, twist)
5. **airfoil**: ADM 없음 (Ct/Cp) → RDM `profileModel.data` (Cl/Cd vs AOA)
6. **sink flag**: ADM `sink=true` → RDM `rpm` 부호 (양수=正向)

## 선택 기준
- **ADM**: 프로펠러 추력 시뮬레이션, Ct/Cp 계수만 필요, 날개 형상 무시
- **RDM**: 프로펠러 상세 해석, blade element + airfoil curve, rpm/twist 필요
