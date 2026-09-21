---
name: step-utils
description: STEP CAD 기하 처리 도구 모음. 분석(analyze), 스케일(scale), 이동(translate), 회전(rotate), 렌더링(render)
---

# step-utils — STEP CAD Geometry Processing Utilities

STEP CAD 파일의 기하학적 정보를 분석하고 변환하는 도구 모음입니다.
모든 스크립트는 **cadquery** 기반이며, STEP 파일 단위(unit)를 자동 감지합니다.

## 단위 규칙

| 명시 단위 | 감지 | SI 변환 |
|---------|------|---------|
| `.METRE.` | m | 그대로 사용 |
| `.MM.` 또는 `.MILLI.*METRE.` | mm | × 0.001 |
| 미명시 | mm (STEP 기본규약) | × 0.001 |

---

## 1. analyze_step.py — STEP 기하 분석

STEP 파일의 BBox, 표면적, 투영면적, 무게중심을 분석합니다.

### 실행
```bash
python analyze_step.py <input.step> [output.json]
```

### 출력 JSON
```json
{
  "file": "example.step",
  "bounding_box": {
    "xmin": 0.0, "xmax": 2.033,
    "ymin": -1.1, "ymax": 1.1,
    "zmin": 0.0035, "zmax": 0.698,
    "xl": 2.033, "yl": 2.2, "zl": 0.6945
  },
  "areas": {
    "total_surface": 4.567,
    "Axz": 1.234,
    "Axy": 2.345,
    "Ayz": 0.789
  },
  "center_of_gravity": {
    "cgx": 1.016, "cgy": 0.0, "cgz": 0.351
  }
}
```

### 주요 기능
- **BBox**: xmin/xmax/ymin/ymax/zmin/zmax + 길이(xl, yl, zl) — SI 단위(m)
- **Surface area**: 총 표면적 (m²)
- **Projection area**: XY/XZ/YZ 평면 투영면적 (true tessellation + shapely unary_union)
- **Center of gravity**: 무게중심 (균일 밀도 가정) — SI 단위(m)

### Dependencies
```bash
pip install cadquery numpy shapely
```

---

## 2. scale_step.py — STEP 스케일 변환

STEP 파일을 기하 중심(centroid) 기준 스케일합니다.

### 실행
```bash
# Uniform scale (모든 방향 동일 비율)
python scale_step.py <input.step> --uniform 2.0

# Non-uniform scale (X, Y, Z 개별 비율)
python scale_step.py <input.step> --scale 1.0 2.0 1.5
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--uniform n` | 모든 방향 n배 |
| `--scale a b c` | X=a, Y=b, Z=c |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |

### 출력 파일명 규칙
- Uniform: `<name>_<scale>.stp`
- Non-uniform: `<name>_<a>_<b>_<c>.step`

### Dependencies
```bash
pip install cadquery
```

---

## 3. translate_step.py — STEP 이동

STEP 파일을 주어진 오프셋만큼 이동합니다.

### 실행
```bash
python translate_step.py <input.step> --dx <x> --dy <y> --dz <z>
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--dx` | X 방향 이동 (STEP 원본 단위) |
| `--dy` | Y 방향 이동 (STEP 원본 단위) |
| `--dz` | Z 방향 이동 (STEP 원본 단위) |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |

### 출력 파일명
`<name>_<dx>_<dy>_<dz>.step`

### Dependencies
```bash
pip install cadquery
```

---

## 4. rotate_step.py — STEP 회전

STEP 파일을 지정된 중심/축/각도만큼 회전합니다.

### 실행
```bash
python rotate_step.py <input.step> \
    --center 0 0 0 \
    --axis 0 0 1 \
    --angle 45
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--center x y z` | 회전 중심좌표 (STEP 원본 단위) |
| `--axis i j k` | 회전축 벡터 (자동 normalization) |
| `--angle` | 회전각도 (도, degrees) |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |

### 출력 파일명
`<name>_<angle>.stp`

### Dependencies
```bash
pip install cadquery
```

---

## 5. render_step.py — STEP 다중뷰 렌더링

STEP 파일을 3방향 정사영 + 3D iso 뷰 PNG로 렌더링합니다.

### 실행
```bash
python render_step.py <input.stp>
```

### 출력 파일 (STEP 파일이 있는 디렉토리에 저장)

| 파일 | 뷰 | 설명 |
|------|-----|------|
| `{name}_front.png` | XZ 정사영 | 상단에서 본 것 |
| `{name}_top.png` | XY 정사영 | 상단에서 본 것 |
| `{name}_side.png` | YZ 정사영 | 측면에서 본 것 |
| `{name}_3d.png` | 3D iso | 등각투영 |
| `{name}_bbox.csv` | BBox 정보 | extent_mm, min/max |

### 렌더링 특징
- **matplotib** 기반
- Face-filled rendering (투명도 60%)
- 각 뷰별 다른 색상 (front=blue, top=green, side=orange)
- 3D iso 뷰는 별도 1000×1000 PNG

### Dependencies
```bash
pip install cadquery numpy matplotlib
```

---

## 전체 파일 목록

| 파일 | 명령어 | 용도 |
|------|--------|------|
| `analyze_step.py` | `python analyze_step.py <file.step>` | 기하 분석 (BBox/면적/무게중심) |
| `scale_step.py` | `python scale_step.py <file.step> --uniform/-s a/b/c` | 스케일 변환 |
| `translate_step.py` | `python translate_step.py <file.step> -d dx dy dz` | 이동 |
| `rotate_step.py` | `python rotate_step.py <file.step> -c x y z -a i j k -t angle` | 회전 |
| `render_step.py` | `python render_step.py <file.stp>` | 다중뷰 렌더링 |

---

## 공통 의존성

```bash
pip install cadquery numpy shapely matplotlib
```

필수: cadquery, numpy
분석: shapely
렌더링: matplotlib

---

## 참고 사항

- 모든 스크립트는 STEP 원본 단위를 자동 감지하여 처리
- analyze_step.py만 SI(m)로 변환 출력, 나머지는 원본 단위 유지
- cadquery Workplane wrapper 처리 내장 (val()/list 언래핑)
- 출력 파일명은 스크립트마다 규칙에 따라 자동 생성
