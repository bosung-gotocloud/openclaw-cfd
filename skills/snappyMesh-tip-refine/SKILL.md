# snappyMesh-tip-refine 스킬 — 전체 설명

---

## 1. 이 스킬은 무엇인가?

**STL 파일** 하나를 입력받아, OpenFOAM의 **snappyHexMesh** 메쉬 생성 case를 자동 만들어주는 스킬입니다. 가장 큰 특징은 **tip wake line refinement** — 날개 팁 등에서 나는 와류 wakes를 정확하게 포착하기 위해, tip point CSV를 자동으로 찾아 +X 방향으로 가는 얇은 refine box들을 만들어준다는 점입니다.

tip CSV가 없으면 기존 snappyMesh와 동일하게 일반 refine-box-only 모드로 작동합니다 (backward compatibility).

---

## 2. 사용 방법 (3단계 워크플로우)

### Step 0: 스크립트 복사

```bash
cp skills/snappyMesh-tip-refine/scripts/*.py <target_dir>/
```

메쉬를 생성할 대상 디렉토리에 스크립트 3개를 복사합니다. STL 파일과 tip CSV 파일도 그 디렉토리에 있어야 합니다.

### Step 1: `calculate_mesh_params.py` — 파라미터 계산

```bash
python3 calculate_mesh_params.py LC62-50H.stl
```

이 스크립트가 하는 일:
1. **STL 바운딩 박스 읽기** — STL 파일 (binary 또는 ascii) 에서 xmin/xmax/ymin/ymax/zmin/zmax 추출
2. **물치 크기 계산** — xl = xmax-xmin (X 방향 길이)
3. **Far box 계산** — 물체를 감싸는 외부 영역 (X: 10×xl, Y: 5×yl, Z: 10×zl)
4. **Refine box 계산** — 메쉬를 조일 영역 (X: 0.5×far_x, Y: 2×yl, Z: 2×zl)
5. **메쉬 사이즈 계산** (아래 섹션 3 참조)
6. **tip CSV 자동 감지** — `{basename}_tip_points.csv`가 있으면 로드, 없으면 refine-box-only 모드
7. **JSON 생성** — `{basename}_mesh_args.json` 파일로 모든 파라미터 저장
8. **실행 중지** — 이 시점에서 스크립트가 멈춤. 사용자에게 파라미터 확인 요청

**⚠️ 여기서 실행이 멈춥니다. 사용자가 승인해야 다음 단계로 갈 수 있습니다.**

## ⏱️ 실행 시간 가이드 (exec timeout)

blockMesh + snappyHexMesh 메쉬 생성은 **수 분 ~ 수 시간** 소요 (tip refine, cell 수에 따라). `exec` 호출 시 다음 규칙 적용:

| 작업 | exec 설정 |
|------|-----------|
| `calculate_mesh_params.py` (Stage 1, 파라미터 계산) | `timeoutSeconds: 120` (빠름) |
| `block_mesh.py` (blockMesh 실행) | `timeoutSeconds: 300` |
| `snappy_mesh.py` (snappyHexMesh) | **`background: true` + `yieldMs: 60000`** — 1분 후 백그라운드로, `process`로 상태 확인 |
| `reconstructParMesh` (재구성) | `timeoutSeconds: 600` |

- `background: true`로 즉시 백그라운드로 → 세션 블로킹 방지 (exec 기본 timeout ~2분 초과 시 SIGTERM)
- `process(action=poll)`로 진행 상황 확인, 완료 시 `process(action=log)`로 로그 확인

### Step 2: `block_mesh.py` — blockMesh 실행

```bash
python3 block_mesh.py LC62-50H_mesh_args.json
```

이 스크립트가 하는 일:
1. 템플릿 디렉토리 복사
2. blockMeshDict 수정 — far box corner, cell 수 (max_size 기반), far box 면 정의
3. `blockMesh` 실행
4. controlDict 고정 — writeControl none, writeFrequency 0 (메쉬 단계에서 output 불필요)


```bash
```

이 스크립트가 하는 일 (전체 순서):
1. **STL 복사** — `constant/triSurface/`로 복사
2. **OBJ 생성** — `surfaceConvert` 시도 → 실패 시 수동 OBJ 생성
3. **snappyHexMeshDict 수정** — refine box, wake line searchableBox, surface/size 파라미터 등 템플릿 치환
4. **boundary patch 확인** — `constant/polyMesh/boundary`에서 실제 patch 이름 조회
5. **decomposePar 실행** — parallel 분할
6. **snappyHexMesh parallel 실행** — mpirun
7. **reconstructParMesh** — parallel 결과 합치기
8. **STL patch type wall 강제 변환** — snappyMesh 후 type이 patch로 바뀌므로 wall로 되돌림
9. **processor 디렉토리 삭제**
10. **checkMesh 자동 실행** — 메쉬 품질 검사
11. **case.foam 생성** — OpenFOAM case marker

---

## 3. 메쉬 사이즈 계산 로직 — 핵심

이 스킬의 가장 중요한 부분입니다. **Top-Down approach** — surface cell size를 목표로 삼아 위에서 아래로 레벨을 역산합니다.

### 단계별 계산

```
Step 1: max_size (가장 큰 cell)
 max_size = max(box_dx, box_dy, box_dz) / 50
 물체 X 길이의 20% → coarest mesh

Step 2: target_surf_size (surface cell size 목표)
 target_surf_size = xl × 0.005
 물체 X 길이의 0.5%

Step 3: surf_size_level (Level 찾기)
 level 0부터 20까지 탐색:
 cell_at_level = max_size × (0.5)^level
 diff = |cell_at_level - target_surf_size|
 diff가 최소가 되는 level → surf_size_level

Step 4: surf_size 계산
 surf_size = max_size × (0.5)^surf_size_level

Step 5: min_size_level
 min_size_level = surf_size_level + 2

Step 6: min_size 계산
 min_size = surf_size / 4

Step 7: refine_size_level
 refine_size_level = 2 (고정)

Step 8: max_level, feature_level
 max_level = min_size_level
 feature_level = min_size_level
```

### Refinement Level 전체 그림

```
Level 0 → max_size (coarest, 레벨 0)
Level 1 → max_size/2
Level 2 → max_size/4
...
Level N → surf_size (surface cell size)
...
Level N+2 → min_size (volume min cell size)

refine_box → level 2 (cell_size = min_size × 4)
wake line → level = surf_size_level (cell_size = surf_size)
feature edge → level = feature_level (max_level과 동일)
```

### 왜 이렇게 했는가?

기존에는 **BL 두께 T**를 기준으로 min_size를 정하고, 그 역으로 surf_size를 구하는 방식でした. 하지만 BL 두께는 CFD 해석 조건 (y+ 등) 에 따라 달라지는 값이고, 메쉬 사이즈와는 독립적입니다.所以现在:

- **메쉬 사이즈**: 물치 크기와 surface resolution 목표만으로 계산
- **경계층 (BL)**: 사용자가 y+를 기준으로 사전에 결정 → h1, growth, layers로 직접 지정
- T는 계산하지도 않고 JSON에도 포함하지 않습니다

### 경계층 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|------|
| firstCellHeight (h1) | 0.0001 m | 첫 경계층 cell 높이 |
| expansionRatio (growth) | 1.2 | 층별 확장 비율 |
| numberOfLayers (layers) | 10 | 경계층 층 수 |

이 값들은 사용자가 필요시 JSON에서 직접 수정하거나 스크립트에서 재계산할 수 있습니다. addLayersControl은 **firstAndExpansion** 방식을 사용합니다.

---

## 4. Tip Wake Line Refinement

### CSV 자동 감지

```
{basename}_tip_points.csv
```

를 STL 파일이 있는 디렉토리에서 자동으로 찾습니다.

**CSV 포맷:**
- `x,y,z` header 있음 → header 자동 감지 (첫 필드가 영문자) 후 skip
- header 없음 → 모든 row를 데이터로 처리

### Wake Line searchableBox 생성

CSV의 각 tip point마다 +X 방향으로 가는 얇은 box를 만듭니다.

```
Wake box 크기:
 X 방향: tip_x → refine_box xmax (물체 wake downstream)
 Y 방향: tip_y ± (surf_size × 5) (총 폭 = 10×surf_size)
 Z 방향: tip_z ± (surf_size × 10) (총 폭 = 20×surf_size)

wake_half_w = surf_size × 5   # Y 방향
wake_half_z = surf_size × 10  # Z 방향
min = (tip_x, tip_y - wake_half_w, tip_z - wake_half_z)
max = (refine_cx + refine_dx/2, tip_y + wake_half_w, tip_z + wake_half_z)
```

**Refinement level:**
- wake line level = surf_size_level
- wake line cell size = tip_wake_refine_size = surf_size
- wake_box와 refine_box가 겹치는 영역에서는 **더 작은 cell size가 적용됨**

### wake line 역할

날개 팁에서 떨어지는 와류는 매우 얇고 긴 구조입니다. wake line refinement은 이 와류가 지나는 경로를 높은 해상도로 메쉬링하여 와류 구조를 정확하게 포착합니다. Y로 10×surf_size, Z로 20×surf_size 폭을 주는 것은 와류의 확산을 충분히 커버하기 위함입니다.

---

## 5. JSON 스키마 구조

`calculate_mesh_params.py`가 생성하는 JSON의 주요 필드:

```json
{
 "base_name": "물체이름",
 "xl": 1.234, "yl": 0.567, "zl": 0.123, // STL 바운딩 박스
 "h1": 0.0001, "layers": 10, "growth": 1.2, // 경계층 (T 없음)

 // 메쉬 사이즈
 "max_size": 0.015824, // Level 0 (coarest)
 "surf_size": 0.006330, // surface cell size
 "min_size": 0.003165, // volume min cell size
 "surf_size_level": 5, // surface refinement level
 "min_size_level": 7, // min size level (= surf + 2)
 "max_level": 7, // max refinement
 "feature_level": 7, // feature edge refinement
 "refine_size_level": 2, // refine box level

 // Far box
 "box_dx": 12.34, "box_dy": 2.835, "box_dz": 1.23,
 "tx": -0.617, "ty": -0.284, "tz": 0.000,

 // Refine box
 "refine_dx": 6.17, "refine_dy": 1.134, "refine_dz": 0.246,
 "refine_cx": 0.617, "refine_cy": 0, "refine_cz": 0,
 "refine_tx": -0.009, "refine_ty": -0.425, "refine_tz": 0.000,
 "refine_mode": "inside",

 // Tip wake line (CSV 있는 경우만)
 "tip_csv_path": "/path/to/filename_tip_points.csv",
 "tip_points_count": 6,
 "tip_points": [{"x": -0.613, "y": -0.692, "z": -0.043}],
 "tip_wake_lines": [...],
 "tip_wake_refine_size": 0.006330,
 "wake_refine_level": 5
}
```

---

## 6. snappyMesh와 비교

| 항목 | snappyMesh | snappyMesh-tip-refine |
|---|---|------|
| 입력 | STL | STL + tip CSV (optional) |
| tip CSV 자동 감지 | ✗ | ✓ |
| Wake line refinement | ✗ | ✓ (searchableBox) |
| refine_size_level | min_size_level - 1 | **2** (고정) |
| surf_size_level | 6 (hardcoded) | **auto** (target closest) |
| BL 계산 | T 기반 | **y+ 기반, firstAndExpansion** |
| T in JSON | Yes | **No** |
| backward compat | — | CSV 없으면 기존 snappyMesh와 동일 |

---

## 7. Golden Rules

1. **Template 절대 수정 금지** — `assets/snappyHexMesh-case-template/`는 READ-ONLY
2. **JSON 직접 편집 금지** — 파라미터는 JSON에서 수동 조정 가능하지만 스크립트 수정은 안 됨
3. **calculate_mesh_params.py 실행 후 승인 필수** — 표를 보고 확인 → 승인 → 그 후에야 다음 단계
4. **절차 준수** — 계산 → 확인 → 승인 → 실행 (순서 위반 절대 금지)

---

## 8. 파일 구조

```
skills/snappyMesh-tip-refine/
├── SKILL.md ← 이 문서
├── scripts/
│ ├── calculate_mesh_params.py ← Stage 1: 파라미터 계산 + tip CSV 감지
│ ├── block_mesh.py ← Stage 2: blockMesh 실행
└── assets/
 └── snappyHexMesh-case-template/
 └── system/
 ├── blockMeshDict
 ├── snappyHexMeshDict ← wake line placeholder 포함
 ├── controlDict
 ├── decomposeParDict
 ├── fvSchemes
 └── fvSolution
```

---

## 9. 테스트 결과 (LC62-50H 예시)

| 단계 | 결과 |
|---|------|
| blockMesh | 50 × 27 × 17 = 22,950 cells |
| snappyHexMesh | 병렬 16proc 완료 |
| checkMesh | **OK** |
| 최종 메쉬 | ~1,007,848 cells |
| refine_box | level 2, cell_size=0.025m |
| wake_line×6 | level 5, cell_size=surf_size |
| STL patch | constant/triSurface/ ✅ |
| boundary | far + surface patch ✅ |

---

## 요약

이 스킬은 **STL 파일 하나**로 시작해서 **tip CSV 있으면 wake line refinement**까지 자동으로 해주는 snappyHexMesh case 생성 스킬입니다. 메쉬 사이즈는 **물치 크기의 0.5%를 surface target**으로 하고, 레벨을 위에서 아래로 역산합니다. BL 두께 T는 더 이상 계산에 포함되지 않으며, 경계층은 사용자가 y+를 기준으로 직접 결정합니다.

---

## ⚠️ mpirun 실행 방식 수정 (2026-09-09)

**문제:** `mpirun ... 2>&1 | tee log.snappyHexMesh` — pipe buffer(64KB)가 가득 차면 mpirun이 write blocked → hang → gateway SIGKILL

**수정 전:**
```bash
mpirun -np N snappyHexMesh -parallel 2>&1 | tee log.snappyHexMesh
```

**수정 후:**
```bash
mpirun -np N snappyHexMesh -parallel > log.snappyHexMesh 2>&1
```

**원인:** `os.system()` + `tee` 파이프에서 Python이 pipe buffer를 읽지 않아 쌓임 → write blocked → hang → SIGKILL
**해결:** `tee` 파이프 제거, 파일에 직접 redirect → pipe 없음, buffer 축적 없음
**수정 파일:** `snappy_mesh.py` (mpirun 호출 부분)

## 경계층 (addLayers) 안정화 설정 — 2026-09-21

`snappyMesh-elliptic-tip-refine`와 동일하게 경계층이 잘 쌓이도록
`assets/.../snappyHexMeshDict` template을 수정함 (backup: `snappyHexMeshDict.bak-20260921`).

### castellatedMeshControls
- `nCellsBetweenLevels 3 -> 5` — 급격한 배경 격자 해상도 변화로 인한 Layer Collapse 방지

### addLayersControls
- `maxThicknessToMedialRatio 15.0 -> 100.0` (국소 미세 셀 영역 두께 제약 해제)
- `maxFaceThicknessRatio 300.0 -> 1000.0` (배경 격자 대비 두께 제약 완화)
- `minFaceWeight -1`, `minVolRatio -1`
- `nBufferCellsNoExtrude 1 -> 0` (실패 지점 인접 셀 동반 삭제 방지)
- 스무딩/완화: `featureAngle 120 -> 180` (모든 날카로운 엣지 feature, LE edge snap 강화),
  `nRelaxIter 10 -> 50`, `nSmoothSurfaceNormals 1 -> 5`, `nSmoothThickness 10 -> 20`,
  `nSmoothNormals 3 -> 5`, `nMedialAxisIter 30 -> 50`, `nLayerIter 100 -> 200`, `nRelaxedIter 20 -> 50`
- relaxed: `minFaceWeight/minVolRatio 0.001 -> 0.0001` (`maxNonOrtho 95` 유지)

### meshQualityControls
- `maxNonOrtho 65 -> 85`, `maxInternalSkewness 4 -> 20`, `minVol 1e-13 -> 1e-15`
- `minDeterminant 0.001 -> 1e-5`, `minTwist 0.02 -> -1`
- `minFaceWeight 0.05 -> 0.0001`, `minVolRatio 0.01 -> 0.0001` (핵심)
- `minTetQuality 1e-9 -> 1e-15`, relaxed `maxNonOrtho 75 -> 95`

### 유의사항
- `expansionRatio`는 반드시 수치 (placeholder가 그대로 들어가면
  `FOAM FATAL IO ERROR: expected scalar value, found 'BASE_EXPANSION_RATIO'`)
- `relativeSizes false` + `thicknessModel firstAndExpansion`이면
  `firstLayerThickness`가 절대 길이(mm)로 적용됨
