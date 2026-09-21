# stl-viewer — Interactive STL Slice + 3D Viewer

## Description

Dash + Plotly 기반 웹 애플리케이션으로 STL 파일을 3D로 렌더링하고 X/Y/Z 슬라이스 교차면을 실시간으로 시각화합니다.

## 주요 기능

- **3D 뷰어**: Plotly Mesh3d (WebGL)로 STL 메쉬 3D 렌더링
- **슬라이스 교차면**: X/Y/Z 축 슬라이더로 실시간 단면 추출
- **🎯 Find Tip**: 다방향 2D projection + DBSCAN으로 tip 자동 감지
- **TOL 슬라이드**: 0.01 ~ 10.0 (step 0.1), default 5.0
- 슬라이드 이동 시 tol 재계산 → tip 재검출 → 3D 뷰/팁 목록 실시간 갱신
- **BBox / CoM**: Bounding box, 질량중심, 면적 자동 계산
- **Projection 면적**: XY/XZ/YZ 평면 투영 면적 계산
- **💾 Export Tips**: Find Tip 결과의 tip 포인트를 `.txt` 파일로 다운로드
  - 버튼 클릭 시 `/tmp`에 `{stlname}_tips.txt` 저장
  - Dash `dcc.download`로 브라우저 자동 다운로드
  - TXT 포맷: `Tip Export from {filename}`, `TOL: {value}`, `[N tips]`, `tip{i}: (x, y, z)`
- **파일 업로드**: Drag & Drop 또는 클릭으로 STL 파일 업로드
- **↺ Reset**: 전체 UI 초기화

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

```bash
cd /path/to/your/case/
cp skills/stl-viewer/web-stl-viewer.py .
python3 -m venv venv && source venv/bin/activate
pip install dash plotly trimesh shapely numpy scipy networkx scikit-learn
python web-stl-viewer.py your_file.stl
```

브라우저에서 `http://0.0.0.0:8051/` 접속

## Deployment

1. `skills/stl-viewer/web-stl-viewer.py` 를 대상 디렉토리에 복사
2. 해당 디렉토리에서 실행
3. 가상환경 생성 + 의존성 설치
4. 브라우저 열기

## Architecture

- **Frontend**: Dash (Flask-based web framework) + Plotly.js
- **Mesh Processing**: trimesh (STL 로드, section, center_mass)
- **Projection Calculation**: shapely (face projection → unary_union 면적)
- **3D Rendering**: Plotly Mesh3d (WebGL 기반, normals 자동 교정) + Scatter3d (tip markers)
- **Slice Rendering**: Plotly Scatter (closed polygon fill)
- **Tip Detection**: scikit-learn DBSCAN clustering (multi-direction projection 기반 tip 포인트 감지)
- **Callback 구조**: 단일 unified callback (29 outputs) — `callback_context.triggered`로 trigger 판별

### Tip Detection Algorithm

```python
def find_tip_points(mesh, tol=0.5):
    vertices = mesh.vertices; faces = mesh.faces
    tip_candidates = []

    # 1. 3방향 projection (YZ + XZ + XY)
    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
        # face centroid 기반 radial 계산
        centroids = vertices[faces].mean(axis=1)
        verts_2d = vertices[:, [axis1, axis2]]
        origin_2d = centroids[:, [axis1, axis2]].mean(axis=0)
        radial = np.linalg.norm(verts_2d - origin_2d, axis=1)

        # 30/50/70th percentile에서 radial peak candidate 추출
        for pct in [30, 50, 70]:
            threshold = np.percentile(radial, pct)
            high_mask = radial > threshold
            if high_mask.sum() == 0: continue
            high_coords = verts_2d[high_mask]
            high_indices = np.where(high_mask)[0]
            high_radial = radial[high_mask]

            if len(high_indices) < 10: continue

            # Performance: max 5000 points downsampling (fixed seed)
            if len(high_indices) > 5000:
                rng = np.random.RandomState(42)
                idx = rng.choice(len(high_indices), 5000, replace=False)
                high_coords = high_coords[idx]
                high_indices = high_indices[idx]
                high_radial = high_radial[idx]

            # DBSCAN clustering
            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale
            eps_val = 0.3 / max(scale.min(), 1e-6)
            eps_val = max(0.001, min(eps_val, 0.999))  # max 0.999 (critical fix)
            clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
            labels = clustering.labels_

            for label in set(labels):
                if label == -1: continue
                cm_mask = labels == label
                cluster_idx_2d = high_indices[cm_mask]
                cluster_radial = high_radial[cm_mask]
                peak_local = cluster_radial.argmax()
                peak_idx_3d = cluster_idx_2d[peak_local]
                tip_candidates.append(vertices[peak_idx_3d].copy())

    # Deduplication by TOL distance threshold
    tips = []
    for t in tip_candidates:
        if not any(np.linalg.norm(t - q) < tol for q in tips):
            tips.append(t)
    return tips[:20]
```

### Tip Marker

- **Symbol**: Closed circle (`symbol='circle'`)
- **Color**: Red (`color='red'`)
- **Size**: 8px
- **Label**: "tip N"

## File Structure

```
stl-viewer/
├── SKILL.md              ← this file
├── web-stl-viewer.py     ← main application (updated 2026-06-24)
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

### 2026-07-04 — Export Tip CSV + Callback 구조 rewrite

**Export Tip CSV:**
- Export format `.txt` → `.csv`로 변경
- CSV 포맷: `x,y,z` (comma-separated, 6 decimal places)
- filename: `{stlname}_tip_points.csv`
- step-viewer와 동일한 export 로직으로 통일

**Callback 구조 rewrite:**
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
- **TOL slider range**: 0.01 ~ 0.99 → 0.01 ~ 10.0, default 5.0
  - 미터 단위 geometry에서 0.99m max는 tip merge가 안 됨

### 2026-06-24 — TOL Slide + Marker Fix

**New features:**
- **TOL 슬라이드**: 0.01 ~ 10.0 (step 0.1), default 5.0
- 슬라이드 이동 시 tol 재계산 → tip 재검출 → 3D 뷰/팁 목록 실시간 갱신
- **Tip marker**: 'x' → red filled circle (closed circle, color='red')

**Callback fixes:**
- 29 outputs 정확한 tuple length (모든 분기)
- tol-slider triggered block에서 axis 변수 정의 순서 수정
- dcc.Slider style → className (Dash 호환)
- no_tuple 오타 → no_update 전량 수정

### 2026-06-23 — Find Tip 기능 추가

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
