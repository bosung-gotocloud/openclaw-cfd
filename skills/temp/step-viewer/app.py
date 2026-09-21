#!/usr/bin/env python3
"""STEP Viewer - Web-based STEP file 3D viewer and analyzer."""

import sys
from flask import Flask, request, jsonify, render_template
from backend.step_viewer_backend import StepViewerBackend

app = Flask(__name__)
viewer = None


def init_viewer():
    """Initialize the STEP viewer backend."""
    global viewer
    viewer = StepViewerBackend()


@app.route("/")
def index():
    """Render the STEP viewer page."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Upload STEP file and compute mesh data."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    file_bytes = file.read()
    filename = file.filename

    try:
        data = viewer.process_file(file_bytes, filename)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/slice", methods=["POST"])
def slice_compute():
    """Compute slice area at given position and axis."""
    body = request.get_json()
    if not body:
        return jsonify({"error": "No JSON body"}), 400

    axis = body.get("axis", "z")
    position = body.get("position", 0.0)

    try:
        area, vertices = viewer.compute_slice(axis, position)
        return jsonify({"area": area, "vertices": vertices})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/projected")
def projected_areas():
    """Compute projected areas on XY, YZ, ZX planes."""
    try:
        areas = viewer.compute_projected_areas()
        return jsonify(areas)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main():
    """Main entry point."""
    init_viewer()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5100
    print(f"STEP Viewer running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
