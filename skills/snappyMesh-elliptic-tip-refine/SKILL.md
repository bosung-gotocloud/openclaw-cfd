---
name: snappyMesh-elliptic-tip-refine
description: STL-based snappyHexMesh with SALOME-like elliptic far boundary and refine ellipsoid, plus tip-wake line refinement.
---

# snappyMesh-elliptic-tip-refine

STL 기반 snappyHexMesh 메쉬 생성 스킬입니다. 기존 `snappyMesh-tip-refine`의 rectangular far/refine box 대신, `salome-elliptic`과 동일한 **x축 대칭 ellipsoid**을 사용합니다.

## 핵심 구조

- **model STL**: `triSurfaceMesh`, `wall`, `addLayers` 대상
- **far ellipsoid STL**: `triSurfaceMesh`, outer boundary patch, 기본 `patch`
- **refine ellipsoid STL**: `triSurfaceMesh`, refinement region 이름만 등록, `refinementSurfaces`에 넣지 않는다
- **tip wake lines**: `searchableBox` refinement regions
- **blockMesh box**: far ellipsoid를 감싸는 margin이 포함된 base box

Far ellipsoid는 SALOME elliptic 규칙을 따릅니다:

```text
far_dx = 10 * xl
far_dy = 5 * yl
far_dz = 10 * zl

far_a_x  = far_dx / 2
far_a_yz = max(far_dy, far_dz) / 2

far_center_x = model_cx + 0.25 * far_dx
far_center_y = model_cy
far_center_z = model_cz
```

Refine ellipsoid도 동일 규칙입니다:

```text
refine_dx = 5 * xl
refine_dy = 2 * yl
refine_dz = 2 * zl

refine_a_x  = refine_dx / 2
refine_a_yz = max(refine_dy, refine_dz) / 2

refine_center_x = model_cx + 0.25 * refine_dx
```

## 워크플로우

### Step 0: 스크립트 복사

```bash
cp /home/bosung/.openclaw/workspace/skills/snappyMesh-elliptic-tip-refine/scripts/*.py <target_dir>/
```

대상 디렉토리에 다음 파일이 있어야 합니다:

```text
<basename>.stl
<basename>_tip_points.csv   # optional
```

### Step 1: 파라미터 계산 + ellipsoid STL 생성

```bash
python3 calculate_mesh_params.py <basename>.stl
```

생성물:

```text
<basename>_mesh_args.json
<basename>_far_ellipsoid.stl
<basename>_refine_ellipsoid.stl
```

이 단계에서 JSON과 ellipsoid STL을 확인한 뒤 승인을 받아야 합니다.

### Step 2: blockMesh

```bash
python3 block_mesh.py <basename>_mesh_args.json
```

blockMesh box는 JSON의 `block_box`를 사용합니다:

```text
block_box = far ellipsoid bounding box + margin
margin = max(0.05 * far_max_extent, max_size)
```

### Step 3: snappyHexMesh

```bash
python3 snappy_mesh.py <basename>_mesh_args.json
```

다음 순서로 실행됩니다:

1. model/far/refine STL을 `constant/triSurface/`로 복사
2. `snappyHexMeshDict` placeholder 치환
3. tip wake line geometry/refinement injection
4. `decomposePar`
5. `mpirun snappyHexMesh -parallel`
6. `reconstructParMesh`
7. boundary patch type 수정
   - model surface → `wall`
   - far surface → `patch` 또는 JSON 지정 type
8. processor cleanup
9. `checkMesh`
10. `case.foam` 생성

## 타임스텝 디렉토리 구조 (정상 동작)

snappyHexMesh는 내부적으로 3개 타임스텝으로 진행하며, 각 디렉토리는 특정 단계를 나타냅니다:

| 디렉토리 | 내용 |
|----------|------|
| `1/` | castellatedMesh 단계 결과 |
| `2/` | snap 단계 결과 |
| `3/` | **최종 결과** — addLayers 포함, 최종 mesh가 저장됨 |

> ⚠️ **중요**: 최종 메쉬는 `3/polyMesh`에 저장됩니다. `constant/polyMesh`는 초기 blockMesh 상태일 수 있으며, 실제 시뮬레이션에 사용할 mesh는 `3/` 디렉토리를 기준으로 합니다.
>
> 최종 결과 확인 방법:
> ```bash
> cd <case_dir>/3 && checkMesh
> ```
>
> `boundary` 파일에 model surface가 `wall` 타입으로, far surface가 `patch` 타입으로 등록되어 있다면 정상입니다.

## snappyHexMeshDict 역할

<details>
<summary>핵심 template 구조</summary>

```foam
geometry
{
    "MODEL_STL"
    {
        type triSurfaceMesh;
        name MODEL_SURFACE;
    }

    "FAR_STL"
    {
        type triSurfaceMesh;
        name FAR_SURFACE;
    }

    "REFINE_STL"
    {
        type triSurfaceMesh;
        name refine_ellipsoid;
    }

    // TIP_WAKE_LINE_PLACEHOLDER
}

castellatedMeshControls
{
    refinementSurfaces
    {
        MODEL_SURFACE
        {
            patchInfo { type wall; }
            level MODEL_LEVEL;
        }

        FAR_SURFACE
        {
            patchInfo { type FAR_PATCH_TYPE; }
            level FAR_LEVEL;
        }
    }

    refinementRegions
    {
        // TIP_WAKE_LINE_REF_PLACEHOLDER
        refine_ellipsoid
        {
            mode REFINE_MODE;
            levels ((1 REFINE_LEVEL));
        }
    }
}

addLayersControls
{
    relativeSizes true;
    thicknessModel totalThickness;
    layers
    {
        MODEL_SURFACE
        {
            nSurfaceLayers    BASE_NLAYERS;
            firstLayerHeight  BASE_FIRSTLAYER;   // 0.5 = local surface cell size의 50%
            expansionRatio    BASE_EXPANSION_RATIO;
        }
    }
}
```

> `firstLayerHeight 0.5` = 첫 셀 높이가 local surface cell size의 50%.
> `nSurfaceLayers`/`nLayers`는 JSON `layers` 값, `expansionRatio`는 JSON `growth` 값.
> **주의**: `relativeSizes false`일 때 `firstLayerHeight`를 길이 단위로 쓰면 snappyHexMesh가
> `Entry 'layers' not found` 오류를 낸다. 반드시 `relativeSizes true` + per-surface dict 구조를 사용할 것.

</details>

## JSON 주요 필드

```json
{
  "base_name": "model",
  "xl": 1.0,
  "yl": 0.5,
  "zl": 0.2,
  "max_size": 0.2,
  "surf_size": 0.00625,
  "min_size": 0.003125,
  "surf_size_level": 5,
  "min_size_level": 7,
  "h1": 0.0001,
  "growth": 1.3,
  "layers": 10,

  "far_ellipsoid": {
    "shape": "axisymmetric_x",
    "dx": 10.0,
    "dy": 2.5,
    "dz": 2.0,
    "a_x": 5.0,
    "a_yz": 1.25,
    "center": [1.25, 0.0, 0.0],
    "stl": "model_far_ellipsoid.stl",
    "patch_name": "far",
    "patch_type": "patch",
    "boundary_level": [0, 1]
  },

  "refine_ellipsoid": {
    "shape": "axisymmetric_x",
    "refine_dx": 5.0,
    "refine_dy": 1.0,
    "refine_dz": 0.4,
    "a_x": 2.5,
    "a_yz": 0.5,
    "center": [1.25, 0.0, 0.0],
    "stl": "model_refine_ellipsoid.stl",
    "mode": "inside",
    "refine_level": 2
  },

  "block_box": {
    "dx": 10.5,
    "dy": 2.75,
    "dz": 2.5,
    "min": [0.0, -1.375, -1.25],
    "max": [10.5, 1.375, 1.25]
  },

  "tip_wake_lines": []
}
```

## 규칙

1. 기존 `snappyMesh-tip-refine`은 수정하지 않는다.
2. `calculate_mesh_params.py` 실행 후 파라미터/STL/JSON을 확인하고 승인을 받는다.
3. 승인 전 `block_mesh.py`, `snappy_mesh.py`를 실행하지 않는다.
4. far ellipsoid는 boundary surface로, refine ellipsoid는 refinement region으로만 사용한다.
5. `addLayers`는 model surface에만 적용한다.
6. far ellipsoid STL는 watertight해야 한다.

## 파일 구조

```text
skills/snappyMesh-elliptic-tip-refine/
├── SKILL.md
├── scripts/
│   ├── calculate_mesh_params.py
│   ├── block_mesh.py
│   ├── snappy_mesh.py
│   └── ellipsoid_stl.py
└── assets/
    └── snappyHexMesh-case-template/
        └── system/
            ├── blockMeshDict
            ├── controlDict
            ├── decomposeParDict
            ├── fvSchemes
            ├── fvSolution
            └── snappyHexMeshDict
```

## 주의사항

- `locationInMesh`는 **model 밖, far ellipsoid 안**에 있어야 합니다.
- blockMesh box는 far ellipsoid와 정확히 tangent되는 것보다 margin을 두는 것이 안정적입니다.
- far ellipsoid는 snapping 대상이므로 STL 해상도가 중요합니다.
- refine ellipsoid는 snapping surface가 아니므로 `refinementSurfaces`에 넣지 않습니다.
- tip wake box는 refine ellipsoid와 겹칠 수 있으며, 더细한 refinement level이 우선 적용됩니다.
