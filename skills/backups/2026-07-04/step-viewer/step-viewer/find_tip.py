#!/usr/bin/env python3

import sys
import os
import base64
import numpy as np
import trimesh

from shapely.geometry import Polygon
from shapely.ops import unary_union
from scipy.spatial import cKDTree

import plotly.graph_objects as go

from dash import Dash, dcc, html, callback, Output, Input, no_update, State, callback_context


# ================================================================
# find_tip — tip point detection algorithm
# ================================================================

def find_tip_points(mesh, tol=0.5):
    """
    Multi-direction 2D projection tip detector.
    YZ + XZ projection -> radial peak detection -> clustering -> dedup.
    Returns list of (x, y, z) tip coordinates.
    """
    from sklearn.cluster import DBSCAN
    vertices = mesh.vertices
    faces = mesh.faces

    tip_candidates = []

    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2)]:
        centroids = vertices[faces].mean(axis=1)
        verts_2d = vertices[:, [axis1, axis2]]
        origin_2d = centroids[:, [axis1, axis2]].mean(axis=0)
        radial = np.linalg.norm(verts_2d - origin_2d, axis=1)

        for pct in [30, 50, 70]:
            threshold = np.percentile(radial, pct)
            high_mask = radial > threshold
            if high_mask.sum() == 0:
                continue

            high_coords = verts_2d[high_mask]
            high_indices = np.where(high_mask)[0]
            high_radial = radial[high_mask]

            if len(high_indices) < 10:
                continue

            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale

            clustering = DBSCAN(eps=0.3 / scale.min(), min_samples=5).fit(features)
            labels = clustering.labels_

            for label in set(labels):
                if label == -1:
                    continue
                cluster_mask = labels == label
                cluster_idx_2d = high_indices[cluster_mask]
                cluster_radial = high_radial[cluster_mask]

                peak_local = cluster_radial.argmax()
                peak_idx_3d = cluster_idx_2d[peak_local]
                tip_pos = vertices[peak_idx_3d].copy()
                tip_candidates.append(tip_pos)

    # deduplicate by tol
    tips = []
    for t in tip_candidates:
        duplicated = False
        for q in tips:
            if np.linalg.norm(t - q) < tol:
                duplicated = True
                break
        if not duplicated:
            tips.append(t)

    return tips


# ================================================================
# Projection area (all faces, union)
# ================================================================

def compute_projection_area(mesh):

    normals = {"XY": [0, 0, 1], "XZ": [0, 1, 0], "YZ": [1, 0, 0]}
    areas = {}

    for label, normal in normals.items():

        n = np.array(normal, dtype=float)
        n /= np.linalg.norm(n)

        if abs(n[0]) < 0.9:
            u = np.cross(n, [1, 0, 0])
        else:
            u = np.cross(n, [0, 1, 0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        v /= np.linalg.norm(v)

        visible_faces = mesh.faces
        visible_verts = mesh.vertices[visible_faces]

        polys = []
        for fv in visible_verts:
            fu = fv @ u
            fv_proj = fv @ v
            poly = [(fu[0], fv_proj[0]), (fu[1], fv_proj[1]), (fu[2], fv_proj[2])]
            try:
                poly = Polygon(poly)
                if poly.is_valid and poly.area > 1e-15:
                    polys.append(poly)
            except Exception:
                continue

        if polys:
            merged = unary_union(polys)
            areas[label] = merged.area if hasattr(merged, "area") else 0.0
        else:
            areas[label] = 0.0

    return areas


# ================================================================
# Plane helper
# ================================================================

def make_plane(axis, value):
    origin = [0.0, 0.0, 0.0]
    origin[axis] = value
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    return np.array(origin), np.array(normal)


# ================================================================
# Slice extraction
# ================================================================

def extract_slice(mesh, axis, value):
    if isinstance(axis, str):
        axis_map = {'x': 0, 'y': 1, 'z': 2}
        axis = axis_map[axis]
    origin, normal = make_plane(axis, value)
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return {"paths": [], "polygons": [], "area": 0.0, "contours": [], "xlabel": "", "ylabel": ""}

    polygons = []
    paths = []
    contours = []
    xlabel, ylabel = "", ""

    for discrete in section.discrete:
        pts3d = np.array(discrete)
        if len(pts3d) < 3:
            continue

        if axis == 0:
            px, py = pts3d[:, 1], pts3d[:, 2]
            xlabel, ylabel = "Y", "Z"
        elif axis == 1:
            px, py = pts3d[:, 0], pts3d[:, 2]
            xlabel, ylabel = "X", "Z"
        else:
            px, py = pts3d[:, 0], pts3d[:, 1]
            xlabel, ylabel = "X", "Y"

        pts2d = np.vstack([px, py]).T
        try:
            poly = Polygon(pts2d)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.area <= 1e-12:
                continue
        except Exception:
            continue

        polygons.append(poly)
        paths.append(pts2d)

        center3d = np.mean(pts3d, axis=0)
        if axis == 0:
            center2d = (center3d[1], center3d[2])
        elif axis == 1:
            center2d = (center3d[0], center3d[2])
        else:
            center2d = (center3d[0], center3d[1])

        contours.append({"polygon": poly, "center2d": center2d,
                         "center3d": tuple(center3d), "area": poly.area})

    return {"paths": paths, "polygons": polygons, "area": 0.0,
            "contours": contours, "xlabel": xlabel, "ylabel": ylabel}


# ================================================================
# 2D Figure (closed outline + fill, no labels)
# ================================================================

def build_2d_figure(data, axis, index, value, xmin, xmax, ymin, ymax, zmin, zmax):
    fig = go.Figure()

    for ci, contour in enumerate(data["contours"]):
        poly = contour["polygon"]
        if poly.geom_type == 'MultiPolygon':
            for g in poly.geoms:
                x, y = g.exterior.xy
                fig.add_trace(go.Scatter(x=list(x)+[x[0]], y=list(y)+[y[0]],
                                         mode='lines', fill='toself',
                                         fillcolor='rgba(100,149,237,0.35)',
                                         line=dict(width=2, color='navy'),
                                         showlegend=False))
            continue
        x, y = poly.exterior.xy
        fig.add_trace(go.Scatter(x=list(x)+[x[0]], y=list(y)+[y[0]],
                                 mode='lines', fill='toself',
                                 fillcolor='rgba(100,149,237,0.35)',
                                 line=dict(width=2, color='navy'),
                                 showlegend=False))

    fig.update_layout(title=f"{axis.upper()} Slice @ {value:.4f}",
                      template='plotly_white', yaxis_scaleanchor='x',
                      xaxis_title=data["xlabel"], yaxis_title=data["ylabel"],
                      margin=dict(l=40, r=40, t=50, b=40), paper_bgcolor='#f5f5f5')
    if axis == 'x':
        fig.update_xaxes(range=[ymin, ymax]); fig.update_yaxes(range=[zmin, zmax])
    elif axis == 'y':
        fig.update_xaxes(range=[xmin, xmax]); fig.update_yaxes(range=[zmin, zmax])
    else:
        fig.update_xaxes(range=[xmin, xmax]); fig.update_yaxes(range=[ymin, ymax])
    return fig


# ================================================================
# 3D Figure
# ================================================================

def build_3d_figure(mesh, axis, value, tip_points=None):
    vertices = mesh.vertices
    faces = mesh.faces
    fig = go.Figure()
    fig.add_trace(go.Mesh3d(x=vertices[:,0], y=vertices[:,1], z=vertices[:,2],
                              i=faces[:,0], j=faces[:,1], k=faces[:,2],
                              opacity=0.5, name='STL'))
    bounds = mesh.bounds
    xmin, ymin, zmin = bounds[0]; xmax, ymax, zmax = bounds[1]
    if axis == 'x':
        xx, yy, zz = np.array([[value,value],[value,value]]), np.array([[ymin,ymax],[ymin,ymax]]), np.array([[zmin,zmin],[zmax,zmax]])
    elif axis == 'y':
        xx, yy, zz = np.array([[xmin,xmax],[xmin,xmax]]), np.array([[value,value],[value,value]]), np.array([[zmin,zmin],[zmax,zmax]])
    else:
        xx, yy, zz = np.array([[xmin,xmax],[xmin,xmax]]), np.array([[ymin,ymin],[ymax,ymax]]), np.array([[value,value],[value,value]])
    fig.add_trace(go.Surface(x=xx, y=yy, z=zz, opacity=0.5, showscale=False, name='Slice Plane'))

    # Add tip points if provided
    if tip_points and len(tip_points) > 0:
        tip_arr = np.array(tip_points)
        fig.add_trace(go.Scatter3d(
            x=tip_arr[:, 0], y=tip_arr[:, 1], z=tip_arr[:, 2],
            mode='markers+text',
            marker=dict(size=8, color='red', symbol='x', line=dict(width=2, color='white')),
            text=[f"tip {i}" for i in range(len(tip_points))],
            textposition='top center',
            name='Tips',
            showlegend=False
        ))

    fig.update_layout(template='plotly_white', scene_aspectmode='data', margin=dict(l=0,r=0,b=0,t=30))
    return fig


# ================================================================
# Load STL file
# ================================================================

def load_stl(stl_file):
    mesh = trimesh.load_mesh(stl_file)
    if mesh.is_empty:
        return None
    total_surface_area = mesh.area
    bounds = mesh.bounds
    xmin, ymin, zmin = bounds[0]
    xmax, ymax, zmax = bounds[1]
    bbox_center = (bounds[0] + bounds[1]) / 2
    bbox_xc, bbox_yc, bbox_zc = bbox_center
    if mesh.is_watertight:
        cm = mesh.center_mass
        cm_desc = "  (watertight)"
    else:
        v0, v1, v2 = mesh.vertices[mesh.faces[:,0]], mesh.vertices[mesh.faces[:,1]], mesh.vertices[mesh.faces[:,2]]
        fc = (v0+v1+v2) / 3.0
        normals = np.cross(v1-v0, v2-v0)
        areas = np.linalg.norm(normals, axis=1) / 2.0
        cm = np.sum(fc * areas[:, None], axis=0) / areas.sum()
        cm_desc = "  (non-watertight)"
    proj = compute_projection_area(mesh)
    return {
        "mesh": mesh, "total_surface_area": total_surface_area,
        "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax,
        "zmin": zmin, "zmax": zmax,
        "bbox_xc": bbox_xc, "bbox_yc": bbox_yc, "bbox_zc": bbox_zc,
        "cm_x": cm[0], "cm_y": cm[1], "cm_z": cm[2],
        "cm_desc": cm_desc,
        "proj_xy": proj["XY"], "proj_xz": proj["XZ"], "proj_yz": proj["YZ"],
    }


# ================================================================
# Main
# ================================================================

if len(sys.argv) < 2:
    print("Usage: python find_tip.py <stl_file>")
    sys.exit(1)

stl_file = sys.argv[1]
info = load_stl(stl_file)
if info is None:
    print("ERROR: failed to load STL file")
    sys.exit(1)


# ================================================================
# Dash app
# ================================================================

app = Dash(__name__)

# Shared state
_tip_points_store = []
_tip_text_store = ""

app.layout = html.Div([
    # ===== LEFT PANE: info panel =====
    html.Div([
        # Reset button
        html.Button("↺ Reset", id='btn-reset', n_clicks=0, n_clicks_timestamp=-1,
            style={'width':'100%', 'padding':'8px', 'fontSize':13,
                   'backgroundColor':'#e0e0e0', 'border':'none',
                   'borderRadius':'5px', 'cursor':'pointer', 'marginBottom':'10px'}),

        # File upload
        dcc.Upload(
            id='file-upload',
            children=html.Div([
                html.P("📁 Drag & Drop or click to browse STL"),
            ], style={'textAlign':'center', 'padding':'5px 0', 'fontSize':12}),
            style={
                'width': '100%', 'height': '50px',
                'borderWidth': '2px', 'borderStyle': 'dashed',
                'borderRadius': '5px', 'textAlign': 'center',
                'backgroundColor': '#fafafa',
                'lineHeight': '40px', 'cursor': 'pointer',
                'marginBottom': '10px', 'boxSizing': 'border-box'
            },
            multiple=False
        ),

        # Status message
        html.Div(id='loading-status', children="", style={'textAlign':'center', 'color':'#0099ff', 'fontSize':12, 'fontWeight':'bold', 'marginBottom':10}),

        # Info
        html.P(id='file-name', children=f"📄 {os.path.basename(stl_file)}"),
        html.H3(id='surface-area', children=f"Surface Area = {info['total_surface_area']:.6f}"),

        html.H4("Projection Areas"),
        html.P(id='proj-xy', children=f"XY: {info['proj_xy']:.6f} m^2"),
        html.P(id='proj-xz', children=f"XZ: {info['proj_xz']:.6f} m^2"),
        html.P(id='proj-yz', children=f"YZ: {info['proj_yz']:.6f} m^2"),

        html.H4("BBox Center"),
        html.P(id='bbox-center', children=f"X: {info['bbox_xc']:.4f}, Y: {info['bbox_yc']:.4f}, Z: {info['bbox_zc']:.4f}"),

        html.H4("Center of Mass"),
        html.P(id='center-mass', children=f"X: {info['cm_x']:.4f}, Y: {info['cm_y']:.4f}, Z: {info['cm_z']:.4f}"),
        html.Small(id='cm-desc', children=info["cm_desc"], style={"color": "gray"}),

        html.H4("Slice Axis"),
        dcc.Tabs(id='axis-tabs', value='x', children=[
            dcc.Tab(label='X', value='x'),
            dcc.Tab(label='Y', value='y'),
            dcc.Tab(label='Z', value='z'),
        ]),
    ], style={
        'width': '20%', 'padding': '10px', 'overflowY': 'scroll',
        'height': '100vh', 'borderRight': '1px solid gray'
    }),

    # ===== RIGHT PANE: 2D slice + 3D =====
    html.Div([
        # X/Y/Z axis buttons above 2D figure
        html.Div([
            html.Button("X", id='btn-axis-x', n_clicks=0,
                style={'width':'40px', 'height':'32px', 'fontSize':14, 'fontWeight':'bold', 'cursor':'pointer'}),
            html.Button("Y", id='btn-axis-y', n_clicks=0,
                style={'width':'40px', 'height':'32px', 'fontSize':14, 'fontWeight':'bold', 'cursor':'pointer'}),
            html.Button("Z", id='btn-axis-z', n_clicks=0,
                style={'width':'40px', 'height':'32px', 'fontSize':14, 'fontWeight':'bold', 'cursor':'pointer'}),
        ], style={'textAlign':'center', 'marginBottom':4}),
        dcc.Graph(id='slice-2d', style={'height': '45vh'}),
        dcc.Graph(id='slice-3d', style={'height': '50vh'}),
        html.Div(id='tip-list', children="", style={
            'width': '100%', 'height': '80px', 'overflowY': 'auto', 'fontSize': 11,
            'fontFamily': 'monospace', 'backgroundColor': '#1e1e1e', 'color': '#d4d4d4',
            'padding': '8px', 'borderRadius': '5px', 'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all'
        }),
    ], style={'width': '80%'}),
], style={'display': 'flex'})


# ================================================================
# Callbacks
# ================================================================

# single unified callback
@app.callback(
    Output('slice-2d', 'figure'),
    Output('slice-3d', 'figure'),
    Output('file-name', 'children'),
    Output('surface-area', 'children'),
    Output('proj-xy', 'children'),
    Output('proj-xz', 'children'),
    Output('proj-yz', 'children'),
    Output('bbox-center', 'children'),
    Output('center-mass', 'children'),
    Output('cm-desc', 'children'),
    Output('loading-status', 'children'),
    Output('tip-list', 'children'),
    Input('axis-tabs', 'value'),
    Input('file-upload', 'contents'),
    Input('btn-reset', 'n_clicks'),
    Input('btn-find-tip', 'n_clicks'),
    Input('btn-axis-x', 'n_clicks'),
    Input('btn-axis-y', 'n_clicks'),
    Input('btn-axis-z', 'n_clicks'),
    State('file-upload', 'filename'),
    prevent_initial_call=True,
)
def unified_update(axis, file_contents, reset_n, find_tip_n, btn_x, btn_y, btn_z, file_filename):
    global info, _tip_points_store, _tip_text_store

    trigger = callback_context.triggered[0] if callback_context.triggered else None
    trigger_name = trigger['prop_id'].split('.')[0] if trigger else None

    # Determine current axis
    current_axis = axis
    if trigger_name in ('btn-axis-x',):
        current_axis = 'x'
    elif trigger_name in ('btn-axis-y',):
        current_axis = 'y'
    elif trigger_name in ('btn-axis-z',):
        current_axis = 'z'

    if current_axis == 'x':
        value = (info['xmin'] + info['xmax']) / 2
    elif current_axis == 'y':
        value = (info['ymin'] + info['ymax']) / 2
    else:
        value = (info['zmin'] + info['zmax']) / 2

    # ---- File upload ----
    if trigger_name == 'file-upload' and file_contents is not None:
        fname = file_filename or 'unnamed.stl'
        content_type, content_string = file_contents.split(',')
        decoded = base64.b64decode(content_string)
        save_path = os.path.join('/tmp', fname)
        with open(save_path, 'wb') as f:
            f.write(decoded)
        new_info = load_stl(save_path)
        if new_info is None:
            return (no_update, no_update, f'❌ Failed', no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update,
                    '❌ Failed', no_update)
        info = new_info
        _tip_points_store = []
        _tip_text_store = ""
        cx = (new_info['xmin'] + new_info['xmax']) / 2
        data = extract_slice(new_info['mesh'], 'x', cx)
        return (build_2d_figure(data, 'x', 0, cx,
                        new_info['xmin'], new_info['xmax'],
                        new_info['ymin'], new_info['ymax'],
                        new_info['zmin'], new_info['zmax']),
                build_3d_figure(new_info['mesh'], 'x', cx),
                f"📄 {os.path.basename(save_path)}",
                f"Surface Area = {new_info['total_surface_area']:.6f}",
                f"XY: {new_info['proj_xy']:.6f} m^2",
                f"XZ: {new_info['proj_xz']:.6f} m^2",
                f"YZ: {new_info['proj_yz']:.6f} m^2",
                f"X: {new_info['bbox_xc']:.4f}, Y: {new_info['bbox_yc']:.4f}, Z: {new_info['bbox_zc']:.4f}",
                f"X: {new_info['cm_x']:.4f}, Y: {new_info['cm_y']:.4f}, Z: {new_info['cm_z']:.4f}",
                new_info["cm_desc"],
                "✅ Loaded", no_update)

    # ---- Reset ----
    if trigger_name == 'btn-reset':
        _tip_points_store = []
        _tip_text_store = ""
        cx = (info['xmin'] + info['xmax']) / 2
        data = extract_slice(info['mesh'], 'x', cx)
        return (build_2d_figure(data, 'x', 0, cx,
                        info['xmin'], info['xmax'],
                        info['ymin'], info['ymax'],
                        info['zmin'], info['zmax']),
                build_3d_figure(info['mesh'], 'x', cx),
                f"📄 {os.path.basename(stl_file)}",
                f"Surface Area = {info['total_surface_area']:.6f}",
                f"XY: {info['proj_xy']:.6f} m^2",
                f"XZ: {info['proj_xz']:.6f} m^2",
                f"YZ: {info['proj_yz']:.6f} m^2",
                f"X: {info['bbox_xc']:.4f}, Y: {info['bbox_yc']:.4f}, Z: {info['bbox_zc']:.4f}",
                f"X: {info['cm_x']:.4f}, Y: {info['cm_y']:.4f}, Z: {info['cm_z']:.4f}",
                info["cm_desc"],
                "↺ Reset to default", no_update)

    # ---- Find Tip (hardcoded tol=0.5) ----
    if trigger_name == 'btn-find-tip':
        tip_points = find_tip_points(info['mesh'], tol=0.5)
        _tip_points_store = tip_points

        lines = [f"[{len(tip_points)} tips found]\n"]
        for i, tp in enumerate(tip_points):
            lines.append(f"tip{i+1}: ({tp[0]:8.4f}, {tp[1]:8.4f}, {tp[2]:8.4f})")
        _tip_text_store = "\n".join(lines)

    # ---- Normal slice update ----
    data = extract_slice(info['mesh'], current_axis, value)
    fig2d = build_2d_figure(data, current_axis, 0, value,
                             info['xmin'], info['xmax'],
                             info['ymin'], info['ymax'],
                             info['zmin'], info['zmax'])
    fig3d = build_3d_figure(info['mesh'], current_axis, value,
                            tip_points=_tip_points_store if _tip_points_store else None)

    return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
            no_update, no_update, no_update,
            no_update, _tip_text_store)


# ================================================================
# Run
# ================================================================

app.run(host="0.0.0.0", port=8051, debug=True)
