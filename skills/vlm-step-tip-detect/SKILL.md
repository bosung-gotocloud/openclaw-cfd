---
name: vlm-step-tip-detect
description: VLM(Vision Language Model) 기반 STEP CAD tip detection. Orthographic projection → VLM pixel detection → CAD coordinate mapping → triangulation → CSV/PNG output.
---

# vlm-step-tip-detect.py — VLM-Based STEP CAD Tip Detection

**최종 버전: 2026-08-12**

STEP CAD 파일에서 날끝(wingtip), 꼬리끝(tailtip), canard tip, sharp concave points 등
모든 뾰족한 돌출부를 **VLM의 시각적 식별 능력**으로 검출합니다.

## 📋 워크플로우 요약

```
STEP 파일 (CAD)
    ↓
1. load_step()       — STEP header unit 감지 → mm 통일 저장 + bbox 계산
    ↓
2. render_ortho_stl() — 3 orthographic views (XZ, YZ, XY) → 1100×1100 PNG
    ↓
3. VLM 호출          — 각 뷰별 이미지 → VLM이 tip pixel 좌표 반환
    ↓
4. parse_vlm()       — VLM JSON 응답 파싱 (image_width/height 지원)
    ↓
5. Scale 보정        — VLM이 반환한 image_size 기준 pixel → 실제 PNG(1100×1100) 기준 pixel
    ↓
6. pixel→CAD 역산    — 1100×1100 PNG 기준 pixel → CAD(mm) 좌표
    ↓
7. triangulate()     — 3-view hints → 3D 좌표
    ↓
8. Dedup             — tol(0.05 × max_bbox) 이내의 근접 tip 하나로 합치기
    ↓
Output: tip_points.csv + tip.png (ISO 뷰) + annotated PNGs
```

---

## 1. STEP 로드 (`load_step`)

### 단위 감지
```python
# STEP header에서 LENGTH_UNIT 확인
LENGTH_UNIT ... METRIC    → mm (변환 없음)
LENGTH_UNIT ... INCH      → mm (×1000)
LENGTH_UNIT ... METER     → m (기존 유지)
단위 없음                  → bbox diagonal > 100 → mm 추측
```

### 내부 데이터 구조 (모든 값 mm 통일)
```python
{
    'edges': [Edge, Edge, ...],       # STEP native edges
    'verts_mm': np.array([[x,y,z], ...]), # 모든 vertex (mm)
    'bbox_mm': {
        'xmin','xmax','ymin','ymax','zmin','zmax',  # min/max
        'xl','yl','zl',                             # span (xmax-xmin 등)
        'center_mm': ((xmin+xmax)/2, ...)           # center
    },
    'bbox': {...},        # bbox_mm을 m로 나눈 값
    'use_mm': True
}
```

---

## 2. Orthographic Rendering (`render_ortho_stl`)

### 3 뷰 정의
| 뷰 | 수평축 | 수직축 | 시야 방향 |
|----|--------|--------|-----------|
| XZ | X | Z | +Y (front) |
| YZ | Y | Z | +X (side) |
| XY | X | Y | +Z (top) |

### 렌더링 과정
1. **STL 내보내기**: `shape.vals()[0].exportStl()` → temp file
2. **STL 로드**: `trimesh.load()` → vertices + faces
3. **Back-face culling**: face normal · view_direction > 0 인 면만
4. **Face-filled rendering**: 
   - front-facing faces → gray fill (200,200,200)
   - silhouette edges → gray line (same color)
   - white background (255,255,255)
5. **View label**: X→, Z↑ 등 axis 라벨

### scale 계산
```python
h_span = xmax - xmin; v_span = ymax - ymin
margin = 0.10  # 10% padding
fit_scale = min(1100*(1-0.2)/h_span, 1100*(1-0.2)/v_span)
offset_x = 1100//2 - center_h * fit_scale
offset_y = 1100//2 - center_v * fit_scale
```

### pixel ↔ CAD 변환 함수
```python
# CAD → pixel
def to_px(h, v):
    px = int(round(h * fit_scale + offset_x))
    py = int(round(1100 - (v * fit_scale + offset_y)))  # flip Y
    return px, py

# pixel → CAD (역산)
CAD_h_mm = (px - offset_x) / fit_scale
CAD_v_mm = (1100 - py - offset_y) / fit_scale
```

---

## 3. VLM 호출 (`get_vlm`)

### 프롬프트
```
Find ALL sharp convex extremities of the geometry.
These are the pointed protruding ends: wing tips, fin tips, blade tips, canard tips,
and in general the outermost/innermost sharp points along the longest span (top & bottom,
left & right, front & back edges) where thin blade/fin/wing structures terminate.
Do NOT mark smooth curves, rounded bodies, or flat surfaces.
Return ONLY JSON with double quotes:
{"tips": [{"tip_id": N, "x": pixelX, "y": pixelY}, ...], "image_width": W, "image_height": H}
```

### 호출 방식
```python
ollama.chat(
    model='orcarouter/qwen3.8-27b-uncensored:latest',
    messages=[{"role":"user","content":VL_PROMPT,"images":[image_path]}],
    stream=False
)
```

### VLM 반환 형식
```json
{
  "tips": [
    {"tip_id": 1, "x": 96, "y": 480},
    {"tip_id": 2, "x": 898, "y": 448}
  ],
  "image_width": 1000,
  "image_height": 1000
}
```

---

## 4. VLM 응답 파싱 (`parse_vlm`)

### 지원하는 형식
- `{image_width, image_height, tips: [...]}`
- `{tips: [...], image_size: [w,h]}`
- `{tips: [...], imageSize: {...}}`
- `{tip_id, x, y}` 단일 객체
- `[{tip_id, x, y}, ...]` 배열
- `{x1, y1, x2, y2}` bbox 형식

### image_width/image_height 처리
```python
def extract_tips(obj):
    imsz_w = obj.get('image_width', obj.get('imageWidth', None))
    imsz_h = obj.get('image_height', obj.get('imageHeight', None))
    if imsz_w and imsz_h:
        return int(imsz_w), int(imsz_h)
    
    # fallback
    imsz = obj.get('image_size', obj.get('imageSize', obj.get('img_size', None)))
    
    # tips 먼저 확인 (image_size 없어도 작동)
    tips = obj.get('tips', None)
    if tips: return tips, imsz_h
```

---

## 5. 스케일 보정

### 문제
VLM이 `image_width=1000` 기준으로 pixel을 반환하지만, 실제 PNG는 `1100×1100`입니다.
따라서 **스케일 보정 없이 pixel을 사용하면 CAD 역산이 어긋납니다**.

### 보정 과정
```python
# VLM이 image_width=1000으로 반환 → 실제 이미지 1100에 맞게 보정
scale_w = 1100 / 1000 = 1.1
scale_h = 1100 / 1000 = 1.1

# tips_vlm_scaled 생성 (이미지 상 pixel 좌표)
for tp in tips_vlm:
    tips_vlm_scaled.append({
        'tip_id': tp['tip_id'],
        'x': tp['x'] * scale_w,   # 96 → 105.6 (1100 기준)
        'y': tp['y'] * scale_h
    })
```

### annotated PNG 그리기
**스케일 보정된 pixel**(1100 기준)로 그려야 이미지에 정확히 맞습니다.

```python
for tip in tips_vlm_scaled:
    tx, ty = int(tip['x']), int(tip['y'])
    # 주황색 큰 원
    draw.ellipse([tx-35, ty-35, tx+35, ty+35], outline="orange", width=5)
    draw.ellipse([tx-25, ty-25, tx+25, ty+25], fill="orange")
```

---

## 6. Pixel → CAD 역산

```python
# tips_vlm_scaled (1100 기준) → CAD(mm)
CAD_h_mm = (px - offset_x) / fit_scale
CAD_v_mm = (1100 - py - offset_y) / fit_scale
# ⚠️ h_min/v_min 추가하지 않음! fit_scale+offset에 이미 center 기준 offset 포함
```

각 뷰별 의미:
| 뷰 | h (CAD_h_mm) | v (CAD_v_mm) |
|----|-------------|-------------|
| XZ | X | Z |
| YZ | Y | Z |
| XY | X | Y |

---

## 7. Triangulation (`triangulate`)

### 3-view hints clustering
```python
view_axes = {'XZ':(0,2), 'YZ':(1,2), 'XY':(0,1)}

# 각 뷰의 tip hints를 clustering
for vn, tips in tips_by_view.items():
    ah, av = view_axes[vn]  # XZ→(0,2), YZ→(1,2), XY→(0,1)
    for tip in tips:  # tip = [CAD_h, CAD_v, 0.0]
        # 같은 3D 지점에 매칭되는 hint를 찾음 (0.05mm tol)
        # 없으면 새 cluster 생성
```

### 3D 좌표 복원
```python
for cl in clusters:
    x=y=z=None
    for vn, tip, ah, av in cl['hints']:
        if ah==0 and av==2: x, z = tip[0], tip[1]   # XZ
        elif ah==1 and av==2: y, z = tip[0], tip[1]  # YZ
        elif ah==0 and av==1: x, y = tip[0], tip[1]  # XY
    
    if x and y and z: result.append([x,y,z])
    else: missing channel는 verts_mm에서 가장 가까운 점으로 보간
```

### 첫 번째 Dedup (50mm)
```python
final = []
for t in result:
    if all(np.linalg.norm(t-f) >= 50.0 for f in final):
        final.append(t)
```

---

## 8. Final Dedup (Y-Z Dedup + Max-X Filter)

**CAD 좌표에서 한 번만 수행** (pixel에서는 수행하지 않음).

### 로직
```python
tol = max(xl, yl, zl) * 0.05  # BBox 최대 span의 5%

deduped = []
for t in result:
    placed = False
    for i, d in enumerate(deduped):
        dx = abs(t[0] - d[0])
        dy = abs(t[1] - d[1])
        dz = abs(t[2] - d[2])
        
        if dx < tol and dy < tol and dz < tol:
            # x, y, z가 모두 tol 이내 → 동일한 지점
            # x가 큰 것만 남김 (wing tip은 X max 방향)
            if t[0] > d[0]:
                deduped[i] = t
            placed = True
            break
    if not placed:
        deduped.append(t)
```

### Dedup 기준
| 조건 | 값 | 설명 |
|------|-----|------|
| **tolerance** | `max(xl, yl, zl) × 0.05` | BBox 최대 span의 5% |
| **매칭** | dx < tol AND dy < tol AND dz < tol | 3차원 거리 기준 |
| **선택** | x가 가장 큰 점 | wing tip은 X max 방향 |
| **최종 결과** | deduped 리스트 | 최종 tip 목록 |

---

## 실행 방법

### 기본 (VLM 자동 호출)
```bash
python vlm-step-tip-detect.py <input.stp>
```

### VLM 없이 CAD snap만
```bash
python vlm-step-tip-detect.py <input.stp> --no-vlm
```

---

## 출력 파일

| 파일 | 형식 | 설명 |
|------|------|------|
| `{name}_tip_points.csv` | CSV (헤더 없음) | `x,y,z` (m, 6자리 소수점), 한 줄 = 한 tip |
| `{name}_tip.png` | PNG | 3D iso 뷰 (카메라: (-1,-1,1) 방향) + 주황색 tip marker (r=14/10) |
| `{name}_XZ_annotated.png` | PNG | XZ 뷰 VLM detection 결과 (주황색 원, r=35/25) |
| `{name}_YZ_annotated.png` | PNG | YZ 뷰 VLM detection 결과 |
| `{name}_XY_annotated.png` | PNG | XY 뷰 VLM detection 결과 |

---

## Dependencies

```bash
pip install cadquery numpy Pillow opencv-python trimesh ollama
```

---

## Known Issues

| 항목 | 설명 | 대응 |
|------|------|------|
| **VLM timeout** | PNG가 크거나 VLM 모델이 무거우면 응답 없음 | timeout 늘리기, bbox 직접 입력 가능 |
| **image_size mismatch** | VLM이 실제 PNG 크기와 다른 image_width 반환 | **2026-08-12 fix**: 동적 스케일링 적용 |
| **VLM 응답 변동** | 같은 입력에도 VLM이 다른 tip을 검출할 수 있음 | dedup tol을 충분히 크게 설정 (0.05) |
| **triangulate incomplete** | 3 view 중 1개에서만 tip 받으면 일부 좌표 미정복 | verts_mm interpolation으로 보간 |
| **STL export 실패** | 일부 STEP 형식에서 exportStl 실패 시 edges-only fallback | edges_only_img()로 기본 동작 |

---

## History

- **2026-08-12**: VLM image_size 기반 동적 스케일링, annotated PNG 스케일 보정된 pixel 사용, pixel→CAD 직결 역산, dedup tol 0.05 × max_bbox (X,Y,Z 3차원), `sharp concave points` 프롬프트 추가. VLM 응답 없을 때 UnboundLocalError 방지.
- **2026-08-11**: mm 통일, pixel→CAD 직결 역산 (fit_scale+offset만), VLM bbox → pixel center → CAD(mm) → snap to edges → CAD refine → triangulate 파이프라인 확정.
- **2026-08-05**: pixel-based VLM tip detection 초기 버전.
