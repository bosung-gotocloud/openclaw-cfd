---
name: stl-viewer
description: Dash+Plotly interactive STL 3D viewer with slice cross-sections, tip detection (DBSCAN), TOL slider, BBox/CoM/projection area, and CSV export.
---

# stl-viewer — Interactive STL Slice + 3D Viewer

## Description

Dash + Plotly 기반 웹 애플리케이션으로 STL 파일을 3D로 렌더링하고 X/Y/Z 슬라이스 교차면을 실시간으로 시각화합니다.

## 주요 기능

- **3D 뷰어**: Plotly Mesh3d (WebGL)로 STL 메쉬 3D 렌더링
  - face color: `#888888` (gray) — iso 뷰에서 tip(blue)과 식별성 향상
  - line color: `#666666` (dark gray), width 0.5px
  - `flatshading=True`, opacity 0.5
- **슬라이스 교차면**: X/Y/Z 축 슬라이더로 실시간 단면 추출
  - shapely Polygon 기반 contour 추출
  - MultiPolygon 처리 포함
  - 채우기: `rgba(100,149,237,0.35)`, 테두리: navy 2px
- **🎯 Find Tip**: 다방향 2D projection + DBSCAN으로 tip 자동 감지
- **TOL 슬라이드**: 0.01 ~ 0.99 (step 0.01), default 0.5 (미터 단위)
  - 슬라이드 이동 시 tol 재계산 → tip 재검출 → 3D 뷰/팁 목록 실시간 갱신
- **BBox / CoM**: Bounding box, 질량중심 자동 계산
  - watertight mesh: `trimesh.center_mass` 사용
  - non-watertight: face area-weighted center of mass 직접 계산
- **Projection 면적**: XY/XZ/YZ 평면 투영 면적 계산 (shapely unary_union)
- **💾 Export Tips**: Find Tip 결과의 tip 포인트를 `.csv` 파일로 다운로드
  - 버튼 클릭 시 `{stlname}_tip_points.csv` 저장
  - Dash `dcc.download`로 브라우저 자동 다운로드
  - CSV 포맷: `x,y,z` (comma-separated, 6 decimal places)
- **파일 업로드**: Drag & Drop 또는 클릭으로 STL 파일 업로드
- **↺ Reset**: tip 데이터 클리어 + UI 전체 초기화

## Dependencies

```
dash
plotly
trimesh
shapely
numpy
scipy
scikit-learn
networkx
```

## Usage

**STL 파일이 있는 디렉토리에서 실행하세요.**

```bash
cd /path/to/your/stl/file/
python3 -m venv venv && source venv/bin/activate
pip install dash plotly trimesh shapely numpy scipy networkx scikit-learn
cp skills/stl-viewer/web-stl-viewer.py .
python web-stl-viewer.py your_file.stl
```

브라우저에서 `http://0.0.0.0:8051/` 접속

## Deployment

1. STL 파일이 있는 디렉토리로 이동
2. 가상환경 생성 + 의존성 설치
3. `skills/stl-viewer/web-stl-viewer.py` 복사 후 실행
4. 브라우저 열기

> ⚠️ **venv 위치**: 각 case 디렉토리마다 독립적인 venv를 생성하세요. skills/ 아래에 venv를 저장하지 마세요.

## Architecture

- **Frontend**: Dash (Flask-based web framework) + Plotly.js
- **Mesh Processing**: trimesh (STL 로드, section, center_mass)
- **Projection Calculation**: shapely (face projection → unary_union 면적)
- **3D Rendering**: Plotly Mesh3d (WebGL 기반, flat shading) + Scatter3d (tip markers)
- **Slice Rendering**: Plotly Scatter (closed polygon fill)
- **Tip Detection**: scikit-learn DBSCAN clustering (multi-direction projection 기반 tip 포인트 감지)
- **Callback 구조**: 단일 unified callback (30 outputs) — `callback_context.triggered`로 trigger 판별
  - triggered_id 순서: file-upload → axis → slider → find-tip → export-tip → reset → tol-slider → default

### Tip Detection Algorithm — 상세 로직

```
find_tip_points(mesh, tol=0.5)
```

**전체 흐름:**

1. **3방향 projection** — YZ, XZ, XY 평면에 vertex를 2D projection
2. **face centroid 기반 radial thresholding** — 30%, 50%, 70th percentile에서 외곽 vertex 추출
3. **DBSCAN clustering** — 각 projection에서 radial peak cluster 탐지
4. **cluster peak selection** — 각 cluster에서 radial이 최대인 vertex를 tip candidate
5. **TOL 기반 deduplication** — tol 거리 이내의 중복 tip 제거
6. **최대 20개 tip 반환**

**단계별 상세:**

#### Step 1: 3방향 projection

```python
for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
```

- YZ (Y,XZ → XZ (XZ (X,Y (X,Y → XY (X,Y)

각 projection에서 2차원으로 압축. 3방향 모두 필요한 이유: 단일 방향 projection에서는 tip이 중첩되거나 가려질 수 있음 (예: Z축 방향 tip은 XY projection에서 유일하게 탐지됨).

#### Step 2: Face centroid 기반 radial 계산

```python
centroids = vertices[faces].mean(axis=1)   # 각 face의 centroid
verts_2d = vertices[:, [axis1, axis2]]     # projection된 vertex 좌표
origin_2d = centroids[:, [axis1, axis2]].mean(axis=0)  # centroid 평균
radial = np.linalg.norm(verts_2d - origin_2d, axis=1)  # origin으로부터의 거리
```

radial = origin(centroid 평균)으로부터 vertex까지의 2D 거리. 이 distances → 외곽 vertexほど radial이 큼.

#### Step 3: Radial percentile thresholding

```python
for pct in [30, 50, 70]:
    threshold = np.percentile(radial, pct)
    high_mask = radial > threshold
```

30%, 50%, 70% percentile에서 radial이 큰 vertex만 필터. 다중 threshold가 필요한 이유:
- 30%: 넓은 범위로 small protrusion 탐지
- 50%: 중간 범위
- 70%: 매우 외곽의 prominent tip 탐지
→ 서로 다른 크기/위치의 tip을 모두 잡기 위함.

#### Step 4: Downsampling (large mesh용)

```python
if len(high_indices) > 5000:
    rng = np.random.RandomState(42)
    idx = rng.choice(len(high_indices), 5000, replace=False)
    high_coords = high_coords[idx]
    high_indices = high_indices[idx]
    high_radial = high_radial[idx]
```

5000개 초과 시 fixed seed(42)로 5000개 downsample. DBSCAN 성능 최적화.

#### Step 5: DBSCAN Clustering

```python
scale = np.std(high_coords, axis=0)          # 각 축의 표준편차
scale[scale < 1e-6] = 1.0                    # zero-std 축 보호
features = high_coords / scale               # normalization
eps_val = 0.3 / max(scale.min(), 1e-6)       # adaptive eps
eps_val = max(0.001, min(eps_val, 0.999))    # eps range 제한 (0.999 max)
clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
```

- **Normalization**: 각 축의 std로 스케일링 → isotropic clustering
- **Adaptive eps**: `eps = 0.3 / scale.min()` — 스케일에 따라 동적 조정
- **eps max = 0.999** (critical): 너무 큰 eps → 모든 tip이 하나의 cluster로 merge → tip 개수 적게 나옴
- **min_samples = 5**: 최소 5개 vertex가 모여야 하나의 cluster로 인정

#### Step 6: Peak selection per cluster

```python
for label in set(labels):
    if label == -1: continue   # noise cluster 제외
    cm_mask = labels == label
    cluster_idx_2d = high_indices[cm_mask]
    cluster_radial = high_radial[cm_mask]
    peak_local = cluster_radial.argmax()   # radial이 최대인 인덱스
    peak_idx_3d = cluster_idx_2d[peak_local]
    tip_candidates.append(vertices[peak_idx_3d].copy())
```

각 cluster에서 radial이 가장 큰 vertex → 해당 cluster의 "tip"으로 채택. noise cluster(label=-1)는 무시.

#### Step 7: Deduplication by TOL

```python
tips = []
for t in tip_candidates:
    if not any(np.linalg.norm(t - q) < tol for q in tips):
        tips.append(t)
return tips[:20]
```

`tip_candidates` 전체를 순회. 기존 `tips`에 tol 거리 이내에 있는 점이 있으면 skip (중복 제거). 최대 20개까지 반환.

**TOL slider 동작:**
- 0.01: 매우 엄격한 dedup → 많은 tip 검출 (세밀한 protrusion 분리)
- 0.99: 매우 관대한 dedup → 적은 tip (근접 tip merge)
- 0.5 (default): 균형 잡힌 값

**Tip marker (3D 뷰):**
- Symbol: `circle` (closed circle)
- Color: `red` (`color='red'`)
- Size: `8px`
- Label: `tip N` (N=1,2,3,...)
- Position: marker top center (`textposition='top center'`)

## File Structure

```
stl-viewer/
├── SKILL.md              ← this file
├── web-stl-viewer.py     ← main application (updated 2026-08-14)
├── stl-rotate.py         ← STL rotation utility
├── find_tip.py           ← tip detection library
└── dummy.stl             ← test STL
```

## rotate.py — STL Rotation Utility

```bash
python rotate.py <stlfile.stl> <cx> <cy> <cz> <ix> <iy> <iz> <degree>
```
- `(cx, cy, cz)` — center of rotation
- `(ix, iy, iz)` — rotation axis (auto-normalized)
- `degree` — rotation angle in degrees

Output: `<stlfile>_<degree>.stl`

## Updates

### 2026-08-14 — ISO view coloring fix + SKILL.md finalize

**ISO view coloring:**
- STL face color: `#888888` (gray) — tip(blue)과 식별성 향상
- STL line color: `#666666` (dark gray), width 0.5px
- `flatshading=True` 적용
- tip marker: red circle 유지

**SKILL.md documentation update:**
- TOL slider: 0.01 ~ 0.99 (step 0.01), default 0.5 (미터 단위)
- Export format: `.csv` (not `.txt`) — `x,y,z` format
- Tip detection algorithm detailed documentation added

### 2026-07-04 — Export Tip CSV + Callback structure rewrite

**Export Tip CSV:**
- Export format `.txt` → `.csv`로 변경
- CSV 포맷: `x,y,z` (comma-separated, 6 decimal places)
- filename: `{stlname}_tip_points.csv`
- step-viewer와 동일한 export 로직으로 통일

**Callback structure rewrite:**
- 29 outputs → **30 outputs** (`download-tips` data 추가)
- `elif` 기반 → **early-return 방식**으로 rewrite
- step-viewer와 동일한 triggered_id 체크 순서: file-upload → axis → slider → find-tip → export-tip → reset → tol-slider → default
- 모든 분기가 정확한 30개 요소 튜플 반환

**TOL slider:** 0.01 ~ 0.99 (step 0.01) — STL 버전으로 복귀

### 2026-07-03 — Find Tip Algorithm Update

**Critical fixes:**
- **Projection direction**: YZ + XZ → YZ + XZ + XY (3방향)
  - XY projection 추가 → Z축 방향 tip 놓침 방지
- **DBSCAN eps max**: 100.0 → 0.999
  - 100.0 → clustering이 모든 tip을 한 클러스터로 합침 → tip 개수 적게 나옴
  - 0.999 → tip separation 정상
- **TOL slider range**: 0.01 ~ 0.99 (step 0.01), default 0.5
  - 미터 단위 geometry에서 0.99m max는 tip merge가 안 됨

### 2026-06-24 — TOL Slide + Marker Fix

**New features:**
- **TOL 슬라이드**: 0.01 ~ 0.99 (step 0.01), default 0.5
- 슬라이드 이동 시 tol 재계산 → tip 재검출 → 3D 뷰/팁 목록 실시간 갱신
- **Tip marker**: 'x' → red filled circle (closed circle, color='red')

**Callback fixes:**
- 29 outputs 정확한 tuple length (모든 분기)
- tol-slider triggered block에서 axis 변수 정의 순서 수정
- dcc.Slider style → className (Dash 호환)
- no_tuple 오타 → no_update 전량 수정

### 2026-06-23 — Find Tip 기능 추가

- **🎯 Find Tip 버튼**: 다방향 2D projection + DBSCAN clustering 기반 tip 감지
- **Tip 표시**: red filled circle marker + "tip N" label, 좌측 패널 tip 목록 출력
- **Reset 버튼**: tip 데이터 클리어 + UI 전체 초기화
- 단일 unified callback (29 outputs) — trigger별 분기

### 2026-06-03 — UI 최종 확정

- 왼쪽 패널 출력 형식 통일 (폰트 크기 14, bold)
- 슬라이더 ↔ 버튼 상호작용
- 활성 버튼: `#4a90d9` 배경, `#2c6fbb` 테두리, 흰색 글자
- 비활성 버튼: `#f5f5f5` 배경, `#ddd` 테두리, 회색 글자

### 2026-05-31 — 로딩 상태 표시 + 업로드 리셋

### 2026-05-25 — Callback 분리 및 UI 개선

## Notes

- `is_watertight`: trimesh strict check
- non-watertight mesh: face area-weighted center of mass 직접 계산
- `flatshading=True`: Mesh3d flat shading — face별 조명 계산 (iso 뷰에서 면 간 경계 명확)
- DBSCAN eps max 0.999: 이 값이 critical. 1.0 이상 → 모든 점이 같은 cluster → tip 탐지 실패
