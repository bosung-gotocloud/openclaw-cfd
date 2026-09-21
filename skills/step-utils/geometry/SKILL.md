---
name: geometry
description: STEP CAD 기하 처리
---

# geometry/ — STEP CAD Geometry Processing

geometry/ 디렉토리의 모든 스킬은 STEP CAD 파일에서 기하학적 정보를 추출하는 도구를 제공합니다.

## 스킬 목록

### 1. `render_step_views.py` — STEP 다중뷰 렌더링 (debugging용)
- **방식**: cadquery native SVG export
- **용도**: debugging, 시각 확인

### 2. `step-find-tip.py` — 전통적 기하학적 Tip 검출
