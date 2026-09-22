#!/usr/bin/env python3
"""
STEP Viewer — 로컬 웹서버에서 STEP 파일을 3D 뷰어 + 분석 도구로 표시.

사용법:
    python step_viewer.py model.step          # STEP 파일 직접 지정
    python step_viewer.py                     # 드래그 앤 드롭으로 파일 선택

포트: 5100~5110 중 사용 가능한 포트
라이브러리: pythonocc-core, trimesh, numpy
"""

import os
import sys
import json
import struct
import threading
import tempfile
import http.server
import socketserver
import urllib.parse
import gzip
import contextlib
from pathlib import Path
from http import HTTPStatus
from io import BytesIO

import numpy as np

# STEP 파일 읽기 — pythonocc-core
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import topods
from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.Message import Message_ProgressRange
from OCC.Core.Standard import Standard_Transient

# mesh 처리 — trimesh
import trimesh


PORT_START = 5100
PORT_MAX = 5110
HTML_DIR = Path(__file__).parent / "templates"

# ─── STEP 파일 처리 ───────────────────────────────────────────

def read_step(filepath: str):
    """STEP 파일을 읽고 트라이앵글 메쉬 데이터 추출."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP 파일 읽기 실패")

    reader.TransferRoot()
    nbr = reader NbShapes()
    if nbr == 0:
        raise RuntimeError("STEP 파일에shapes가 없음")

    # 모든 솔리드/페이스에서 메쉬 추출
    all_verts = []
    all_tris = []

    for i in range(1, nbr + 1):
        shape = reader Shape(i)
        if shape.IsNull():
            continue

        # 메쉬 생성
        mesh = BRepMesh_IncrementalMesh(shape, 0.1)
        mesh.Run()

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = topodsFace(explorer.Current())
            tri_mesh = extract_face_mesh(face)
            if tri_mesh is not None:
                all_verts.extend(tri_mesh["vertices"])
                all_tris.extend(tri_mesh["triangles"])
            explorer.Next()

    if len(all_verts) == 0:
        raise RuntimeError("메쉬 데이터 추출 실패 — STEP 파일이 비어있거나 지원 안되는 형식일 수 있음")

    # numpy 배열로 변환
    verts = np.array(all_verts, dtype=np.float64)
    tris = np.array(all_trris, dtype=np.int64)

    # 바운딩 박스 & center
    x_min, y_min, z_min, x_max, y_max, z_max = get_bounds(verts)
    center = np.array([(x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2])

    return {
        "vertices": verts.tolist(),
        "triangles": tris.tolist(),
        "bounds": [x_min, y_min, z_min, x_max, y_max, z_max],
        "dimensions": [x_max - x_min, y_max - y_min, z_max - z_min],
        "center": center.tolist(),
        "num_verts": len(verts),
        "num_tris": len(tris),
    }


def extract_face_mesh(face):
    """특정 면에서 트라이앵글 메쉬 추출."""
    triang = BRep_ToolTriangulation(face)
    if triang.IsNull():
        return None

    loc = TopLoc_Location()
    triang_array = triang Values(loc)
    if triang_array is None:
        return None

    nodes = triang_array.Nodes()
    faces = triang_array.TriangleArray()

    verts = []
    tris = []

    for i in range(1, faces.Length() + 1):
        tri = faces.Value(i)
        for j in range(1, 4):
            pnt = nodes.Value(tri(j).Value()).Coord()
            verts.append([pnt[0], pnt[1], pnt[2]])

    for i in range(1, faces.Length() + 1):
        tri = faces.Value(i)
        idx1 = tri(1).Value() - 1
        idx2 = tri(2).Value() - 1
        idx3 = tri(3).Value() - 1
        tris.append([idx1, idx2, idx3])

    return {"vertices": verts, "triangles": tris}


def get_bounds(verts):
    """배열에서 바운딩 박스 계산."""
    x_min = float(np.min(verts[:, 0]))
    y_min = float(np.min(verts[:, 1]))
    z_min = float(np.min(verts[:, 2]))
    x_max = float(np.max(verts[:, 0]))
    y_max = float(np.max(verts[:, 1]))
    z_max = float(np.max(verts[:, 2]))
    return x_min, y_min, z_min, x_max, y_max, z_max


def compute_centroid(verts):
    """무게 중심 계산 (밀도 일가정)."""
    return float(np.mean(verts[:, 0])), float(np.mean(verts[:, 1])), float(np.mean(verts[:, 2]))


def compute_slice(verts, tris, axis: str, position: float):
    """
    주어진 축과 위치에서 단면 계산.
    axis: 'x', 'y', or 'z'
    position: 슬라이스 위치
    면적과 단면 삼각형 정보 반환.
    """
    if axis == "x":
        idx_coord = 0
        axes_2d = [1, 2]
    elif axis == "y":
        idx_coord = 1
        axes_2d = [0, 2]
    elif axis == "z":
        idx_coord = 2
        axes_2d = [0, 1]
    else:
        raise ValueError(f"axis must be 'x', 'y', or 'z', got '{axis}'")

    pos_val = position
    # 삼각형이 슬라이스 평면을 지나는 것만 필터
    cross_tris = []
    for tri in tris:
        p0 = verts[tri[0], idx_coord]
        p1 = verts[tri[1], idx_coord]
        p2 = verts[tri[2], idx_coord]

        if (p0 < pos_val and p1 > pos_val) or (p1 < pos_val and p0 > pos_val):
            t0 = (pos_val - p0) / (p1 - p0)
            cross_tris.append((tri[0], tri[1], t0))
        if (p1 < pos_val and p2 > pos_val) or (p2 < pos_val and p1 > pos_val):
            t1 = (pos_val - p1) / (p2 - p1)
            cross_tris.append((tri[1], tri[2], t1))
        if (p2 < pos_val and p0 > pos_val) or (p0 < pos_val and p2 > pos_val):
            t2 = (pos_val - p2) / (p0 - p2)
            cross_tris.append((tri[2], tri[0], t2))

    # 교점 좌표 계산
    pts_2d = []
    for _, _, _ in cross_tris:
        pts_2d.append(cross_tris)

    # 중복 제거
    unique_pts = {}
    for v1, v2, t in cross_tris:
        p1 = verts[v1]
        p2 = verts[v2]
        pt = p1 + (p2 - p1) * t
        key = tuple(round(v, 6) for v in pt)
        if key not in unique_pts:
            unique_pts[key] = [pt[axes_2d[0]], pt[axes_2d[1]]]

    # 면적 계산 (2D 다각형)
    if len(unique_pts) >= 3:
        poly = list(unique_pts.values())
        area = polygon_area_2d(poly)
    else:
        area = 0.0

    return {
        "area": area,
        "vertices": list(unique_pts.values()),
    }


def polygon_area_2d(polygon):
    """2D 다각형 면적 (shoelace formula)."""
    n = len(polygon)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i][0] * polygon[j][1]
        area -= polygon[j][0] * polygon[i][1]
    return abs(area) / 2.0


def compute_projected_areas(verts, tris):
    """
    XY, YZ, ZX 평면에 대한 투영면적 계산.
    각 삼각형의 투영면적을 합산.
    """
    areas = {}

    for plane, axes in [("xy", [0, 1]), ("yz", [1, 2]), ("zx", [0, 2])]:
        total = 0.0
        for tri in tris:
            v0 = verts[tri[0], axes]
            v1 = verts[tri[1], axes]
            v2 = verts[tri[2], axes]
            area = triangle_area_2d(v0, v1, v2)
            total += area
        areas[f"projected_{plane}"] = total

    return areas


def triangle_area_2d(v0, v1, v2):
    """2D 삼각형 면적."""
    return abs((v0[0] * (v1[1] - v2[1]) + v1[0] * (v2[1] - v0[1]) + v2[0] * (v0[1] - v1[1])) / 2.0)


# ─── Web Server ─────────────────────────────────────────────

def find_free_port():
    """사용 가능한 포트 찾기."""
    for port in range(PORT_START, PORT_MAX + 1):
        with socketserver.TCPServer(("0.0.0.0", port), RequestHandler) as s:
            return port
    raise RuntimeError("사용 가능한 포트가 없음")


def start_server(port: int, file_data: dict = None):
    """로컬 HTTP 서버 시작."""
    server = socketserver.TCPServer(("0.0.0.0", port), RequestHandler)
    server.serve_forever()


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """STEP 파일을 처리하는 간단한 HTTP 핸들러."""

    # class-level data storage
    file_data = None
    filename = ""
    file_path = ""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """GET 요청 처리."""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            html_path = HTML_DIR / "index.html"
            if html_path.exists():
                with open(html_path, "r", encoding="utf-8") as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_error(404, "index.html not found")
        elif parsed.path == "/status":
            if self.file_data is None:
                data = {"status": "waiting"}
            else:
                data = {
                    "status": "ready",
                    "filename": self.filename,
                    "dimensions": self.file_data.get("dimensions"),
                    "center": self.file_data.get("center"),
                    "bounds": self.file_data.get("bounds"),
                    "num_verts": self.file_data.get("num_verts"),
                    "num_tris": self.file_data.get("num_tris"),
                }
            self.send_json(200, data)
        else:
            self.send_error(404)

    def do_POST(self):
        """POST 요청 처리."""
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if parsed.path == "/load":
            try:
                req = json.loads(body)
                filepath = req.get("file_path")
                if not filepath:
                    self.send_json(400, {"error": "file_path required"})
                    return

                if not os.path.exists(filepath):
                    self.send_json(400, {"error": f"File not found: {filepath}"})
                    return

                data = read_step(filepath)
                self.file_data = data
                self.filename = Path(filepath).name
                self.send_json(200, data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif parsed.path == "/upload":
            # multipart upload
            boundary = self.headers.get("Content-Type", "").split("boundary=")[-1]
            parts = parse_multipart(body, boundary)

            if "file" not in parts:
                self.send_json(400, {"error": "No file in upload"})
                return

            filename = parts["file_name"]
            file_bytes = parts["file_data"]

            # temp file 저장
            tmp = tempfile.NamedTemporaryFile(suffix=".step", delete=False)
            tmp.write(file_bytes)
            tmp.close()

            try:
                data = read_step(tmp.name)
                self.file_data = data
                self.filename = filename
                self.file_path = tmp.name
                self.send_json(200, data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
                os.unlink(tmp.name)

        elif parsed.path == "/slice":
            try:
                req = json.loads(body)
                axis = req.get("axis", "z")
                position = float(req.get("position", 0))
                if self.file_data is None:
                    self.send_json(400, {"error": "No file loaded"})
                    return

                verts = np.array(self.file_data["vertices"])
                tris = np.array(self.file_data["triangles"])
                result = compute_slice(verts, tris, axis, position)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif parsed.path == "/projected":
            if self.file_data is None:
                self.send_json(400, {"error": "No file loaded"})
                return
            try:
                verts = np.array(self.file_data["vertices"])
                tris = np.array(self.file_data["triangles"])
                areas = compute_projected_areas(verts, tris)
                self.send_json(200, areas)
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        else:
            self.send_error(404)

    def send_json(self, code, data):
        """JSON 응답."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def parse_multipart(body, boundary):
    """multipart/form-data 파싱."""
    parts = {}
    bnd = boundary.encode("utf-8")

    # split by boundary
    sep = b"--" + bnd
    splits = body.split(sep)

    for part in splits[1:]:  # skip first empty
        part = part.rstrip(b"\r\n")
        if part.startswith(b"--"):
            break

        headers_end = part.find(b"\r\n\r\n")
        if headers_end == -1:
            continue

        headers = part[:headers_end].decode("utf-8")
        data = part[headers_end + 4:]

        # extract filename
        fname = ""
        for line in headers.split("\n"):
            if "filename=" in line:
                fname = line.split("filename=")[1].strip('"')

        # extract field name
        field = ""
        for line in headers.split("\n"):
            if "name=" in line:
                field = line.split("name=")[1].strip('"')
                break

        if field and data:
            parts[field] = data
            parts[f"{field}_name"] = fname

    return parts


# ─── Main ─────────────────────────────────────────────────────



def main():
    port = find_free_port()
    print(f"\n🦋 STEP Viewer")
    print(f"   URL: http://localhost:{port}")
    print(f"   Python: {sys.version.split()[0]}")
    print()

    # STEP 파일이 인자로 주어진 경우
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if os.path.exists(filepath):
            print(f"STEP file: {filepath}")
            data = read_step(filepath)
            print(f"  vertices: {data['num_verts']}")
            print(f"  triangles: {data['num_tris']}")
            print(f"  bounds: X[{data['bounds'][0]:.4f}, {data['bounds'][3]:.4f}]  "
                  f"Y[{data['bounds'][1]:.4f}, {data['bounds'][4]:.4f}]  "
                  f"Z[{data['bounds'][2]:.4f}, {data['bounds'][5]:.4f}]")
            print(f"  center: {data['center']}")
            print(f"  dimensions: {data['dimensions']}")
            centroid = compute_centroid(data["vertices"])
            print(f"  centroid: {centroid}")
        else:
            print(f"File not found: {filepath}")
            sys.exit(1)

    # 웹 서버 시작
    print("Starting web server...")
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()
    print(f"\n✓ Open http://localhost:{port} in your browser")
    print("  Drop STEP file on the page, or type file path below\n")

    # 터미널 대기
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
