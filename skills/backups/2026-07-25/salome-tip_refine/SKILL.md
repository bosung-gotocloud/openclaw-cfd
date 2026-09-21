---
name: salome-tip_refine
description: SALOME-based mesh generation with tip-wake line refinement and viscous layers. STEP import → Netgen mesh → OpenFOAM case. No snappyHexMesh.
---

# salome-tip_refine Skill

SALOME-based two-step batch mesh generation for OpenFOAM. Adds **tip-wake line refinement** and **viscous boundary layers** in SALOME (Netgen) - **no snappyHexMesh dependency**.

**Based on:** `salome-tip_refine-snappy` skill (snappy parts removed, viscous layers added)
**Location:** `~/.openclaw/workspace/skills/salome-tip_refine/`
**SALOME path:** `/home/bosung/opt/salome/salome`
**Last confirmed:** 2026-07-25 (BL-based sizing: surf_size=4*T, min_size=2*T, tip_wake_refine_size=2*surf_size)

---

## ⚠️ Critical: Surface Curvature Must Be Enabled

`SetUseSurfaceCurvature(1)` **MUST be enabled** for stable STEP mesh computation.

## ⚠️ Critical: Viscous Layers in SALOME

Viscous layers are configured **inside** `compute_mesh.py` via `netgen.ViscousLayers(h1, layers, growth, far_faces, 1, smeshBuilder.FACE_OFFSET)`.
No separate snappyHexMesh layer config needed.

## ⚠️ Critical: Netgen Mesh Quality Options

mesh quality는 **fineness** 파라미터로만 제어. custom optimization params 비활성화, SetOptimize만 활성화:

```python
params.SetFineness(fineness)          # 2=mod / 3=fine / 4=vfine
# Custom params disabled (use fineness only):
# params.SetGrowthRate(1.3)
# params.SetNbSurfOptSteps(3)
# params.SetNbVolOptSteps(3)
params.SetOptimize(1)                  # 3D tetrahedra optimization (ENABLED)
# params.SetSecondOrder(0)
```

> salome-tip_refine-snappy 스킬과 동일한 설정. `compute_mesh.py`에 이미 적용됨.

---

## Batch Mode

```bash
/home/bosung/opt/salome/salome -t -b <script.py> args:<directory>:<filename>
```

**Always use `-t -b`** (terminal + batch) - no GUI, no server mode.

---

## Workflow Overview

```
STEP File + optional tip_points CSV
    │
    ▼
calculate_mesh_params.py   (Stage 1)
    ├─ STEP import + bbox
    ├─ Far-field box + tool solid
    ├─ Refine box size calculation
    ├─ Auto-discover {basename}_tip_points.csv
    ├─ Wake lines generated (after boolean cut)
    ├─ Boolean Cut/Partition
    ├─ Face classification (far vs model)
    ├─ Calculate mesh params
    ├─ Save {basename}_mesh_args.json
    └─ Save {basename}_geom.hdf
    │
    ▼  (user reviews & confirms)
    │
compute_mesh.py            (Stage 2)
    ├─ Rebuild geometry fresh from STEP
    ├─ refineBox (shape only)
    ├─ Create wake lines (if tips found)
    ├─ **Wake line domain clipping**: `geompy.MakeCut(wake_line, domain)` 으로 domain 밖으로 뚫고 나가는 부분 clip
    ├─ **min_size auto-correction**: STEP에서 가장 작은 face bbox diagonal을 계산. `min_size > smallest_face_diag` 면 `args['min_size'] = smallest_face_diag`로 조정 (Netgen이 face meshing 못 하는 것 방지)
    ├─ Netgen mesh: SetUseSurfaceCurvature(1)
    ├─ **ViscousLayers(h1=0.0001, layers=10, growth=1.2, far_faces, NODE_OFFSET)** — BOUNDARY LAYERS
    ├─ Mesh compute (no timeout)
    ├─ **exportToFoam: generates complete case structure**
    │   ├─ constant/polyMesh/  (points, faces, owner, neighbour, boundary, cellZones)
    │   ├─ 0/                  (p, U)
    │   ├─ system/             (controlDict, fvSchemes, fvSolution)
    │   └─ case.foam marker
    └─ Save mesh HDF
```

---

## Mesh Sizing Logic (BL-based)

**BL 기반 sizing: 경계층 두께 T에서 유도.**

### 계산 단계

```
Step 1: max_size   = xl / 5           (background mesh max cell size)
Step 2: surf_size  = 4 × T            (surface cell size = 4 × BL thickness)
Step 3: min_size   = 2 × T            (minimum cell size)
Step 4: refine_size = max_size / 4    (refine box local size)
Step 5: tip_wake_refine_size = surf_size × 2  (tip wake line local size)
```

### 경계층 (Boundary Layer)

경계층 두께 **계산 후 sizing에 직접 사용**.

```
h1 = 0.0001  (first cell height, m)
growth = 1.2   (growth rate)
layers = 10    (boundary layer count)

T = h1 × (growth^layers - 1) / (growth - 1)  (total BL thickness)
```

- `T`는 **sizing에 직접 사용** — `surf_size = 4 × T`, `min_size = 2 × T`
- `h1`, `growth`, `layers`는 JSON에서 직접 수정 가능

---

## Step 1: Calculate Parameters

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>
```

**Auto-Discovery:** If `{basename}_tip_points.csv` exists in the same directory as the STEP file, it is automatically loaded. CSV format: `x,y,z` header + data rows. If no CSV found, workflow continues in refine-box-only mode.

**Outputs:**
- `{filename}_geom.hdf` - Geometry study
- `{filename}_mesh_args.json` - Mesh parameters (includes tip fields if CSV found)

---

## Step 2: Compute Mesh

```bash
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<basename>_mesh_args.json
```

---

## Script Differences from salome-tip_refine-snappy

| Aspect | salome-tip_refine-snappy | salome-tip_refine |
|--------|--|------|
| Viscous layers | Disabled (snappyHexMesh handles) | **Enabled in SALOME** via `ViscousLayers()` |
| snappyHexMesh case setup | Yes (template + snappyHexMeshDict) | **Removed** |
| decomposePar / mpirun | Yes (parallel snappyHexMesh) | **Removed** |
| reconstructParMesh | Yes | **Removed** |
| checkMesh | ✅ 자동 실행 (exportToFoam 완료 후) |
| OpenFOAM case output | polyMesh + triSurface + snappyDict | **polyMesh + 0/p + 0/U + system/ (checkMesh + solver ready)** |
| Templates needed | Yes | **No — exportToFoam 생성** |

---

## Important Notes

1. **SALOME path:** `/home/bosung/opt/salome/salome`
2. **Always use `-t -b`** (terminal + batch mode)
3. **Viscous layers** are fully configured inside `compute_mesh.py` via `netgen.ViscousLayers()`
4. **No snappyHexMesh dependency** - boundary layers, meshing, and export all handled in SALOME
5. **Tip-wake refinement** works via SALOME line geometry with local cell size
6. Wake lines are **clipped to domain** using `geompy.MakeCut(wake_line, domain)` before meshing
7. **No parallel meshing** - single-process Netgen mesh computation
7. **exportToFoam**이 complete OpenFOAM case 구조 (polyMesh + 0/p + 0/U + system/ + case.foam) 자동 생성
8. **fvSchemes/fvSolution**은 simpleFoam 호환 default 설정 포함

---

## Workflow Rules

### Golden Rule - Edit JSON directly, not scripts

Show the parameter table, then allow the user to directly edit `{filename}_mesh_args.json`. After user edits, re-display ALL calculated parameters. Do NOT re-run `calculate_mesh_params.py` for parameter changes.

### Workflow Steps

1. `calculate_mesh_params.py` 실행 → 파라미터 표 표시 → 승인 받음
2. 승인 후 수정 요청 시 → **수정할 파라미터만 JSON에서 직접 수정**
3. 관련 유도 파라미터 재계산 **절대 금지**
4. 재계산 필요하다면 → **사용자에게 명시적으로告知**
5. 실행 전 절대 JSON을 수정하거나 실행하지 않음

---

## Monitoring Rules

**compute_mesh.py 실행 후 - 사용자가 모니터링 요청 전까지 절대 확인하지 않음.**

1. `compute_mesh.py` 실행 → 즉시 "실행 중" 보고 + "완료되면 알려드립니다" 회신
2. **사용자가 모니터링을 요청하기 전까지** 로그 확인, 상태 확인 절대 하지 않음
3. 사용자가 모니터링 요청 시: `compute_mesh.py` 결과 확인
4. 완료 시: `{basename}-case/` 전체 구조 확인 (polyMesh + 0/ + system/) + checkMesh 결과

---

## Final Script (Confirmed 2026-07-24)

```bash
# Stage 1: Parameters
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>

# Stage 2: Mesh + export complete OpenFOAM case + auto checkMesh
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

### unified sizing (with salome-tip_refine-snappy)
- **h1=0.0001, layers=10, growth=1.2**
- **T = h1 × (growth^layers - 1) / (growth - 1)** (BL total thickness)
- **surf_size = 4 × T** (surface cell size)
- **min_size = 2 × T** (minimum cell size)
- **tip_wake_refine_size = surf_size × 2**
- **Mesh Quality**: fineness only (SetFineness, 2=mod) + SetOptimize(1) (enabled)
- **wake lines**: after boolean cut
- **mesh compute**: no timeout
- **ViscousLayers**: enabled (SALOME handles BL)
- **auto checkMesh**: yes

---

## File Structure

- `skills/salome-tip_refine/` - **This skill** (confirmed 2026-07-24)
- `skills/salome-tip_refine/scripts/` - `calculate_mesh_params.py`, `compute_mesh.py`
- `skills/salome-tip_refine/SKILL.md` - This file
- `skills/salome-tip_refine-snappy/` - Original (NOT MODIFIED, reference only)
- `skills/salome-snappy/` - **NOT MODIFIED**

## Backup

- `skills/backups/2026-07-25/salome-tip_refine/` - Final confirmed version (2026-07-25)
