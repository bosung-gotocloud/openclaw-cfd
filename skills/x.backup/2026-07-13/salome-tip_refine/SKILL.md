---
name: salome-tip_refine
description: SALOME-based mesh generation with tip-wake line refinement and viscous layers. STEP import → Netgen mesh → OpenFOAM case. No snappyHexMesh.
---

# salome-tip_refine Skill

SALOME-based two-step batch mesh generation for OpenFOAM. Adds **tip-wake line refinement** and **viscous boundary layers** in SALOME (Netgen) — **no snappyHexMesh dependency**.

**Based on:** `salome-tip_refine-snappy` skill (snappy parts removed, viscous layers added)
**Location:** `~/.openclaw/workspace/skills/salome-tip_refine/`
**SALOME path:** `/home/bosung/opt/salome/salome`

---

## ⚠️ Critical: Surface Curvature Must Be Enabled

`SetUseSurfaceCurvature(1)` **MUST be enabled** for stable STEP mesh computation.

## ⚠️ Critical: Viscous Layers in SALOME

Viscous layers are configured **inside** `compute_mesh.py` via `netgen.ViscousLayers(T, layers, growth, far_faces, 1, smeshBuilder.FACE_OFFSET)`.
No separate snappyHexMesh layer config needed.

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
    ├─ Wake lines generated (before boolean cut, after surf_size)
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
    ├─ Netgen mesh: SetUseSurfaceCurvature(1)
    ├─ **ViscousLayers(T, layers, growth, far_faces)** — BOUNDARY LAYERS
    ├─ Mesh compute (no timeout)
    ├─ Export OpenFOAM polyMesh
    ├─ Create case.foam marker
    └─ Save mesh HDF
```

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

## Script Differences from salome-tip_refine-snappy

| Aspect | salome-tip_refine-snappy | salome-tip_refine |
|--------|--------------------------|-------------------|
| Viscous layers | Disabled (snappyHexMesh handles) | **Enabled in SALOME** via `ViscousLayers()` |
| snappyHexMesh case setup | Yes (template + snappyHexMeshDict) | **Removed** |
| decomposePar / mpirun | Yes (parallel snappyHexMesh) | **Removed** |
| reconstructParMesh | Yes | **Removed** |
| checkMesh auto-run | Yes | **Removed** |
| STL export | Yes (for snappyHexMesh layers) | **Removed** |
| OpenFOAM case output | polyMesh + triSurface + snappyDict | **polyMesh only** |
| case.foam marker | Yes | **Added** |

---

## Output Files

- `{filename}_mesh_setup.hdf` - Mesh setup (for manual tuning in SALOME GUI)
- `{filename}_mesh.hdf` - Computed mesh
- `{filename}-case/case.foam` - ParaView case marker
- `{filename}-case/constant/polyMesh/` - OpenFOAM volume mesh:
  - `points`, `faces`, `owner`, `neighbour`, `boundary`, `cellZones`

---

## Important Notes

1. **SALOME path:** `/home/bosung/opt/salome/salome`
2. **Always use `-t -b`** (terminal + batch mode)
3. **Viscous layers** are fully configured inside `compute_mesh.py` via `netgen.ViscousLayers()`
4. **No snappyHexMesh dependency** — boundary layers, meshing, and export all handled in SALOME
5. **Tip-wake refinement** works via SALOME line geometry with local cell size
6. **No parallel meshing** — single-process Netgen mesh computation
7. **No checkMesh** — user must run manually if needed

---

## Final Script (Confirmed)

```bash
# Stage 1: Parameters
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/calculate_mesh_params.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/calculate_mesh_params.py args:<directory>:<step_file.stp>

# Stage 2: Mesh (with viscous layers, no snappyHexMesh)
cp ~/.openclaw/workspace/skills/salome-tip_refine/scripts/compute_mesh.py <directory>/
/home/bosung/opt/salome/salome -t -b <directory>/compute_mesh.py args:<directory>:<filename>_mesh_args.json
```

---

## Monitoring Rules

**compute_mesh.py 실행 후 — 사용자가 모니터링 요청 전까지 절대 확인하지 않음.**

1. `compute_mesh.py` 실행 → 즉시 "실행 중" 보고 + "완료되면 알려드립니다" 회신
2. **사용자가 모니터링을 요청하기 전까지** 로그 확인, 상태 확인 절대 하지 않음
3. 사용자가 모니터링 요청 시: `log.snappyHexMesh` 대신 `compute_mesh.py` 결과 확인
4. 완료 시: `{basename}-case/constant/polyMesh/` 파일 존재 확인

---

## File Structure

- `skills/salome-tip_refine/` - **This skill** (new, based on tip_refine-snappy)
- `skills/salome-tip_refine/scripts/` - `calculate_mesh_params.py`, `compute_mesh.py`
- `skills/salome-tip_refine/SKILL.md` - This file
- `skills/salome-tip_refine-snappy/` - Original (NOT MODIFIED, reference only)
- `skills/salome-snappy/` - **NOT MODIFIED**
