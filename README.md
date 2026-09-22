# CFD Skills

CFD (OpenFOAM) 시뮬레이션 전처리/해석/후처리 및 기하 처리 관련 스킬 모음.
매 스킬은 `SKILL.md` 파일과 `scripts/`, `assets/` 등의 보조 리소스를 포함한다.

## 완성된 스킬

| 스킬 | 설명 | 마지막 업데이트 |
|------|------|----------------|
| **apc-prop-geom** | APC 프로펠러 성능 데이터 기반 3D 기하 생성 (CLARK-Y 단면) | 2026-07-13 |
| **apc-prop-perf** | APC 프로펠러 공식 성능 데이터 파싱, SQLite 저장, 추력·토크·효율 보간 계산 | 2026-07-13 |
| **hisa** | HiSA 고속 공기역학 솔버 (compressible kOmegaSST) | 2026-07-22 |
| **paraview** | ParaView 기반 OpenFOAM 후처리 (시각화, 슬라이스, 등가선, 분할 case) | 2026-07-22 |
| **post** | OpenFOAM 후처리 (잔여량, 힘, 계수) | 2026-07-22 |
| **salome** | SALOME 기반 기하 처리 및 볼륨 메쉬 생성 (STEP/IGES → CFD 도메인) | 2026-07-22 |
| **salome-elliptic-tip-shock-refine** | 타원형 원거리 경계 + 충격파/팁 와류 라인 정밀 SALOME Netgen 메쉬 | 2026-09-21 |
| **salome-elliptic-tip-shock-refine-snappy** | 타원형 원거리 + snappyHexMesh addLayers + 충격파/팁 정밀 파이프라인 | 2026-09-21 |
| **salome-snappy** | SALOME 볼륨 메쉬 → snappyHexMesh (addLayers) 파이프라인 | 2026-09-22 |
| **salome-tip-refine** | SALOME Netgen + 팁-와류 라인 정밀 + 점성층 메쉬 | 2026-09-16 |
| **salome-tip-refine-snappy** | SALOME Netgen + snappyHexMesh + 팁-와류 라인 정밀 | 2026-09-22 |
| **salome-tip-shock-refine** | SALOME Netgen + 충격파 포인트 정밀 + 팁-와류 정밀 (snappyHexMesh 없음) | 2026-09-16 |
| **salome-tip-shock-refine-snappy** | SALOME Netgen + 충격파 정밀 + snappyHexMesh | 2026-09-16 |
| **shock-refine** | SI 기반 충격파 감지 + OpenFOAM refineMesh 적응적 세분화 | 2026-09-05 |
| **simpleFoam** | OpenFOAM 정상 상태 (simpleFoam) kΩ-SST 해석 | 2026-09-19 |
| **simpleFoam-adm** | simpleFoam Actuator Disk Model — 프로펠러 추력 시뮬레이션 | 2026-09-09 |
| **snappyMesh** | STL 기반 snappyHexMesh 메쉬 생성 (blockMesh, snappyHexMeshDict) | 2026-09-16 |
| **snappyMesh-elliptic-tip-refine** | 타원형 원거리 + refine ellipsoid + 팁-와류 라인 정밀 (SALOME 방식) | 2026-09-21 |
| **snappyMesh-tip-refine** | STL + 팁-와류 라인 정밀 snappyHexMesh 파이프라인 | 2026-09-21 |
| **step-tip-detect** | STEP CAD 기하 tip 감지 (Graph Sharp Corner + DBSCAN + 볼록성 검사) | 2026-08-14 |
| **step-utils** | STEP 기하 처리 (분석, 스케일, 이동, 회전, 렌더링) | 2026-08-13 |
| **step-viewer** | STEP 3D 뷰어 | 2026-07-15 |
| **stl-tip-detect** | STL 기반 tip 감지 (직교 투영 + 엣지 그래프 + VLM) | 2026-08-14 |
| **stl-utils** | STL 기하 처리 (분석, 스케일, 이동, 회전, 렌더링) | 2026-08-13 |
| **stl-viewer** | Dash+Plotly 인터랙티브 STL 뷰어 (스라이스, tip 감지, BBox, CSV 내보내기) | 2026-08-14 |
| **vlm-step-tip-detect** | VLM 기반 STEP tip 감지 (직교 투영 → 픽셀 감지 → CAD 좌표 매핑) | 2026-09-08 |
| **vlm-stl-tip-detect** | VLM 기반 STL tip 감지 (직교 투영 → 픽셀 감지 → CAD 좌표 매핑) | 2026-09-08 |

## 특수 디렉토리

| 디렉토리 | 용도 |
|----------|------|
| `x.backup/` | 날짜별 백업 (요청 시 생성됨) |
| `y.under-develop/` | 개발 중이며 완성되지 않은 스킬 |
| `z.trash/` | 삭제 대기 중 (잘 만들었거나 더 이상 필요 없는 스킬) |
