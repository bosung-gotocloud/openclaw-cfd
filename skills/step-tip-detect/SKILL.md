---
name: step-tip-detect
description: STEP CAD native edges 기반 tip detection. Hybrid: Graph Sharp Corner + DBSCAN radial clustering fusion + convexity check. VLM 없이 CAD 기하학만으로 동작.
---

# step-tip-detect — STEP CAD Tip Detection (Hybrid: Graph Sharp Corner + DBSCAN Fusion + Convexity Check)

STEP CAD 파일에서 날끝(wingtip), 꼬리끝(tailtip), **canard 및 모든 작은 돌출부**를
**Hybrid 기하학 알고리즘**만으로 검출합니다. VLM이 필요 없으며,
pure geometry로 동작합니다.

## 📋 워크플로우 요약

```
STEP 파일 (CAD)
    ↓
1. load_step()       — STEP header unit 감지 → mm 통일 + bbox 계산
    ↓
2. get_all_edges()    — STEP native edges ALL 추출 (중복 제거)
    ↓
┌─ Approach 1: Graph Sharp Corner Detection ──────────────────────┐
│ 3. Per-view: orthographic projection -> 2D graph                 │
│ 4. Per-view: graph에서 sharp corner detection (>90 deg tangent)  │
│ 5. 3-direction 매칭 -> triangulation + postprocess dedup (BBox 5%)│
└──────────────────────────────────────────────────────────────────┘
    ↓
┌─ Approach 2: DBSCAN Radial Clustering ──────────────────────────┐
│ 6. face tessellation -> vertices 수집                            │
│ 7. 3-direction projection -> radial calculation                  │
│ 8. Multi-percentile thresholding (30%, 50%, 70%)                │
│ 9. Adaptive DBSCAN -> peak selection -> tip candidates           │
└──────────────────────────────────────────────────────────────────┘
    ↓
10. Fusion: merge + dedup + convexity check + silhouette filter
11. tip classification: wing_tip / tail_tip / other
12. type-specific clustering -> final tips
    ↓
Output: tip_points.csv + tip_cam.png (camera view)
```

---

## 1. STEP 로드 (`read_step_header_unit` + `load_step`)

### 단위 감지
```python
# STEP header에서 LENGTH_UNIT 확인
SI_UNIT(... .(METRE|MMETER). ...)
    → METRE  → 'M' (미터)
    → MMETER → 'MM' (밀리미터)
단위 없음 → MM 추측
```

### 로드
```python
shape_mm = cq.importers.importStep(path, unit='MM').val()
faces = list(shape_mm.Faces())
edges = get_all_edges(shape_mm)  # ALL edges
```

### BBox 계산
```python
{
    'xmin','xmax','ymin','ymax','zmin','zmax',  # min/max (mm)
    'xl','yl','zl',                              # span
    'center': np.array([center_x, center_y, center_z])
}
```

---

## 2. Edge 추출 (`get_all_edges`)

STEP shape에서 **모든 edges**를 추출하고, vertex tuple로 중복 제거합니다.

---

## 🔍 Tip Detection Algorithm — Hybrid Dual Approach

### Approach 1: STEP Edge Graph Sharp Corner

**역할**: STEP native edges의 기하학적 급변(sharp corner)을 검출. canard 같은 작은 돌출부 탐지에 특화.

**단계별 로직:**

1. **Edge 추출** — `get_all_edges()`: 모든 STEP edge를 unique edges로 추출
2. **3방향 projection** — XZ/YZ/XY로 projection, 각 view별로 2D graph 구성
3. **Vertex snapping** — 1mm grid tolerance로 vertex snap (floating point 오차 방지)
4. **Sharp corner detection** — graph vertex에서 tangent angle > 90° (cos < 0) 인 점 검출
5. **Silhouette extraction** — bbox ±margin 기반 silhouette edges 추출
6. **Silhouette contour 구성** — odd-degree vertex 기준 DFS로 closed loop polygon 생성
7. **3-view triangulation** — 각 view에서 sharp corner를 매칭, 3개 view 모두에서 일치하는 3D 좌표로 복원
8. **Post-process dedup** — BBox 5% 이내 점들을 그룹핑하여 평균값

### Approach 2: DBSCAN-based Radial Clustering (NEW v5)

**역할**: face tessellation vertices의 radial distribution 기반 tip 검출. sharp corner detection이 놓칠 수 있는 protrusion을 추가 탐지.

**단계별 로직:**

1. **Face tessellation** — 각 face에 `tessellate(1.0)` → vertices 수집 (cadquery native)
2. **3방향 projection** — YZ/XZ/XY 평면에 vertex projection
3. **Face centroid 기반 radial 계산** — 각 face의 centroid 평균을 origin으로, vertex까지의 거리(radial) 계산
4. **다중 percentile thresholding** — 30%, 50%, 70th percentile에서 radial이 큰 vertex 추출 (서로 다른 크기/위치의 tip 모두 탐지)
5. **Downsampling** — 50000개 초과 시 fixed seed(42)로 downsample (DBSCAN 성능 최적화)
6. **Normalization** — 각 축의 std로 스케일링 → isotropic clustering
7. **Adaptive DBSCAN** — `eps = 0.3 / scale.min()`, max 0.999, min_samples=5
8. **Peak selection** — 각 cluster에서 radial이 최대인 vertex → tip candidate
9. **Dedup** — tol 거리 이내의 중복 제거

### Fusion: Merge & Filter & Classify

```python
# 1. 두 접근법에서 검출된 tip을 모두 합치기
all_candidates = tips_graph + tips_dbscan

# 2. BBox 5% dedup
dedup_tol = max(xl, yl, zl) * 0.05

# 3. Convexity check: face normal outward dot product > 0.3 -> convex external
# 4. Heuristic: bbox extreme proximity -> external likelihood
# 5. Silhouette contour outside check (2+ views)

# 6. 필터링: is_sharp OR is_likely_ext OR is_convex_ext OR (is_external AND (is_convex_ext OR is_extreme))

# 7. 타입별 클러스터링: wing_tip/tail_tip/other 그룹별 clustering

# 8. CSV + PNG 출력
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
tol = args.tol  # default 5.0mm
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
1. silhouette edges 추출 (projection direction에서 global bbox ±margin)
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

### Closed Loop Polygon 구성 (구현 세부)
```
1. silhouette edges를 2D projection (view 방향)
2. endpoint snap grid (tol=5mm) -> unique endpoints
3. adjacency list by shared endpoints
4. DFS: odd-degree vertex에서 시작 -> closed loop 완성
5. shapely Polygon 구성 (buffer(0)로 self-intersection fix)
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
| **wing_tip** | `abs(dy) > yl/4` AND `abs(dz) < zl/4` | Y 방향 중심에서 먼 점 |
| **tail_tip** | `abs(dz) > zl/4` | Z 방향 중심에서 먼 점 |
| **other** | 위 조건 모두 아님 | 기타 tip (canard 포함) |

---

## 8. Camera View Rendering

### Camera configuration
- **방향**: (-1, 1, 1) — tail-back view
- **Rotation**: -90° X -> -45° Y -> +35.264° X
- **Canvas**: 800x800, 흰색 배경
- **Tip marker**: 빨간 circle (r=4 filled, r=5 border)
- **Projection**: bbox center가 화면 중앙에 오도록
- **rx = tx*cos45 + tz*sin45** (vlm-tip-detect과 동일 formula)
- **rz = -tx*sin45 + tz*cos45**

### Rendering 함수
```python
def render_cam_with_tips(points_list, tips_mm, bbox, img_size=800):
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

## 실행 방법

### 기본 실행
```bash
python step-tip-detect.py <input.stp>
```

### 커스텀 tolerance
```bash
python step-tip-detect.py <input.stp> --tol 10.0
```

### DBSCAN fusion 비활성화
```bash
python step-tip-detect.py <input.stp> --no-dbscan
```

### Convexity check 비활성화
```bash
python step-tip-detect.py <input.stp> --no-convexity
```

### verbose 모드
```bash
python step-tip-detect.py <input.stp> --verbose
```

### 출력이력 지정
```bash
python step-tip-detect.py <input.stp> <output.csv>
```

---

## 출력 파일

| 파일 | 형식 | 설명 |
|------|------|------|
| `{name}_tip_points.csv` | CSV (헤더 없음) | `x,y,z` (m, 6자리 소수점) |
| `{name}_tip_cam.png` | PNG (800x800) | Camera view (tail-back) + 빨간 tip marker |

---

## 알고리즘 특징

### ✅ 장점
- **VLM 의존도 없음** — CAD native 데이터만으로 동작
- **Hybrid dual detection** — Graph Sharp Corner + DBSCAN fusion → 높은 검출률
- **canard 포함한 작은 돌출부 검출** — 모든 edges를 graph로 분석
- **silhouette contour 내부/외부 판별** — body surface에 붙은 점 자동 제외
- **sharp angle 90°** — tangent direction 급변 기준 (노이즈 감소)
- **convexity check** — face normal outward dot product 기반 external 판별
- **postprocess dedup** — BBox 5% 이내 점들 그룹핑 -> 평균
- **closed loop contour** — ConvexHull 대신 silhouette edges의 실제 contour 사용
- **type-specific clustering** — wing_tip/tail_tip 그룹별 병합 (과검출 방지)

### ❌ 단점
- **모든 edges graph 분석** — 계산량 많음
- **Face tessellation** — large STEP 파일에서 vertices 수집 비용 (최대 50000 downsample)
- **ConvexHull 기반 contour** — non-convex contour는 approximated

---

## 주요 파라미터

| 파라미터 | 값 | 설명 |
|------|-----|------|
| **sharp_angle** | `cos < 0.0` (90°) | tangent direction 급변 기준 |
| **dedup_tol** | `args.tol` (default 5.0mm) | 3-direction 매칭 tolerance |
| **postprocess_tol** | `max(xl,yl,zl) × 5%` | 후처리 dedup 그룹핑 tol |
| **nose_filter** | `dx < 0` | bbox center보다 -X 방향 점 제외 |
| **wing_tip_threshold** | `|dy| > yl/4` | Y 방향 중심 거리 기준 |
| **tail_tip_threshold** | `|dz| > zl/4` | Z 방향 중심 거리 기준 |
| **outside_cont** | `>= 2 views` | silhouette contour outside 판정 기준 |
| **DBSCAN_eps** | `0.3/scale.min()`, max 0.999 | radial clustering epsilon |
| **DBSCAN_min_samples** | `5` | 최소 cluster 크기 |
| **dbscan_downsample** | `50000` vertices | large mesh downsampling threshold |
| **convexity_threshold** | `> 0.3` | face normal outward dot product 기준 |

---

## 테스트 결과 (v5 Hybrid)

### LC62-50B.stp (366 faces, 880 edges)
- **BBox**: X[7.22..2032.74] Y[-1100..1100] Z[3.5..698] mm
- **Graph**: XZ(206 vertices, 347 edges), YZ(322, 586), XY(338, 591)
- **Sharp corners**: XZ(23), YZ(23), XY(51)
- **DBSCAN**: 20 tip candidates (face tessellation vertices 기반)
- **검출 결과**: **14 tips** (+3 from v3's 11)
  - wing_tip: 4개 (기존 2개 + DBSCAN 추가 2개: wing root)
  - tail_tip: 2개
  - other: 8개 (canard 포함)
- **특징**: DBSCAN fusion으로 wing root tip 추가 검출

### MQ9-reaper.stp (78 faces, 162 edges)
- **BBox**: X[100..11133.76] Y[-10265.93..10265.93] Z[-1212.73..2526.76] mm
- **Graph**: XZ(41, 61), YZ(55, 92), XY(56, 84)
- **DBSCAN**: 20 tip candidates
- **검출 결과**: **6 tips** (wing_tip 1, tail_tip 4, other 1)

### myShahed.stp (114 faces, 148 edges)
- **BBox**: X[-10.36..2352.98] Y[-1200..1200] Z[-200..130] mm
- **Graph**: XZ(26, 44), YZ(36, 63), XY(39, 63)
- **DBSCAN**: 20 tip candidates
- **검출 결과**: **7 tips** (tail_tip 5, other 2)

---

## Dependencies

```bash
pip install cadquery numpy opencv-python shapely scipy scikit-learn
```

---

## Updates

### 2026-08-14 — v5 Hybrid (Graph Sharp Corner + DBSCAN Fusion + Convexity Check)

**새로운 Approach 2 (DBSCAN fusion):**
- face tessellation vertices 수집 (`cadquery.Face.tessellate()`)
- 3-direction radial clustering (30/50/70 percentile)
- Adaptive DBSCAN (eps, min_samples, normalization)
- Peak selection → tip candidates

**Convexity check 강화:**
- face normal outward dot product (> 0.3 = convex external)
- edge curvature 분석 (tangent angle > 60°)

**Fusion filter:**
- `is_sharp OR is_likely_ext OR is_convex_ext OR (is_external AND (is_convex_ext OR is_extreme))`
- type-specific clustering (과검출 방지)

**테스트 결과:**
- LC62-50B: 11 → 14 tips (+3 DBSCAN 추가)
- MQ9-reaper: 5 → 6 tips
- myShahed: 7 → 7 tips (유지)

### 2026-08-05~06 — step-tip-detect.py v3 최종 확정 (Graph Sharp Corner only)
- **방식**: STEP native edges → orthographic projection (XZ/YZ/XY) → silhouette(외곽선) → sharp corner → convexity → Y-Z dedup + max-X → -X 필터
- **Silhouette margin**: max(bbox_span × 1%, 5mm)
- **Sharp corner**: tangent direction 급변 (cos < 0.5, angle > 60°) + endpoints
- **Convexity check**: face normal outward dot product > 0.3 → internal/concave 제외

### 2026-07-30 — STEP Tip Detection - LC62-50B Wing Tip Rule
- **wing tip 검출 규칙**: LC62-50B에서 wing tip은 **Y=0에서 가장 먼 지점** (최대 ±Y direction)
- **Y max** ≈ 1100 mm, **Y min** ≈ -1100 mm → 양쪽 날끝 (상단 날 / 하단 날)
