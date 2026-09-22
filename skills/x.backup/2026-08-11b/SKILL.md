---
name: tip-detect
description: STEP CAD geometry processing and VLM-based tip detection
---

# tip-detect — STEP CAD Tip Detection

STEP CAD 파일에서 날끝(wingtip), 꼬리끝(tailtip), canard 등 뾰족한 tip을 검출하는 도구 모음입니다.

## 스킬 목록

### 1. `vlm-tip-detect.py` — **VLM 기반 Tip 검출 (권장, 최신)**
- STEP → 3 orthographic views (XZ, YZ, XY) PNG → VLM per-view bbox → pixel→CAD(mm) 변환 → snap to edges → triangulate → CSV/PNG

### 2. `step-find-tip.py` — CAD 기하 기반 Tip 검출 (비-VLM fallback)
- STEP native edges → silhouette extraction → sharp corner → convexity → dedup → classification

---

## vlm-tip-detect.py — VLM 기반 Tip 검출 (최신 버전)

### 2026-08-11 — 최종 워크플로우 확정

```
STEP 파일 (cadquery)
    ↓
load_step(): STEP header unit 감지 + mm 통일 저장
    - LENGTH_UNIT M → mm
    - LENGTH_UNIT INCH → mm 변환
    - unit 없음 → diag > 100 기준 mm 추측
    - 내부: 무조건 mm로 저장 (verts_mm, bbox_mm)
    ↓
3 orthographic views render_ortho() (1000×1000 PNG)
    - XZ (front): X horizontal, Z vertical
    - YZ (side): Y horizontal, Z vertical
    - XY (top): X horizontal, Y vertical
    - scale: bbox span → 1000×1000 fit_scale
    - pixel→CAD: fit_scale + offset만으로 직결 역산
    ↓
VLM(qwen3.6:35b) per-view 호출 → bbox JSON 반환
    - 프롬프트: "날개끝, 꼬리끝, canard끝 등 뾰족한 끝부분을 찾아. 각 끝부분 주변에 30x30px bbox로 반환해. 형식: [{\"bbox_2d\":[minX,minY,maxX,maxY],\"label\":\"이유\"}]"
    - VLM은 bbox corners [minX, minY, maxX, maxY] 반환
    ↓
parse_vlm(): VLM 응답 파싱 (JSON array/object 자동 감지)
    ↓
pixel→CAD(mm) 변환 (각 뷰별):
    - pixel center: px = (x1+x2)/2, py = (y1+y2)/2
    - CAD_h = (px - offset_x) / fit_scale
    - CAD_v = (img_size - py - offset_y) / fit_scale
    - fit_scale + offset만으로 역산 (h_min/v_min 불필요!)
    ↓
snap_to_edges(): CAD 좌표에서 해당 뷰 edges로 snap
    - tol = bbox_max_span × 0.05
    - sharp corner bonus (cos < 0.7 → score×2)
    ↓
triangulate(): multi-view tips → 3D 좌표
    - XZ hint: (h,v) → X,Z
    - YZ hint: (h,v) → Y,Z
    - XY hint: (h,v) → X,Y
    - 3 hints 합쳐 3D point 생성
    - 5mm 내 근접 tip 제거
    ↓
Output: {name}_tip_points.csv (mm 단위) + {name}_tip.png (iso view + red tip circles)
```

### Pixel → CAD 매핑 핵심 로직 (중요)

```python
# render_ortho에서 to_px 정의:
def to_px(h, v):
    px = int(round(h * fit_scale + offset_x))    # h → horizontal pixel
    py = int(round(img_size - (v * fit_scale + offset_y)))  # v → vertical pixel (flip)

# pixel → CAD inverse (to_px의 정확한 역산):
CAD_h_mm = (px - offset_x) / fit_scale          # X 또는 Y (view에 따라)
CAD_v_mm = (img_size - py - offset_y) / fit_scale  # Z 또는 Y (view에 따라)
# ⚠️ h_min, v_min을 더하지 않음! fit_scale + offset에 이미 center 기준 offset 포함
```

### snap_to_edges 핵심 로직

```python
for edge in edges:
    pts = edge.sample(200)
    for segment in pts:
        t = projected parameter on segment
        ph, pv = linear interpolation
        dist = |ph - cad_h| + |pv - cad_v|  # L1 distance
        if dist < tol:
            score = 1 / (dist + 0.001)
            # sharp corner bonus: tangent angle > 37° (cos < 0.7)
            score *= 2
        if score > best_score:
            best_score = score
            best_pt = point_on_edge  # 3D (mm)
```

### triangulate 핵심 로직

```python
for each tip hint (view, px, py):
    - XZ hint: x=px, z=py  (y=None)
    - YZ hint: y=px, z=py  (x=None)
    - XY hint: x=px, y=py  (z=None)
    cluster hints within 50mm threshold
    if all x,y,z available → 3D tip
    else → verts_mm에서 nearest fill
dedup within 50mm → final tips
```

### Workflow Details

1. **STEP 로드**: `load_step()` — cadquery importStep(), edge/vertex 추출, bbox(mm) 계산, unit 감지
2. **3-view rendering**: `render_ortho()` — 각 view별 1000×1000 PNG 생성
   - bbox span → fit_scale → 이미지에 fit
   - edge sampling 30개/edge, cv2.line로 draw
   - fit_scale, offset, to_px 함수를 di(dict)에 저장
3. **VLM 호출**: `get_vlm()` — ollama.chat(qwen3.6:35b, images=[png])
   - 프롬프트: 날개끝/꼬리끝/canard끝 등 뾰족 부분 → bbox_2d
   - timeout 60초 (PNG 너무 크면 초과 가능)
4. **VLM 응답 파싱**: `parse_vlm()` — JSON array/object 자동 감지, bbox_2d [minX,minY,maxX,maxY] 형식 표준화
5. **pixel→CAD 변환**: 각 bbox center를 CAD(mm)로 역산 (fit_scale + offset)
6. **snap to edges**: CAD 좌표에서 view별 edges로 snap (tol 5%, sharp corner bonus)
7. **triangulate**: multi-view tips → 3D (hints clustering + 5mm dedup)
8. **output**: CSV (mm) + PNG (iso + tip circles)

### Installation

```bash
pip install cadquery numpy Pillow opencv-python
```

### Usage

```bash
# 기본 사용 (VLM 자동 호출)
python vlm-tip-detect.py <input.stp>

# VLM 없이 CAD snap만
python vlm-tip-detect.py <input.stp> --no-vlm

# manual tips for testing (JSON string)
python vlm-tip-detect.py <input.stp> --tips '[{"bbox_2d":[100,100,200,200],"label":"test"}]'
```

### Output

- **`{name}_tip_points.csv`**
  - 헤더 없음, `x,y,z` (mm 단위, 6자리 소수점)
  - 각 줄: 하나의 3D tip 좌표

- **`{name}_tip.png`**
  - Isometric 3D 뷰 (gray wireframe)
  - tip 위치: 빨간 동그라미 (r=10px)

### Known Issues & Limitations

| 항목 | 설명 | 대응 |
|------|------|------|
| **VLM timeout** | PNG가 크거나 VLM 모델이 무거우면 SIGKILL | timeout 늘리기 또는 bbox 직접 입력 (--tips) |
| **YZ view bbox** | YZ에서 tip bbox가 이미지 밖으로 나가면 snap 실패 | 여러 view에서 tip을 받도록 함 |
| **pixel→CAD 역산** | fit_scale + offset만으로 역산, h_min/v_min 추가하지 않음 | **이 규칙 절대 위반 금지** |
| **snap tol** | tol=5% of bbox span → 큰 모델은 tol 큼 | 필요시 --tol 파라미터 추가 |
| **triangulate** | 3 view 중 1개에서만 tip 받으면 incomplete | 최소 2 view에서 tip 필요 |

### History

- **2026-08-11**: mm 통일, pixel→CAD 직결 역산 (fit_scale+offset만), VLM bbox 기반 workflow 확정. VLM bbox → pixel center → CAD(mm) → snap to edges → triangulate 파이프라인 완성.
- **2026-08-06**: step-tip-detect.py v3 (silhouette + sharp corner + convexity). LC62-50B에서 11 tip 검출.
- **2026-08-05**: pixel-based VLM tip detection (bbox format, format="json" 제거, temperature 0.5).
- **2026-07-30**: STEP tip detection 초기 개발.
