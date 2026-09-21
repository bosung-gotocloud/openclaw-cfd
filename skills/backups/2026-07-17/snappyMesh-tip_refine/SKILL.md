---
name: snappyMesh-tip_refine
description: STL-based snappyHexMesh with tip-wake line refinement via searchableBoxes.
---

# snappyMesh-tip_refine Skill

STL-based snappyHexMesh mesh generation with **tip wake line refinement**. Auto-discovers `{basename}_tip_points.csv` and generates X-direction wake line refinement regions using searchableBoxes. Falls back to original refine-box-only mode if no tip CSV found.

**Based on:** `snappyMesh` skill (original unchanged)
**Location:** `~/.openclaw/workspace/skills/snappyMesh-tip_refine/`

---

## ⚠️ Golden Rule — Never Modify Template Files

**The template directory (`skills/snappyMesh-tip_refine/assets/snappyHexMesh-case-template/`) is READ-ONLY.**

---

## Batch Mode

```bash
cp skills/snappyMesh-tip_refine/scripts/*.py <target_dir>/
cd <target_dir>
python3 calculate_mesh_params.py <filename>.stl
python3 block_mesh.py <filename>_mesh_args.json
python3 snappy_mesh.py <filename>_mesh_args.json
```

---

## Workflow

### Step 0: Copy Scripts

```bash
cp /home/bosung/.openclaw/workspace/skills/snappyMesh-tip_refine/scripts/*.py <target_dir>/
```

### Execution Order

```
1. calculate_mesh_params.py <filename>.stl   → JSON 생성 (tip CSV 자동 감지)
2. block_mesh.py <filename>_mesh_args.json   → template 복사 → blockMesh 실행
3. snappy_mesh.py <filename>_mesh_args.json  → STL 복사 → OBJ 생성 → snappyHexMeshDict 수정
                                                 → tip wake line searchableBox 생성
                                                 → block_mesh.py에서 생성된 polyMesh/boundary 사용
                                                 → decomposePar → snappyHexMesh 병렬 → reconstructParMesh
                                                 → STL surface patch type patch → wall 고정
```

---

## Tip Wake Line Refinement

### Auto-Discovery
If `{basename}_tip_points.csv` exists in the same directory as the STL file, it is automatically loaded.
- **CSV format:** `x,y,z` header + data rows — OR — no header (data rows only)
- **Header detection:** If the first field starts with a letter → treated as header and skipped
- **No header:** All rows treated as data
If no CSV found, workflow proceeds in refine-box-only mode.

### Implementation: searchableBox (thin wake lines)

Each tip point generates a thin searchableBox extending in +X direction to `refine_box_xmax`:

```foam
geometry
{
    wake_line_0
    {
        type searchableBox;
        min (tip_x  refine_ty  refine_tz);
        max (refine_xmax  refine_ty+refine_dy  refine_tz+refine_dz);
    }
}

castellatedMeshControls
{
    refinementRegions
    {
        wake_line_0
        {
            mode    inside;
            levels  ((1 WAKE_LEVEL));
        }
    }
}
```

### Wake Line Parameters

| Parameter | Formula | Description |
|------|------|------|
| **tip_wake_refine_size** | `surf_size` | Cell size along wake line |
| **WAKE_LEVEL** | = `surf_size_level` | Wake refinement level |
| **Line origin** | Tip point (x, y, z) | From CSV |
| **Line extent** | X: tip → refine_box_xmax, Y/Z: tip-centered, span=10×surf_size | X-direction only |
| **Count** | Matches CSV row count | One box per tip point |

The smaller cell size wins in the intersection zone between wake line box and refine box.

---

## Parameters JSON Schema (tip CSV found)

```json
{
  "base_name": "LC62-50H",
  "tip_csv_path": "/path/to/LC62-50H_tip_points.csv",
  "tip_points_count": 6,
  "tip_points": [{"x": -0.613, "y": -0.692, "z": -0.043}, ...],
  "tip_wake_lines": [
    {
      "origin": [-0.613, -0.692, -0.043],
      "end": [7.568, -0.692, -0.043],
      "min": [-0.613, -0.724, -0.075],
      "max": [7.568, -0.660, -0.011]
    }
  ],
  "tip_wake_refine_size": 0.0126595,
  "wake_refine_level": 5
}
```

### Refinement Level Defaults

| Parameter | Default | Description |
|--|------|--|
| **surf_size_level** | 5 | Surface refinement level |
| **min_size_level** | 6 | Volume mesh min size level |
| **refine_size_level** | 2 | Refine box level |
| **wake_refine_level** | = surf_size_level | Wake line refinement level |

---

## Backwards Compatibility

- If no `{basename}_tip_points.csv` exists → works exactly like original `snappyMesh` skill
- No tip-related JSON fields added if CSV not found
- `skills/snappyMesh/` - **NOT MODIFIED**

---

## Comparison: snappyMesh vs snappyMesh-tip_refine

| Feature | snappyMesh | snappyMesh-tip_refine |
|---------|--|------|
| Input | STL | STL (+ optional tip CSV) |
| Tip CSV auto-discovery | ✗ | ✓ |
| Wake line refinement | ✗ | ✓ (X-direction from tips) |
| Wake implementation | - | searchableBox |
| **refine_size_level** | = min_size_level - 1 | **2** |
| **surf_size_level** | 6 | **5** |
| **min_size_level** | = surf_size_level + 2 | **6** |
| **wake_refine_level** | - | **= surf_size_level** |
| **tip_wake_refine_size** | - | **= surf_size** |
| Backwards compat | - | Fallback to refine-box-only |

---

## Workflow Rules

- **calculate_mesh_params.py 실행 후 반드시 모든 파라미터를 표로 보여주고 승인 받을 것**
- **사용자 승인 전에 block_mesh.py, snappy_mesh.py 절대 실행 금지**
- 파라미터 계산 → 확인 → 승인 → 실행 (절대 순서 위반 금지)
- **Golden Rule:** JSON 직접 편집, 스크립트 수정 아님

---

## File Structure

```
skills/snappyMesh-tip_refine/
├── SKILL.md
├── scripts/
│   ├── calculate_mesh_params.py  ← Stage 1: param calc + tip CSV discovery
│   ├── block_mesh.py             ← Stage 2: blockMesh
│   └── snappy_mesh.py            ← Stage 3: snappyHexMesh + checkMesh
└── assets/
    └── snappyHexMesh-case-template/
        └── system/
            ├── blockMeshDict
            ├── snappyHexMeshDict (wake line placeholder support)
            ├── controlDict
            ├── decomposeParDict
            ├── fvSchemes
            └── fvSolution
```

---

## Known Issues & Fixes

| Issue | Resolution |
|------|--|
| Wake line over-refinement causing OOM | refine_size_level=2, surf_size_level=5, wake_refine_level=surf_size_level |
| tip_wake_refine_size changed | = surf_size (was 2×surf_size) |
| template blockMeshDict leading whitespace | Removed leading spaces from vertices block |
| OpenFOAM v2512 separate mesh files | block_mesh.py checks `points` file instead of single `polyMesh` |
| No tip CSV → compute error | tip_wake_lines check prevents errors |
| surfaceConvert -writeFormat error | Falls back to manual OBJ generation |
| CSV no-header support | `discover_tip_points()` auto-detects header — if first field starts with a letter, treats as header; otherwise reads all rows as data |
| STL surface patch type | snappyMesh 실행 후 `constant/polyMesh/boundary`에서 type patch → wall 강제 변환 (snappy_mesh.py post-processing) |

## Test Results (LC62-50H)

| Stage | Result |
|--|------|
| blockMesh | 50 × 27 × 17 = 22,950 cells |
| snappyHexMesh | Completed (parallel 16proc) |
| checkMesh | **OK** |
| Final mesh | ~1,007,848 cells |
| refine_box | level 2, cell_size=0.025m |
| wake_line×6 | level 5, cell_size=surf_size |
| LC62-50H_surface.stl | constant/triSurface/ ✅ |
| boundary patches | far + LC62-50H_surface ✅ |

---

## 🔧 2026-07-13 Final Script Updates

### `block_mesh.py` (2026-07-13 21:50 UTC)
- **Template directory fallback**: `template_dir`을 JSON에서 먼저 찾고, 없으면 `assets/snappyHexMesh-case-template/` 사용
- **OpenFOAM v2512 separate mesh 검증**: `polyMesh/points` 파일 존재 여부로 mesh 생성 확인 (단일 polyMesh 파일 아님)
- **blockMeshDict 수정 로직**:
  - vertices: far box corner 좌표 치환 (xmin/ymin/zmin ~ xmax/ymax/zmax)
  - block divisions: `max_size` 기반 셀 수 계산 (n_x, n_y, n_z)
  - faces: far box 면 정의 치환 (xmin/xmax/ymin/ymax/zmin/zmax 라벨)
- **controlDict**: writeControl none, writeFrequency 0 고정

### `snappy_mesh.py` (2026-07-13 21:52 UTC)
- **STL surface patch type patch → wall 강제 변환**: snappyMesh 실행 후 `boundary` 파일에서 STL patch의 type을 `patch`에서 `wall`로 변경
- **Tip wake line searchableBox 생성**:
  - `build_wake_line_section()` 함수로 geometry + refinementRegions 섹션 생성
  - wake line min/max 좌표 계산 (Y/Z: 10×surf_size span, X: tip → refine_box xmax)
  - placeholder 기반 치환 (`TIP_WAKE_LINE_PLACEHOLDER`, `TIP_WAKE_LINE_REF_PLACEHOLDER`)
- **snappyHexMeshDict_addLayers**: castellatedMesh no, snap no, explicitFeatureSnap false로 생성
- **checkMesh 자동 실행**: workflow 완료 후 자동으로 checkMesh 실행 및 결과 출력
- **processor 디렉토리 정리**: snappyHexMesh parallel 실행 후 processor* 디렉토리 제거
- **case.foam 생성**: OpenFOAM case marker 파일 생성
- **surfaceConvert fallback**: 실패 시 STL → OBJ 수동 생성 (vertex map deduplication)

### `calculate_mesh_params.py` (2026-07-10 04:39 UTC)
- **CSV header 감지**: `discover_tip_points()`에서 첫 필드가 문자로 시작하면 header로 간주하고 skip
- **No header 지원**: 모든 row를 데이터로 처리
- **Tip CSV 없으면 refine-box-only 모드**: tip_wake_lines check로 에러 방지
