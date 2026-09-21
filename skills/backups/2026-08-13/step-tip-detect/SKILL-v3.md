---
name: step-tip-detect
description: STEP CAD native edges 기반 tip detection. Orthographic projection silhouette → sharp corner + convexity → Y-Z dedup → CSV/PNG output. VLM 없이 CAD 기하학만으로 동작.
---

# step-tip-detect.py v3 — STEP Native Edges 기반 Tip Detection

STEP CAD 파일에서 날끝(wingtip), 꼬리끝(tailtip), 그리고 모든 날카로운 돌출부를
**CAD native edges의 기하학 알고리즘**만으로 검출합니다. VLM이 필요 없으며,
pure geometry로 동작합니다.

## 📋 워크플로우 요약

```
STEP 파일 (CAD)
    ↓
1. load_step()       — STEP header unit 감지 → mm 통일 + bbox 계산
    ↓
2. get_all_edges()    — STEP native edges 추출 (중복 제거)
    ↓
3. Per-view silhouette extraction (XZ/YZ/XY)
    ↓
    a. projection direction에서 global bbox min/max ± margin 이내 edge만 선별
    b. silhouette margin = max(bbox_span × 1%, 5mm)
    ↓
4. sharp corner detection (silhouette edges 위)
    ↓
    a. tangent angle > 60° (cos < 0.5) → sharp corner
    b. endpoints도 포함
    c. convexity check: face normal outward dot > 0.3 → concave 제외
    ↓
5. Y-Z dedup + max-X filter
    ↓
6. tip classification: wing_tip / tail_tip / other (nose 제외)
    ↓
Output: tip_points.csv + tip_cam.png (camera view)
```

---

## 1. STEP 로드 (`load_step` + `read_step_header_unit`)

### 단위 감지
```python
# STEP header에서 LENGTH_UNIT 확인
SI_UNIT(... .(METRE|MMETER). ...)
    → METRE  → 'M' (미터)
    → MMETER → 'MM' (밀리미터)
단위 없음 → bbox diagonal > 100 → mm 추측
```

### 로드
```python
shape_mm = cq.importers.importStep(path, unit='MM').val()
faces = list(shape_mm.Faces())
edges = get_all_edges(shape_mm)
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

STEP shape에서 모든 edges를 추출하고, vertex tuple로 중복 제거합니다.

```python
edges = list(shape.Edges())
edge_set = set()
for e in edges:
    verts = tuple(sorted((v.X, v.Y, v.Z) for v in e.Vertices()))
    if verts not in edge_set:
        edge_set.add(verts)
        unique_edges.append(e)
```

---

## 3. Orthographic Projection + Silhouette 추출

### 3 뷰 정의

| 뷰 | 숨김 축 | 유지 축 | min/max 기준 |
|----|---------|---------|-------------|
| **XZ** | Y | X, Z | ymin / ymax |
| **YZ** | X | Y, Z | xmin / xmax |
| **XY** | Z | X, Y | zmin / zmax |

### Silhouette margin
```python
margin = max(global_span × 0.01, 5.0)  # max(1%, 5mm)
```

### 로직
각 edge를 projection direction으로 투영했을 때,
global bbox의 min/max에 `margin` 이내로 접근하는 edge만 silhouette로 선별합니다.

```python
# Y 방향 숨김 (XZ 뷰)
if (edge_min_y >= ymin - margin and edge_min_y <= ymin + margin) or
   (edge_max_y >= ymax - margin and edge_max_y <= ymax + margin):
    silhouette.append(edge)
```

---

## 4. Sharp Corner Detection (Silhouette Edges 위)

### Tangent 계산
```python
# 각 샘플점에서 양방향 차분 tangent 계산
tangents[i] = (pts[i+1] - pts[i-1]) / 2.0  # 중앙 차분
tangents[0] = pts[1] - pts[0]               # 전방 차분
tangents[n-1] = pts[n-1] - pts[n-2]         # 후방 차분
normalize(tangents)
```

### Sharp corner 판별
```python
# tangent[i-1]와 tangent[i+1] 사이 각도
cos_angle = dot(tangents[i-1], tangents[i+1])
if cos_angle < 0.5:   # angle > 60°
    corner_indices.append(i)
```

### Endpoints 포함
```python
corner_indices = [0, n_pts - 1] + corner_indices
```

---

## 5. Convexity Check

각 sharp corner 점에서 **face normal이 바깥 방향인지** 확인합니다.
내부/concave 점은 tip으로 간주하지 않습니다.

```python
# face seam에서 normal 계산
n = cross(dir_vec, [0, 0, 1])
n = normalize(n)

# outward 방향과의 dot product
best_dot = max(dot(n, outward_dir) for outward_dir in outward_dirs)

if best_dot > 0.3:  # convex → tip 후보
    candidates.append(point)
```

### Outward directions (뷰별)
| 뷰 | Outward directions |
|----|-------------------|
| XZ | (-1,0,0), (1,0,0), (0,0,-1), (0,0,1) |
| YZ | (0,-1,0), (0,1,0), (0,0,-1), (0,0,1) |
| XY | (-1,0,0), (1,0,0), (0,-1,0), (0,1,0) |

---

## 6. Triangulation + Dedup

### 3-view 매칭 → 3D 좌표 복원
각 뷰에서 검출된 corner 점이 **동일한 3D 점**인지 Y-Z 평면에서 그룹핑합니다.

```python
tol = args.tol  # 기본 5.0mm

# Y-Z 평면에서 그룹핑: dy < tol AND dz < tol
group = 모든 (dy, dz) < tol 인 점들
best = group에서 가장 큰 X 점
```

### View axis 매핑
| 뷰 | Axis | 매칭 기준 |
|----|------|----------|
| XZ | (x, z) | Y로 매칭 |
| YZ | (y, z) | X로 매칭 |
| XY | (x, y) | Z로 매칭 |

---

## 7. Tip Classification

### Nose filtering (-X 방향 제외)
```python
dx = tip_x - bbox_center_x
if dx < 0:  # nose 방향 → 제외
    continue
```

### 분류 기준
| 유형 | 조건 | 설명 |
|------|------|------|
| **wing_tip** | `abs(dy) > yl/4` AND `abs(dz) < zl/4` | Y 방향이 중심에서 충분히 먼 점 |
| **tail_tip** | `abs(dz) > zl/4` | Z 방향이 중심에서 충분히 먼 점 |
| **other** | 위 조건 모두 아님 | 기타 tip |

---

## 8. BBox Masking

검출된 tip이 BBox 외부에 있는 경우 제외합니다.

```python
if (tip.x >= xmin and tip.x <= xmax and
    tip.y >= ymin and tip.y <= ymax and
    tip.z >= zmin and tip.z <= zmax):
    # 유효한 tip
```

---

## 9. Camera View Rendering

### Camera configuration
- **방향**: (-1, 1, 1) — tail-back view
- **Rotation**: -90° X → -45° Y → +35.264° X
- **Canvas**: 800×800, 흰색 배경
- **Tip marker**: 빨간 circle (r=4 filled, r=5 border)

### 렌더링
```python
# Edge lines: dark gray (40,40,40), thickness 1px
cv2.line(img, (x1,y1), (x2,y2), (40,40,40), 1)

# Tip marker: red circle
cv2.circle(img, (sx, sy), 4, (220,40,40), -1)
cv2.circle(img, (sx, sy), 5, (180,20,20), 2)
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
| `{name}_tip_cam.png` | PNG (800×800) | Camera view (tail-back) + 빨간 tip marker |

---

## 알고리즘 특징

### ✅ 장점
- **VLM 의존도 없음** — CAD native 데이터만으로 동작
- **기하학적 정확도** — STEP native edges 기반
- **Convexity filter** — 내부/concave 점 자동 제외
- **Silhouette margin** — bbox span 기반 자동 margin (1% 또는 5mm)
- **Y-Z dedup** — 날개 구조에서 동일한 tip의 중복 검출 방지

### ❌ 단점
- **Silhouette로 안 잡히는 protrusion 놓침** — small canard 등
- **Convexity threshold 민감** — dot > 0.3 기준이 모든 형상에 적합하지 않을 수 있음
- **sharp corner만 검출** — smooth한 돌출부는 놓칠 수 있음

---

## 주요 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| **silhouette_margin** | `max(span×1%, 5mm)` | silhouette 판정 margin |
| **sharp_angle** | `cos < 0.5` (60°) | tangent direction 급변 기준 |
| **convexity_threshold** | `dot > 0.3` | outward normal 판정 기준 |
| **dedup_tol** | `args.tol` (default 5.0mm) | Y-Z 평면 dedup tolerance |
| **nose_filter** | `dx < 0` | bbox center보다 -X 방향 점 제외 |
| **wing_tip_threshold** | `|dy| > yl/4` | Y 방향 중심 거리 기준 |
| **tail_tip_threshold** | `|dz| > zl/4` | Z 방향 중심 거리 기준 |
| **bbox_mask** | true | BBox 외부 점 제외 |

---

## 테스트 결과 (LC62-50B)

- **입력**: LC62-50B.stp (366 faces, 880 edges)
- **BBox**: X[7.22..2032.74] Y[-1100..1100] Z[3.5..698] mm
- **검출 결과**: 11 tip (2 wing_tip + 2 tail_tip + 7 other)
  - Tip 2 (1567, 1100, 385): wing_tip (상단 날끝)
  - Tip 5 (1567, -1100, 385): wing_tip (하단 날끝)
  - Tip 8 (2031, -0.6, 693): tail_tip (Z max)
  - Tip 10 (1804, 0.3, 9): tail_tip (Z min)
- **미검출**: canard (silhouette로 안 잡히는 small protrusion)

---

## Dependencies

```bash
pip install cadquery numpy opencv-python
```
