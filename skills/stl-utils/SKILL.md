---
name: stl-utils
description: STL CAD 기하 처리 도구 모음. 분석(analyze), 스케일(scale), 이동(translate), 회전(rotate), 렌더링(render)
---

# stl-utils — STL CAD Geometry Processing Utilities

STL 파일의 기하학적 정보를 분석하고 변환하는 도구 모음입니다.
모든 스크립트는 **trimesh** 기반이며, STL 파일의 기하학 정보를 native하게 다룹니다.

## 단위 규칙

| 포맷 | 단위 | SI 변환 |
|------|------|-------|
| STL 바이너리 | mm (일반적) | × 0.001 |
| STL ASCII | mm (일반적) | × 0.001 |
| 외부모형에서 m 단위 STL | m | 그대로 사용 |

> **주의**: STL 파일은 단위 정보가 없으므로 기본 mm로 간주합니다.
> m 단위 STL을 입력하는 경우 `--unit m` 옵션을 사용하세요.

---

## 1. analyze_stl.py — STL 기하 분석

STL 파일의 BBox, 표면적, 투영면적, 무게중심을 분석합니다.

### 실행
```bash
python analyze_stl.py <input.stl> [output.json]
```

### 출력 JSON
```json
{
  "file": "example.stl",
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
- **Surface area**: 총 표면적 (m²) — trimesh `area` 기반
- **Projection area**: XY/XZ/YZ 평면 투영면적 (true mesh projection)
- **Center of gravity**: 무게중심 (균일 밀도 가정) — SI 단위(m)
- **Mesh stats**: vertex count, face count

### 옵션
| 옵션 | 설명 |
|------|------|
| `--unit m` | 입력 STL이 미터 단위일 때 |
| `--output` | 출력 파일명 |

### Dependencies
```bash
pip install trimesh numpy shapely
```

---

## 2. scale_stl.py — STL 스케일 변환

STL 파일을 기하 중심(centroid) 기준 스케일합니다.

### 실행
```bash
# Uniform scale (모든 방향 동일 비율)
python scale_stl.py <input.stl> --uniform 2.0

# Non-uniform scale (X, Y, Z 개별 비율)
python scale_stl.py <input.stl> --scale 1.0 2.0 1.5
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--uniform n` | 모든 방향 n배 |
| `--scale a b c` | X=a, Y=b, Z=c |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |
| `--unit m` | 입력 STL이 미터 단위일 때 |

### 출력 파일명 규칙
- Uniform: `<name>_<scale>.stl`
- Non-uniform: `<name>_<a>_<b>_<c>.stl`

### Dependencies
```bash
pip install trimesh
```

---

## 3. translate_stl.py — STL 이동

STL 파일을 주어진 오프셋만큼 이동합니다.

### 실행
```bash
python translate_stl.py <input.stl> --dx <x> --dy <y> --dz <z>
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--dx` | X 방향 이동 (미터 단위) |
| `--dy` | Y 방향 이동 (미터 단위) |
| `--dz` | Z 방향 이동 (미터 단위) |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |
| `--unit m` | 입력 STL이 미터 단위일 때 |

### 출력 파일명
`<name>_<dx>_<dy>_<dz>.stl`

### Dependencies
```bash
pip install trimesh
```

---

## 4. rotate_stl.py — STL 회전

STL 파일을 지정된 중심/축/각도만큼 회전합니다.

### 실행
```bash
python rotate_stl.py <input.stl> \
    --center 0 0 0 \
    --axis 0 0 1 \
    --angle 45
```

### 옵션
| 옵션 | 설명 |
|------|------|
| `--center x y z` | 회전 중심좌표 (미터) |
| `--axis i j k` | 회전축 벡터 (자동 normalization) |
| `--angle` | 회전각도 (도, degrees) |
| `--output` | 출력 파일명 (미지정 시 자동 생성) |
| `--unit m` | 입력 STL이 미터 단위일 때 |

### 출력 파일명
`<name>_<angle>.stl`

### Dependencies
```bash
pip install trimesh
```

---

## 5. render_stl.py — STL 다중뷰 렌더링

STL 파일을 3방향 정사영 + 3D iso 뷰 PNG로 렌더링합니다.

### 실행
```bash
python render_stl.py <input.stl>
```

### 출력 파일 (STL 파일이 있는 디렉토리에 저장)

| 파일 | 뷰 | 설명 |
|------|-----|------|
| `{name}_front.png` | XZ 정사영 | 측면에서 본 것 |
| `{name}_top.png` | XY 정사영 | 상단에서 본 것 |
| `{name}_side.png` | YZ 정사영 | 측면에서 본 것 |
| `{name}_3d.png` | 3D iso | 등각투영 |
| `{name}_bbox.csv` | BBox 정보 | extent_mm, min/max |

### 렌더링 특징
- **matplotlib + trimesh** 기반
- Mesh face rendering (투명도 60%)
- 각 뷰별 다른 색상 (front=blue, top=green, side=orange)
- 3D iso 뷰는 별도 1000×1000 PNG

### Dependencies
```bash
pip install trimesh numpy matplotlib
```

---

## 전체 파일 목록

| 파일 | 명령어 | 용도 |
|------|--------|------|
| `analyze_stl.py` | `python analyze_stl.py <file.stl>` | 기하 분석 (BBox/면적/무게중심) |
| `scale_stl.py` | `python scale_stl.py <file.stl> --uniform/-s a/b/c` | 스케일 변환 |
| `translate_stl.py` | `python translate_stl.py <file.stl> -d dx dy dz` | 이동 |
| `rotate_stl.py` | `python rotate_stl.py <file.stl> -c x y z -a i j k -t angle` | 회전 |
| `render_stl.py` | `python render_stl.py <file.stl>` | 다중뷰 렌더링 |

---

## 공통 의존성

```bash
pip install trimesh numpy shapely matplotlib
```

필수: trimesh, numpy
분석: shapely
렌더링: matplotlib

---

## 참고 사항

- 모든 스크립트는 trimesh 기반 STL native 처리
- analyze_stl.py만 SI(m)로 변환 출력, 나머지는 미터 단위 유지
- STL은 단위 정보가 없으므로 기본 mm로 간주 (`--unit m`로 오버라이드)
- 출력 파일명은 스크립트마다 규칙에 따라 자동 생성
