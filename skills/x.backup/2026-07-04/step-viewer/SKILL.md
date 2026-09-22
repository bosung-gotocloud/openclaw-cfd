# step-viewer — Interactive STEP Slice + 3D Viewer

## Description

Dash + Plotly 기반 웹 애플리케이션으로 STEP 파일을 3D로 렌더링하고 X/Y/Z 슬라이스 교차면을 실시간으로 시각화합니다.
cadquery + OCP로 STEP 파일을 native parsing하고 mesh로 변환하여 처리합니다 (STL 변환 없음).

## 주요 기능

- **3D 뷰어**: Plotly Mesh3d (WebGL)로 STEP 메쉬 3D 렌더링
- **슬라이스 교차면**: X/Y/Z 축 슬라이더로 실시간 단면 추출
- **🎯 Find Tip**: 다방향 2D projection + DBSCAN으로 tip 자동 감지
- **💾 Export Tip CSV**: Find Tip 결과의 tip 포인트를 CSV 파일로 다운로드
  - 버튼 클릭 시 `/tmp` (또는 STEP 파일 디렉토리)에 `{stepname}_tip_points.csv` 저장
  - Dash `dcc.download`로 브라우저 자동 다운로드
  - CSV 포맷: `x,y,z` (6자리 소수점) — 파일 이름은 현재 로딩 중인 STEP 파일명 기반
  - 파일 업로드 시 `step_file` 변수가 함께 업데이트되어 export 파일명도 동적으로 변경
### TOL Slider

- **Range**: 0.01 ~ 10.0 (fixed)
- **Default**: 5.0 (half of max)
- **Ticks**: 0.01, 1.0, 5.0, 10.0
- **Step**: 0.1
- **BBox / CoM**: Bounding box, 질량중심, 면적 자동 계산
- **Projection 면적**: XY/XZ/YZ 평면 투영 면적 계산
- **↺ Reset**: 전체 UI 초기화
- **파일 업로드**: Drag & Drop 또는 클릭으로 STEP 파일 업로드

## Dependencies

```
cadquery
trimesh
dash
plotly
numpy
scipy
scikit-learn
networkx
shapely
```

## Usage

```bash
cd /path/to/your/case/
cp skills/step-viewer/web-step-viewer.py .
python3 -m venv venv && source venv/bin/activate
pip install cadquery dash plotly numpy scipy scikit-learn networkx shapely
python web-step-viewer.py your_file.step
```

브라우저에서 `http://0.0.0.0:8051/` 접속

## Deployment

1. `skills/step-viewer/web-step-viewer.py` 를 대상 디렉토리에 복사
2. 해당 디렉토리에서 실행
3. 가상환경 생성 + 의존성 설치
4. 브라우저 열기

## Architecture

- **Frontend**: Dash (Flask-based web framework) + Plotly.js
- **STEP Import**: cadquery (native STEP parsing, no STL conversion)
- **Mesh Extraction**: cadquery `Shape.tessellate()` → vertices + triangular faces
- **Projection Calculation**: shapely (face projection → unary_union 면적)
- **3D Rendering**: Plotly Mesh3d (WebGL 기반) + Scatter3d (tip markers)
- **Slice Rendering**: Plotly Scatter (closed polygon fill)
- **Tip Detection**: scikit-learn DBSCAN clustering (multi-direction projection 기반 tip 포인트 감지)
- **Callback 구조**: 단일 unified callback (29 outputs) — `callback_context.triggered`로 trigger 판별

### Unit Handling

- **Auto-detect**: CAD tessellation raw coords의 diagonal 길이를 기준으로 단위 판별
  - `diag > 100` → mm coordinates → `/1000` 적용
  - `diag <= 100` → 이미 m 단위 → 그대로 유지
- **SI_UNIT metadata parsing 제거**: CAD export 시 SI_UNIT(`.UNSET.`, `.MILLI.` 등)이 불일치하므로 unreliable
- **isValid() 체크 제거**: CAD가 valid geometry라도 `isValid() == False`를 반환하는 경우 있음

### find_tip 로직 (2026-07-03 업데이트)

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

### 2026-07-03 Update Summary

| 항목 | Before | After |
|---|---|---|
| Unit detection | SI_UNIT regex parsing (.MILLI/.UNSET/.MICRO) | Geometry diagonal auto-detect (>100=mm, ≤100=m) |
| isValid() check | `if not val.isValid(): return None` | Removed (CAD unreliable) |
| Projection direction | YZ + XZ (2방향) | YZ + XZ + XY (3방향) |
| DBSCAN eps max | 100.0 | 0.999 |
| TOL slider range | 0.01 ~ 0.99 | 0.01 ~ 10.0 |
| TOL slider default | 0.5 | 5.0 |
| Tessellation | default | 1e-3 deflection |

### Tessellation

- `val.tessellate(1e-3)` — deflection 1mm
- CAD export 시 tessellation density가 exporter 설정에 따라 달라지므로 viewer는 동일한 deflection 고정

### 2026-07-04 Update Summary

#### Bug Fixes
| 항목 | 내용 |
|---|---|
| Z 버튼 NameError | `tol_curr` 변수 axis-z 블록에 추가 (미정의 버그) |
| Callback SchemaLengthValidationError | export tip 추가 후 Output + return tuple을 30개로 통일 |
| bytes JSON 직렬화 에러 | `dcc.download` content를 `bytes` → `str`로 변경 |
| export 파일명 고정 | 파일 업로드 시 `step_file = save_path`로 전역 변수 업데이트 |

#### New Features
| 기능 | 설명 |
|---|---|
| Export Tip CSV 버튼 | 💾 버튼 추가 — tip 포인트를 CSV 다운로드 |
| dcc.download | Dash built-in 다운로드 지원 |
| dynamic step_file | 파일 업로드 시 현재 파일 경로로 자동 갱신 |

### File Structure

```
step-viewer/
├── SKILL.md              ← this file
└── web-step-viewer.py    ← main application
```

## Updates

### 2026-07-04 — Export Tip CSV + Callback Fixes

- Export Tip CSV 기능 추가 (`dcc.download` 기반)
- Z 버튼 NameError (`tol_curr` 미정의) 수정
- Callback return tuple 30개로 통일 (download-tips output 추가)
- file-upload 시 `step_file` 전역 변수 업데이트 (export 파일명 동적 변경)
- `bytes` → `str`로 변경 (`dcc.download` 호환성)

### 2026-06-25 — Initial Release

- STEP 파일을 cadquery로 native parsing
- mesh extraction via `Shape.tessellate()`
- STL viewer와 동일한 find_tip + TOL slider 로직 재사용
- slice extraction: face-triangle intersection 기반
- BBox/CoM/Projection 면적 계산
- 파일 업로드 / Find Tip / Reset / TOL 슬라이더 지원
