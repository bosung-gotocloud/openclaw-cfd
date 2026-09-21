---
name: stl-tip-detect
description: STL mesh edges 기반 tip detection. 2D orthographic projection + mesh edge graph sharp corner → silhouette contour 내부/외부 판별 → wing/tail detection. VLM 없이 CAD 기하학만으로 동작.
---

# stl-tip-detect — STL Mesh Tip Detection (Graph + Silhouette Contour Filter)

STL mesh 파일에서 날끝(wingtip), 꼬리끝(tailtip), **canard 및 모든 작은 돌출부**를
**mesh edges의 기하학 알고리즘**만으로 검출합니다. VLM이 필요 없으며,
pure geometry로 동작합니다.

## 📋 워크플로우 요약

```
STL 파일 (mesh)
    ↓
1. load_stl()       — 단위 감지 (mm default) + bbox 계산
    ↓
2. get_mesh_edges()  — STL mesh edges ALL 추출 (중복 제거)
    ↓
3. Per-view: orthographic projection -> 2D graph
    ↓
4. Per-view: graph에서 sharp corner detection (>90 deg tangent)
    ↓
5. 3-direction 매칭 -> triangulation + postprocess dedup (BBox 5%)
    ↓
6. silhouette contour 내부/외부 판별 (shapely ConvexHull + closed loop)
   - 2개 이상 view에서 outside → external tip ✅
   - 내부 → 제외 ❌
    ↓
7. tip classification: wing_tip / tail_tip / other (nose 제외)
    ↓
Output: tip_points.csv + tip_cam.png (camera view)
```

---

## 1. STL 로드 (`load_stl`)

### 단위 감지
```python
# STL은 단위 정보가 없으므로 heuristic 사용
# max coordinate > 100 → mm로 간주 → 1000으로 나누어 m로 변환
# max coordinate <= 100 → m로 간주
if max(coord) > 100:
    unit = 'MM'
    vertices *= 0.001
else:
    unit = 'M'
```

### 로드
```python
mesh = trimesh.load(path)
edges = get_all_edges(mesh)  # ALL unique edges
bbox = get_bbox(mesh)
```

### BBox 계산 (SI: m)
```python
{
    'xmin','xmax','ymin','ymax','zmin','zmax',  # min/max (m)
    'xl','yl','zl',                              # span
    'center': np.array([center_x, center_y, center_z])
}
```

---

## 2. Edge 추출 (`get_all_edges`)

STL mesh에서 **모든 face edges**를 추출하고, vertex tuple로 중복 제거합니다.

```python
# trimesh edges: mesh.edges_unique (unique edge vertex indices)
# trimesh.vertices[edges_unique] → 3D 좌표
# coordinate matching으로 duplicate edges 제거
```

---

## 3. Orthographic Projection -> 2D Graph

### 3 뷰 정의

| 뷰 | 숨김 축 | 유지 축 | min/max 기준 |
|----|---------|------|-----------|
| **XZ** | Y | X, Z | ymin / ymax |
| **YZ** | X | Y, Z | xmin / xmax |
| **XY** | Z | X, Y | zmin / zmax |

### Graph 구성
```
1. 모든 3D edges를 view 방향으로 orthographic projection
2. endpoint를 snap grid (tol=1mm) -> unique vertices
3. edges를 vertex index pair로 연결
4. adjacency list 구성
```

---

## 4. Sharp Corner Detection (>90 deg)

### Tangent 계산
```python
# graph vertex에서 양방향 neighbor의 tangent vector
a = neighbor1 - vertex
b = neighbor2 - vertex
normalize(a), normalize(b)
cos_angle = dot(a, b)

if cos_angle < 0.0:   # angle > 90°
    sharp_vertex = vertex
```

---

## 5. Triangulation + Postprocess Dedup

### 3-view 매칭 -> 3D 좌표 복원
```python
# 각 view에서 검출된 vertex들을 Y-Z 평면에서 그룹핑
tol = args.tol  # default 5mm
# dy < tol AND dz < tol -> 같은 3D 점
# group에서 가장 큰 X 선택
```

### Postprocess Dedup
```python
# BBox의 5% 이내 점들 그룹핑 -> 평균
group_tol = max(xl, yl, zl) * 0.05
```

---

## 6. Silhouette Contour Internal/External 판별

### 핵심 로직
```
1. silhouette edges 추출 (projected shape boundary = convex hull)
2. silhouette edges에서 closed loop polygon 구성 (DFS by odd-degree vertices)
3. shapely Polygon.contains(point)
   - outside (not within) -> external tip ✅
   - inside (within) -> internal ❌
```

### 판정 기준
```python
outside_count = 0
for view in ['XZ', 'YZ', 'XY']:
    if check_point_outside_contour(tip, silhouette, view):
        outside_count += 1

if outside_count >= 2:  # 2개 이상 view에서 outside
    external_tip = True
```

---

## 7. Tip Classification

### Nose filtering
```python
dx = tip_x - bbox_center_x
if dx < 0:  # nose 방향 -> 제외
    continue
```

### 분류 기준
| 유형 | 조건 | 설명 |
|------|------|------|
| **wing_tip** | `abs(dy) > yl/2` | Y 방향 중심에서 먼 점 (날끝) |
| **tail_tip** | `abs(dz) > zl/2` | Z 방향 중심에서 먼 점 (꼬리끝) |
| **nose_tip** | `dx > xl/2` | X max 방향 (코 끝) |
| **other** | 위 조건 모두 아님 | 기타 tip (canard 포함) |

---

## 8. Camera View Rendering

### Camera configuration
- **방향**: (-1, 1, 1) — tail-back view
- **Rotation**: -90° X -> -45° Y -> +35.264° X
- **Canvas**: 800x800, 흰색 배경
- **Tip marker**: 빨간 circle (r=4 filled, r=5 border)
- **Projection**: bbox center가 화면 중앙에 오도록
- **rx = tx*cos45 + tz*sin45** (step-tip-detect과 동일 formula)
- **rz = -tx*sin45 + tz*cos45**

### Rendering 함수
```python
def render_cam_with_tips(points_list, tips_m, bbox, img_size=800):
    c = bbox['center']; me = max(xl, yl, zl) or 1
    sc = img_size * 0.7 / me
    cx_screen = img_size // 2; cy_screen = img_size // 2
    
    def _project(tx, ty, tz):
        ty2 = ty*cos(-90) - tz*sin(-90)
        tz2 = ty*sin(-90) + tz*cos(-90)
        rx = tx*cos45 + tz2*sin45
        ry = ty2
        rz = -tx*sin45 + tz2*cos45
        ry2 = ry*cos35 - rz*sin35
        return rx*sc+cx, -ry2*sc+cy
```

---

## 🔍 Tip Detection Algorithm — 상세 로직

### Dual Approach: Graph Sharp Corner + DBSCAN Fusion

이 스크립트는 **2가지 독립적 tip 검출**을 수행하고 결과를 fusion합니다.

#### Approach 1: Mesh Edge Graph Sharp Corner

**역할**: mesh edges의 기하학적 급변(sharp corner)을 검출. canard 같은 작은 돌출부 탐지에 특화.

**단계별 로직:**

1. **Edge 추출** — `get_all_edges()`: 모든 mesh face edge를 unique edges로 추출
2. **3방향 projection** — XZ/YZ/XY로 projection, 각 view별로 2D graph 구성
3. **Vertex snapping** — 1mm grid tolerance로 vertex snap (floating point 오차 방지)
4. **Sharp corner detection** — graph vertex에서 tangent angle > 90° (cos < 0) 인 점 검출
5. **Silhouette extraction** — shapely convex hull로 외곽선 추출, hull boundary에 붙은 edges만 silhouette edges로 남김
6. **Silhouette contour 구성** — odd-degree vertex 기준 DFS로 closed loop polygon 생성
7. **3-view triangulation** — 각 view에서 sharp corner를 매칭, 3개 view 모두에서 일치하는 3D 좌표로 복원
8. **Post-process dedup** — BBox 5% 이내 점들을 그룹핑하여 평균값

#### Approach 2: DBSCAN-based Radial Clustering

**역할**: vertex radial distribution 기반 tip 검출. sharp corner detection이 놓칠 수 있는 protrusion을 추가 탐지.

**단계별 로직:**

1. **3방향 projection** — YZ/XZ/XY 평면에 vertex projection
2. **Face centroid 기반 radial 계산** — 각 face의 centroid 평균을 origin으로, vertex까지의 거리(radial) 계산
3. **다중 percentile thresholding** — 30%, 50%, 70th percentile에서 radial이 큰 vertex 추출 (서로 다른 크기/위치의 tip 모두 탐지)
4. **Downsampling** — 5000개 초과 시 fixed seed(42)로 5000개 downsample (DBSCAN 성능 최적화)
5. **Normalization** — 각 축의 std로 스케일링 → isotropic clustering
6. **Adaptive DBSCAN** — `eps = 0.3 / scale.min()`, max 0.999, min_samples=5
7. **Peak selection** — 각 cluster에서 radial이 최대인 vertex → tip candidate
8. **Dedup** — tol 거리 이내의 중복 제거

#### Fusion: Merge & Classify

```python
# 1. 두 접근법에서 검출된 tip을 모두 합치기
all_candidates = tips_graph + tips_dbscan

# 2. BBox 5% dedup
dedup_tol = max(xl, yl, zl) * 0.05

# 3. 외부 판정
is_sharp = sharp corner detection ( Approach 1 )
is_likely_ext = bbox extreme proximity heuristic ( Approach 2 support )

# 4. 필터링: is_sharp OR is_likely_ext 인 점만 최종 tip으로 채택

# 5. 타입별 클러스터링: wing_tip/tail_tip/nose_tip/other 그룹별 clustering

# 6. CSV + PNG 출력
```

---

## 실행 방법

### 기본 실행
```bash
python stl-tip-detect.py <input.stl>
```

### 커스텀 tolerance
```bash
python stl-tip-detect.py <input.stl> --tol 10.0
```

### verbose 모드
```bash
python stl-tip-detect.py <input.stl> --verbose
```

### 입출력 단위 지정
```bash
python stl-tip-detect.py <input.stl> --unit m
```

### 출력 파일 지정
```bash
python stl-tip-detect.py <input.stl> <output.csv>
```

---

## 출력 파일

| 파일 | 형식 | 설명 |
|------|------|------|
| `{name}_tip_points.csv` | CSV (헤더 없음) | `x,y,z` (m, 6자리 소수점) |
| `{name}_tip_cam.png` | PNG (800x800) | Camera view (tail-back) + 빨간 tip marker |

---

## 주요 파라미터

| 파라미터 | 값 | 설명 |
|------|-----|------|
| **sharp_angle** | `cos < 0.0` (90°) | tangent direction 급변 기준 |
| **dedup_tol** | `args.tol` (default 5mm) | 3-direction 매칭 tolerance |
| **postprocess_tol** | `max(xl,yl,zl) × 5%` | 후처리 dedup 그룹핑 tol |
| **nose_filter** | `dx < 0` | bbox center보다 -X 방향 점 제외 |
| **wing_tip_threshold** | `|dy| > yl/2` | Y 방향 중심 거리 기준 |
| **tail_tip_threshold** | `|dz| > zl/2` | Z 방향 중심 거리 기준 |
| **outside_count** | `>= 2 views` | silhouette contour outside 판정 기준 |
| **unit** | `mm` (default) | 입력 단위 (`--unit m`로 오버라이드) |
| **silhouette_tol** | `0.5%` projected span | hull boundary tolerance |
| **vertex_snap** | `1mm` | graph vertex snapping grid |
| **DBSCAN_eps_max** | `0.999` | cluster merge 방지 (critical) |
| **DBSCAN_eps_min** | `0.001` | 최소 eps |
| **DBSCAN_min_samples** | `5` | 최소 cluster 크기 |
| **dbscan_downsample** | `50000` vertices | large mesh downsampling threshold |

---

## Dependencies

```bash
pip install trimesh numpy opencv-python shapely scipy scikit-learn
```

---

## 알고리즘 특징

### ✅ 장점
- **VLM 의존도 없음** — mesh native 데이터만으로 동작
- **Dual detection** — sharp corner + DBSCAN fusion → 높은 검출률
- **canard 포함한 작은 돌출부 검출** — 모든 edges를 graph로 분석
- **silhouette contour 내부/외부 판별** — body surface에 붙은 점 자동 제외
- **sharp angle 90°** — tangent direction 급변 기준
- **postprocess dedup** — BBox 5% 이내 점들 그룹핑 -> 평균
- **closed loop contour** — ConvexHull 기반 silhouette contour

### ❌ 단점
- **모든 edges graph 분석** — 계산량 많음
- **ConvexHull 기반 contour** — non-convex contour는 approximated

---

## Updates

### 2026-08-14 — Code finalize + SKILL.md detailed documentation

**Code cleanup:**
- `extract_silhouette_edges` dead code 제거 (이전 bbox 기반 silhouette 로직)
- `classify_tips` y-coordinate bug fix (`dz` → `dy`)
- 모든 함수에 docstring 추가
- Variable naming 일관성 개선
- Camera rendering comment 개선

**SKILL.md:**
- Tip detection algorithm 상세 설명 추가 (Dual Approach 문서화)
- Approach 1 (Graph Sharp Corner) 단계별 로직
- Approach 2 (DBSCAN Radial Clustering) 단계별 로직
- Fusion strategy 상세
- 주요 파라미터 테이블 완성

### 2026-07-30 — STEP Tip Detection - LC62-50B Wing Tip Rule
- **wing tip 검출 규칙**: LC62-50B에서 wing tip은 **Y=0에서 가장 먼 지점** (최대 ±Y direction)
- **Y max** ≈ 1100 mm, **Y min** ≈ -1100 mm → 양쪽 날끝 (상단 날 / 하단 날)

### 2026-08-05~06 — step-tip-detect.py v3 최종 확정
- **방식**: STEP native edges → orthographic projection (XZ/YZ/XY) → silhouette(외곽선) → sharp corner → convexity → Y-Z dedup + max-X → -X 필터
- **Silhouette margin**: max(bbox_span × 1%, 5mm)
- **Sharp corner**: tangent direction 급변 (cos < 0.5, angle > 60°) + endpoints
- **Convexity check**: face normal outward dot product > 0.3 → internal/concave 제외
