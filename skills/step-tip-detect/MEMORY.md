# step-tip-detect Memory — Design Notes

## 2026-08-13 — Silhouette Protrusion Detection Logic

### 문제: 현재 v3의 한계
step-tip-detect v3는 orthographic projection silhouette edges만 처리하므로, silhouette 밖의 small protrusion(canard 등)을 놓침.

### 해결 방향
3D STEP에서 orthographic projection → 2D edge contours → contour 따라가며 vertex angle 분석 → 3D 재조립 + dedup

### 로직 (구현 전 설계)

#### 1. STEP에서 edges 추출
```python
faces = shape.Faces()
edges = shape.Edges()  # all edges
```

#### 2. Orthographic projection (XZ/YZ/XY)
각 face의 edges를 projection 방향으로 투영 → 2D contour 자연스럽게 형성됨

#### 3. 2D closed contour 추출
- edges를 endpoint로 연결 → closed loop 찾기
- shapely 또는 직접 구현

#### 4. Vertex angle 분석
contour 따라가며 vertex에서의 edge 간 angle 계산 → sharp corner detection

#### 5. 3D 재조립
XZ, YZ, XY에서 찾은 vertex들을 3D로 매칭 → dedup (현재 방식과 동일)

### 장점
- silhouette 선별의 한계(depth threshold 민감도) 제거
- protrusion도 contour에서 angle로 검출 가능
- contour 따라가며 angle 분석 → 더 정확한 tip 위치

### 단점
- 구현이 더 복잡 (2D contours 찾기 로직 필요)

---

## 2026-08-13 — v4 구현 설계

### 핵심 변경사항
- **Silhouette edge 선별 제거** → 모든 edges를 3뷰에 projection
- **2D contour 기반 vertex angle 분석** → edge sampling 대신 closed contours 따라가며 angle
- **Protrusion detection 가능** → contour에서 protrusion도 angle로 검출

### 상세 로직

#### Step 1: STEP edges 추출 (기존과 동일)
```python
edges = shape.Edges()  # all edges (중복 제거)
bbox = shape.BoundingBox()
```

#### Step 2: Orthographic projection (XZ/YZ/XY)
각 edge를 projection 방향으로 2D 평면에 투영
- XZ view → Y축 숨김, (x, z) 좌표
- YZ view → X축 숨김, (y, z) 좌표
- XY view → Z축 숨김, (x, y) 좌표

#### Step 3: 3D → 2D 매핑 (각 뷰별)
```
view_edges = { edge_id: [(x2d, y2d, z3d_full), ...] }
# 2D coords + projection axis 3D coord 저장
```

#### Step 4: 2D contours 추출
- 각 뷰에서 projected edges를 endpoint로 연결
- connected components → closed contours
- **외곽선(contours)에서 sharp vertex 찾기**

#### Step 5: Contour vertex angle 분석
```python
for contour in closed_contours:
    for i in range(len(contour)):
        prev = contour[i-1]
        curr = contour[i]
        next = contour[i+1]
        angle = vector_angle(prev->curr, curr->next)
        if angle > threshold (cos < 0.5 = 60°):
            sharp_vertex = curr
```

#### Step 6: Sharp vertex를 3D 좌표로 매핑
```python
# 2D vertex → 3D 원본 edge에서 대응 vertex 찾기
vertex_3d = edge에서 대응 vertex
```

#### Step 7: 3D 재조립 (현재 방식과 동일)
```python
# XZ, YZ, XY에서 찾은 vertex들을 Y-Z 평면에서 그룹핑
# dedup_tol = args.tol
# group에서 가장 큰 X 선택
```

#### Step 8: Tip classification (현재 방식과 동일)
- Nose filtering (dx < 0 → nose 제외)
- wing_tip, tail_tip, other 분류
- BBox masking

### 추가 기능
- **Convexity check 추가**: face normal outward dot product > 0.3 (internal/concave 제외)
- **Protrusion detection**: contour에서 protrusion도 검출 가능
- **Edge sampling 노이즈 제거**: edge native endpoints만 사용

### 테스트 계획
- LC62-50B.stp 테스트
- v3 결과와 비교 (특히 canard 검출 여부)
- 추가 테스트 케이스: canard가 있는 항공기 CAD 파일

### Dependencies
- cadquery, numpy, opencv-python (기존과 동일)
- **추가**: shapely (2D contours 연결용)

### 출력 파일 (기존과 동일)
- `{name}_tip_points.csv` — `x,y,z` (m 단위)
- `{name}_tip_cam.png` — 800×800 camera view + 빨간 tip marker

### 파라미터
- `--tol`: default 5.0mm (기존과 동일)
- `--sharp-angle`: default cos < 0.5 (60°) → **v4에서 90° 이상 (cos < 0)으로 변경**
- `--convexity`: default dot > 0.3 (기존과 동일)
- **후처리 dedup**: BBox 크기의 5% 이내인 점들을 그룹핑 → 평균
- **tip 수**: v3(11개) → v4목표(11~15개, canard 포함)
