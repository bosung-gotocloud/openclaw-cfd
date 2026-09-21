#!/usr/bin/env python3
"""APC Propeller STEP/CSV Viewer — Simple 3D inspector.

- Drag-and-drop file upload (STEP/CSV)
- trimesh-based mesh extraction via cadquery tessellation
- go.Mesh3d for rendering (single solid, single color)
- No sliders, no slice — pure 3D view
"""

import os
import base64
import numpy as np

try:
    import cadquery as cq
    HAS_OCC = True
except ImportError:
    HAS_OCC = False

try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False

import plotly.graph_objects as go
from dash import Dash, dcc, html, callback, Output, Input, no_update, callback_context, State

# ─── Base directory ──

if '__file__' in dir():
    BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geom")
else:
    BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geom")

# ─── Load helpers ──

def load_step(filepath):
    """Load STEP, auto-detect mm→m, return mesh + metadata."""
    if not HAS_OCC or not HAS_TRIMESH:
        return None
    try:
        shape = cq.importers.importStep(filepath)
        if shape is None or len(shape.vals()) == 0:
            return None
        val = shape.vals()[0]
        # High-res tessellation
        verts, faces = val.tessellate(1e-4)
        verts_arr = np.array([[v.x, v.y, v.z] for v in verts])
        if len(verts_arr) == 0:
            return None
        raw_range = verts_arr.max(axis=0) - verts_arr.min(axis=0)
        diag = np.linalg.norm(raw_range)
        if diag > 100:
            verts_arr = verts_arr / 1000.0
        mesh = trimesh.Trimesh(vertices=verts_arr, faces=faces, process=False)
        # Double-sided: reverse face winding
        verts2 = mesh.vertices.copy()
        faces2 = mesh.faces.copy()
        faces2[:, 1] = mesh.faces[:, 2]
        faces2[:, 2] = mesh.faces[:, 1]
        offset = len(verts2)
        mesh_double = trimesh.Trimesh(
            vertices=np.vstack([verts2, verts2]),
            faces=np.vstack([faces2, mesh.faces + offset]),
            process=False,
        )
        if mesh_double.is_empty:
            return None
        bounds = mesh_double.bounds
        xmin, ymin, zmin = bounds[0]
        xmax, ymax, zmax = bounds[1]
        if mesh.is_watertight:
            cm = mesh.center_mass
        else:
            v0 = mesh.vertices[mesh.faces[:, 0]]
            v1 = mesh.vertices[mesh.faces[:, 1]]
            v2 = mesh.vertices[mesh.faces[:, 2]]
            fc = (v0 + v1 + v2) / 3.0
            normals = np.cross(v1 - v0, v2 - v0)
            areas = np.linalg.norm(normals, axis=1) / 2.0
            cm = np.sum(fc * areas[:, None], axis=0) / areas.sum()
        return {
            "mesh": mesh_double,
            "total_surface_area": mesh_double.area,
            "xmin": xmin, "xmax": xmax,
            "ymin": ymin, "ymax": ymax,
            "zmin": zmin, "zmax": zmax,
            "cm_x": cm[0], "cm_y": cm[1], "cm_z": cm[2],
            "is_watertight": mesh.is_watertight,
        }
    except Exception as e:
        print(f"ERROR loading STEP: {e}")
        return None


def load_csv_info(filepath):
    """Load CSV (airfoil sections) and return metadata."""
    import pandas as pd
    try:
        df = pd.read_csv(filepath)
        x_col = 'X' if 'X' in df.columns else 'x'
        y_col = 'Y' if 'Y' in df.columns else 'y'
        z_col = 'Z' if 'Z' in df.columns else 'z'
        station_col = 'r_over_R' if 'r_over_R' in df.columns else 'station_idx'
        stations = df[station_col].unique()
        return {
            "filename": os.path.basename(filepath),
            "n_sections": len(stations),
            "x_range": (float(df[x_col].min()), float(df[x_col].max())),
            "y_range": (float(df[y_col].min()), float(df[y_col].max())),
            "z_range": (float(df[z_col].min()), float(df[z_col].max())),
        }
    except Exception:
        return None


def build_layout(xmin, xmax, ymin, ymax, zmin, zmax):
    """Common scene layout — same range for all axes (bbox span)."""
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2
    span_y = ymax - ymin
    s = max(span_y * 0.5, (xmax - xmin) * 0.5, (zmax - zmin) * 0.5) * 1.5
    r = s * 0.05  # axis arrow length = 5% of range
    return go.Layout(
        scene={
            'xaxis': {'title': 'X [m]', 'range': [cx - s, cx + s], 'gridcolor': '#ccc', 'zerolinecolor': '#aaa', 'showbackground': True, 'backgroundcolor': '#f5f5f5'},
            'yaxis': {'title': 'Y [m]', 'range': [cy - s, cy + s], 'gridcolor': '#ccc', 'zerolinecolor': '#aaa', 'showbackground': True, 'backgroundcolor': '#f5f5f5'},
            'zaxis': {'title': 'Z [m]', 'range': [cz - s, cz + s], 'gridcolor': '#ccc', 'zerolinecolor': '#aaa', 'showbackground': True, 'backgroundcolor': '#f5f5f5'},
            'aspectmode': 'cube',
            'camera': {'eye': {'x': 1.5, 'y': 1.5, 'z': 1}},
        },
        paper_bgcolor='#f5f5f5', plot_bgcolor='#fafafa',
        margin={'l': 0, 'r': 0, 'b': 0, 't': 0},

    )


def mesh_trace(mesh, color='rgb(180,180,180)'):
    """Single Mesh3d trace — double-sided rendering."""
    v1 = mesh.vertices
    f1 = mesh.faces
    # Double-sided: reverse face winding
    f2 = f1.copy()
    f2[:, 1] = f1[:, 2]
    f2[:, 2] = f1[:, 1]
    offset = len(v1)
    v_all = np.vstack([v1, v1])
    f_all = np.vstack([f2, f1 + offset])
    return go.Mesh3d(
        x=v_all[:, 0],
        y=v_all[:, 1],
        z=v_all[:, 2],
        i=f_all[:, 0],
        j=f_all[:, 1],
        k=f_all[:, 2],
        color=color,
        flatshading=False,
        opacity=1.0,
        hoverinfo='skip',
        showlegend=False,
    )


def csv_traces(info):
    """CSV airfoil section traces."""
    import pandas as pd
    filepath = os.path.join(BASE_DIR, info['filename'])
    df = pd.read_csv(filepath)
    x_col = 'X' if 'X' in df.columns else 'x'
    y_col = 'Y' if 'Y' in df.columns else 'y'
    z_col = 'Z' if 'Z' in df.columns else 'z'
    station_col = 'r_over_R' if 'r_over_R' in df.columns else 'station_idx'
    stations = sorted(df[station_col].unique())
    traces = []
    for i, r_val in enumerate(stations):
        section = df[df[station_col] == r_val]
        ratio = i / max(1, len(stations) - 1)
        color = f'rgb({int(255*ratio)}, {int(255*(1-abs(ratio-0.5)*2))}, {int(255*(1-ratio))})'
        traces.append(go.Scatter3d(
            x=section[x_col].tolist(),
            y=section[y_col].tolist(),
            z=section[z_col].tolist(),
            mode='lines',
            line={'color': color, 'width': 3},
            showlegend=False,
            hoverinfo='skip',
        ))
    return traces


# ─── App ──

app = Dash(__name__)
_info_store = {}
_current_file = None
_current_type = None

app.layout = html.Div([
    # Left panel
    html.Div([
        dcc.Upload(
            id='file-upload',
            children=html.Div(["📁 Drag & Drop or click to browse"],
                              style={'textAlign': 'center', 'padding': '5px 0', 'fontSize': 12}),
            style={
                'width': '100%', 'height': '50px', 'borderWidth': '2px',
                'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center',
                'backgroundColor': '#fafafa', 'lineHeight': '40px', 'cursor': 'pointer',
                'marginBottom': '10px', 'boxSizing': 'border-box',
            },
            multiple=False,
        ),
        html.P(id='file-name', children="No file loaded",
               style={'fontSize': 14, 'fontWeight': 'bold'}),
        html.Div(id='step-info', children="", style={'fontSize': 12, 'marginTop': 4}),
        html.Div(id='csv-info', children="", style={'fontSize': 12, 'marginTop': 4}),
        html.Div(id='status-msg', children="",
                 style={'textAlign': 'center', 'fontSize': 11, 'marginTop': 8, 'color': '#888'}),
    ], style={
        'width': '25%', 'padding': '10px', 'overflowY': 'scroll',
        'height': '100vh', 'borderRight': '1px solid gray',
    }),

    # Right: 3D view
    html.Div([
        dcc.Graph(id='plot-3d', style={'height': '100%', 'width': '100%'})
    ], style={
        'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center',
        'flex': 1, 'overflow': 'hidden',
    }),
], style={'display': 'flex'})


# ─── Callback ──

@app.callback(
    Output('plot-3d', 'figure'),
    Output('file-name', 'children'),
    Output('step-info', 'children'),
    Output('csv-info', 'children'),
    Output('status-msg', 'children'),
    Input('file-upload', 'contents'),
    State('file-upload', 'filename'),
)
def update_plot(contents, filename):
    global _info_store, _current_file, _current_type

    if contents is None:
        return (go.Figure(), "No file", "", "", "")

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    if not filename:
        return (go.Figure(), "❌ No filename", "", "", "")

    ext = os.path.splitext(filename)[1].lower()
    # .stp and .step are both STEP format
    is_step = ext in ('.step', '.stp')
    tmp_path = os.path.join('/tmp', filename)
    if is_step:
        # Normalize extension to .step for internal handling
        tmp_path = os.path.join('/tmp', os.path.splitext(filename)[0] + '.step')
    with open(tmp_path, 'wb') as f:
        f.write(decoded)

    # ── STEP ──
    if is_step:
        info = load_step(tmp_path)
        if info is None:
            return (go.Figure(), "❌ STEP load failed", "", "", "Error loading STEP")
        _info_store[tmp_path] = info
        _current_file = tmp_path
        _current_type = 'step'
        layout = build_layout(info['xmin'], info['xmax'], info['ymin'], info['ymax'], info['zmin'], info['zmax'])
        traces = [mesh_trace(info['mesh'])]
        # Axes arrows at origin (0,0,0)
        axis_len = max(info['xmax'] - info['xmin'], info['ymax'] - info['ymin'], info['zmax'] - info['zmin']) * 0.05
        traces.extend([
            go.Scatter3d(x=[0, axis_len], y=[0, 0], z=[0, 0], mode='lines',
                         line={'color': 'red', 'width': 4}, showlegend=False, name='X'),
            go.Scatter3d(x=[0, 0], y=[0, axis_len], z=[0, 0], mode='lines',
                         line={'color': 'green', 'width': 4}, showlegend=False, name='Y'),
            go.Scatter3d(x=[0, 0], y=[0, 0], z=[0, axis_len], mode='lines',
                         line={'color': 'blue', 'width': 4}, showlegend=False, name='Z'),
        ])
        info_text = (f"Surface Area: {info['total_surface_area']:.6f} m²\n"
                     f"BBox: {info['xmax']-info['xmin']:.4f} × "
                     f"{info['ymax']-info['ymin']:.4f} × "
                     f"{info['zmax']-info['zmin']:.4f} m\n"
                     f"CG: ({info['cm_x']:.4f}, {info['cm_y']:.4f}, {info['cm_z']:.4f})\n"
                     f"Watertight: {info['is_watertight']}")
        return (go.Figure(data=traces, layout=layout),
                f"📄 {filename}", info_text, "", f"Loaded {filename}")

    # ── CSV ──
    elif ext == '.csv':
        info = load_csv_info(tmp_path)
        if info is None:
            return (go.Figure(), "❌ CSV load failed", "", "", "Error loading CSV")
        _info_store[tmp_path] = info
        _current_file = tmp_path
        _current_type = 'csv'
        layout = build_layout(info['x_range'][0], info['x_range'][1],
                              info['y_range'][0], info['y_range'][1],
                              info['z_range'][0], info['z_range'][1])
        traces = csv_traces(info)
        info_text = (f"Sections: {info['n_sections']}\n"
                     f"X: {info['x_range'][0]:.6f} ~ {info['x_range'][1]:.6f}\n"
                     f"Y: {info['y_range'][0]:.6f} ~ {info['y_range'][1]:.6f}\n"
                     f"Z: {info['z_range'][0]:.6f} ~ {info['z_range'][1]:.6f}")
        return (go.Figure(data=traces, layout=layout),
                f"📄 {filename}", "", info_text, f"Loaded {filename}")
    else:
        return (go.Figure(), "❌ Unsupported", "", "", f"Unsupported: {ext}")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8054, debug=False)
