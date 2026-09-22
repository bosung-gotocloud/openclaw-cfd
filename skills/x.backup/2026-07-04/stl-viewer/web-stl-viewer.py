#!/usr/bin/env python3

import sys
import os
import base64
import numpy as np
import trimesh

from shapely.geometry import Polygon
from shapely.ops import unary_union

import plotly.graph_objects as go

from dash import Dash, dcc, html, callback, Output, Input, no_update, State, callback_context


# ============================================================
# Projection area
# ============================================================

def compute_projection_area(mesh):
    normals = {"XY": [0, 0, 1], "XZ": [0, 1, 0], "YZ": [1, 0, 0]}
    areas = {}
    for label, normal in normals.items():
        n = np.array(normal, dtype=float); n /= np.linalg.norm(n)
        if abs(n[0]) < 0.9: u = np.cross(n, [1, 0, 0])
        else: u = np.cross(n, [0, 1, 0])
        u /= np.linalg.norm(u); v = np.cross(n, u); v /= np.linalg.norm(v)
        visible_faces = mesh.faces; visible_verts = mesh.vertices[visible_faces]
        polys = []
        for fv in visible_verts:
            fu = fv @ u; fv_proj = fv @ v
            poly = [(fu[0], fv_proj[0]), (fu[1], fv_proj[1]), (fu[2], fv_proj[2])]
            try:
                poly = Polygon(poly)
                if poly.is_valid and poly.area > 1e-15: polys.append(poly)
            except Exception: continue
        if polys:
            merged = unary_union(polys)
            areas[label] = merged.area if hasattr(merged, "area") else 0.0
        else:
            areas[label] = 0.0
    return areas


# ============================================================
# Slice extraction
# ============================================================

def make_plane(axis, value):
    origin = [0.0, 0.0, 0.0]; origin[axis] = value
    normal = [0.0, 0.0, 0.0]; normal[axis] = 1.0
    return np.array(origin), np.array(normal)


def extract_slice(mesh, axis, value):
    if isinstance(axis, str): axis = {'x': 0, 'y': 1, 'z': 2}[axis]
    origin, normal = make_plane(axis, value)
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    if section is None:
        return {"paths": [], "polygons": [], "area": 0.0, "contours": [], "xlabel": "", "ylabel": ""}
    polygons, paths, contours = [], [], []
    xlabel, ylabel = "", ""
    for discrete in section.discrete:
        pts3d = np.array(discrete)
        if len(pts3d) < 3: continue
        if axis == 0: px, py = pts3d[:, 1], pts3d[:, 2]; xlabel, ylabel = "Y", "Z"
        elif axis == 1: px, py = pts3d[:, 0], pts3d[:, 2]; xlabel, ylabel = "X", "Z"
        else: px, py = pts3d[:, 0], pts3d[:, 1]; xlabel, ylabel = "X", "Y"
        pts2d = np.vstack([px, py]).T
        try:
            poly = Polygon(pts2d)
            if not poly.is_valid: poly = poly.buffer(0)
            if poly.area <= 1e-12: continue
        except Exception: continue
        polygons.append(poly); paths.append(pts2d)
        center3d = np.mean(pts3d, axis=0)
        if axis == 0: center2d = (center3d[1], center3d[2])
        elif axis == 1: center2d = (center3d[0], center3d[2])
        else: center2d = (center3d[0], center3d[1])
        contours.append({"polygon": poly, "center2d": center2d,
                         "center3d": tuple(center3d), "area": poly.area})
    return {"paths": paths, "polygons": polygons, "area": 0.0,
            "contours": contours, "xlabel": xlabel, "ylabel": ylabel}


# ============================================================
# Figure builders
# ============================================================

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
                                         line=dict(width=2, color='navy'), showlegend=False))
            continue
        x, y = poly.exterior.xy
        fig.add_trace(go.Scatter(x=list(x)+[x[0]], y=list(y)+[y[0]],
                                 mode='lines', fill='toself',
                                 fillcolor='rgba(100,149,237,0.35)',
                                 line=dict(width=2, color='navy'), showlegend=False))
    fig.update_layout(title=f"{axis.upper()} Slice @ {value:.4f}",
                      template='plotly_white', yaxis_scaleanchor='x',
                      xaxis_title=data["xlabel"], yaxis_title=data["ylabel"],
                      margin=dict(l=40, r=40, t=50, b=40), paper_bgcolor='#f5f5f5')
    if axis == 'x': fig.update_xaxes(range=[ymin, ymax]); fig.update_yaxes(range=[zmin, zmax])
    elif axis == 'y': fig.update_xaxes(range=[xmin, xmax]); fig.update_yaxes(range=[zmin, zmax])
    else: fig.update_xaxes(range=[xmin, xmax]); fig.update_yaxes(range=[ymin, ymax])
    return fig


def build_3d_figure(mesh, axis, value, tip_points=None):
    vertices = mesh.vertices; faces = mesh.faces
    fig = go.Figure()
    fig.add_trace(go.Mesh3d(x=vertices[:,0], y=vertices[:,1], z=vertices[:,2],
                              i=faces[:,0], j=faces[:,1], k=faces[:,2],
                              opacity=0.5, name='STL'))
    bounds = mesh.bounds; xmin, ymin, zmin = bounds[0]; xmax, ymax, zmax = bounds[1]
    if axis == 'x':
        xx, yy, zz = (np.array([[value,value],[value,value]]), np.array([[ymin,ymax],[ymin,ymax]]), np.array([[zmin,zmin],[zmax,zmax]]))
    elif axis == 'y':
        xx, yy, zz = (np.array([[xmin,xmax],[xmin,xmax]]), np.array([[value,value],[value,value]]), np.array([[zmin,zmin],[zmax,zmax]]))
    else:
        xx, yy, zz = (np.array([[xmin,xmax],[xmin,xmax]]), np.array([[ymin,ymin],[ymax,ymax]]), np.array([[value,value],[value,value]]))
    fig.add_trace(go.Surface(x=xx, y=yy, z=zz, opacity=0.5, showscale=False, name='Slice Plane'))
    if tip_points and len(tip_points) > 0:
        ta = np.array(tip_points)
        tip_texts = [f'tip {j+1}' for j in range(len(ta))]
        fig.add_trace(go.Scatter3d(x=ta[:,0], y=ta[:,1], z=ta[:,2], mode='markers+text',
            marker=dict(size=8, color='red', symbol='circle'),
            text=tip_texts, textposition='top center',
            name='Tips', showlegend=False))
    fig.update_layout(template='plotly_white', scene_aspectmode='data', margin=dict(l=0,r=0,b=0,t=30))
    return fig


# ============================================================
# Load STL
# ============================================================

def load_stl(stl_file):
    mesh = trimesh.load_mesh(stl_file)
    if mesh.is_empty: return None
    total_surface_area = mesh.area; bounds = mesh.bounds
    xmin, ymin, zmin = bounds[0]; xmax, ymax, zmax = bounds[1]
    bbox_center = (bounds[0] + bounds[1]) / 2
    bbox_xc, bbox_yc, bbox_zc = bbox_center
    if mesh.is_watertight: cm = mesh.center_mass
    else:
        v0, v1, v2 = (mesh.vertices[mesh.faces[:,0]], mesh.vertices[mesh.faces[:,1]], mesh.vertices[mesh.faces[:,2]])
        fc = (v0+v1+v2) / 3.0; normals = np.cross(v1-v0, v2-v0)
        areas = np.linalg.norm(normals, axis=1) / 2.0
        cm = np.sum(fc * areas[:, None], axis=0) / areas.sum()
    proj = compute_projection_area(mesh)
    return {"mesh": mesh, "total_surface_area": total_surface_area,
            "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax,
            "zmin": zmin, "zmax": zmax,
            "bbox_xc": bbox_xc, "bbox_yc": bbox_yc, "bbox_zc": bbox_zc,
            "cm_x": cm[0], "cm_y": cm[1], "cm_z": cm[2],
            "proj_xy": proj["XY"], "proj_xz": proj["XZ"], "proj_yz": proj["YZ"],
            "is_watertight": mesh.is_watertight}


# ============================================================
# find_tip — tip point detection
# ============================================================

def find_tip_points(mesh, tol=0.5):
    from sklearn.cluster import DBSCAN
    vertices = mesh.vertices; faces = mesh.faces
    tip_candidates = []
    for proj_dir, axis1, axis2 in [('yz', 1, 2), ('xz', 0, 2), ('xy', 0, 1)]:
        centroids = vertices[faces].mean(axis=1)
        verts_2d = vertices[:, [axis1, axis2]]
        origin_2d = centroids[:, [axis1, axis2]].mean(axis=0)
        radial = np.linalg.norm(verts_2d - origin_2d, axis=1)
        for pct in [30, 50, 70]:
            threshold = np.percentile(radial, pct)
            high_mask = radial > threshold
            if high_mask.sum() == 0: continue
            high_coords = verts_2d[high_mask]
            high_indices = np.where(high_mask)[0]
            high_radial = radial[high_mask]
            if len(high_indices) < 10: continue
            # Downsample for performance on large meshes
            if len(high_indices) > 5000:
                rng = np.random.RandomState(42)
                idx = rng.choice(len(high_indices), 5000, replace=False)
                high_coords = high_coords[idx]
                high_indices = high_indices[idx]
                high_radial = high_radial[idx]
            scale = np.std(high_coords, axis=0)
            scale[scale < 1e-6] = 1.0
            features = high_coords / scale
            eps_val = 0.3 / max(scale.min(), 1e-6)
            eps_val = max(0.001, min(eps_val, 0.999))
            clustering = DBSCAN(eps=eps_val, min_samples=5).fit(features)
            labels = clustering.labels_
            for label in set(labels):
                if label == -1: continue
                cm_mask = labels == label
                cluster_idx_2d = high_indices[cm_mask]
                cluster_radial = high_radial[cm_mask]
                peak_local = cluster_radial.argmax()
                peak_idx_3d = cluster_idx_2d[peak_local]
                tip_candidates.append(vertices[peak_idx_3d].copy())
    tips = []
    for t in tip_candidates:
        if not any(np.linalg.norm(t - q) < tol for q in tips): tips.append(t)
    return tips[:20]


# ============================================================
# Main
# ============================================================

if len(sys.argv) < 2:
    print("Usage: python web-stl-viewer.py <stl_file>")
    sys.exit(1)

stl_file = sys.argv[1]
info = load_stl(stl_file)
if info is None:
    print("ERROR: failed to load STL file")
    sys.exit(1)

# Global state for tip points
_tip_points_store = []
_tip_text_store = ""


# ============================================================
# Dash app
# ============================================================

app = Dash(__name__)

def btn_active():
    return {'border':'1px solid #2c6fbb','textAlign':'center','padding':'4px 16px',
            'borderRadius':'4px','margin':'0 3px','backgroundColor':'#4a90d9',
            'cursor':'pointer','fontSize':12,'color':'white','fontWeight':'bold'}

def btn_inactive():
    return {'border':'1px solid #ddd','textAlign':'center','padding':'4px 16px',
            'borderRadius':'4px','margin':'0 3px','backgroundColor':'#f5f5f5',
            'cursor':'pointer','fontSize':12,'color':'#333'}

app.layout = html.Div([
    html.Div([
        dcc.Upload(id='file-upload',
            children=html.Div([html.P("📁 Drag & Drop or click to browse STL")],
                              style={'textAlign':'center','padding':'5px 0','fontSize':12}),
            style={'width':'100%','height':'50px','borderWidth':'2px','borderStyle':'dashed',
                   'borderRadius':'5px','textAlign':'center','backgroundColor':'#fafafa',
                   'lineHeight':'40px','cursor':'pointer','marginBottom':'10px','boxSizing':'border-box'},
            multiple=False),

        html.P(id='file-name', children=f"📄 {os.path.basename(stl_file)}", style={"fontSize":14,"fontWeight":"bold"}),
        html.H3(id='surface-area', children=f"Surface Area = {info['total_surface_area']:.6f}", style={"fontSize":14,"fontWeight":"bold"}),
        html.H4("Projection Areas", style={"fontSize":14,"fontWeight":"bold"}),
        html.P(id='proj-xy', children=f"XY: {info['proj_xy']:.6f}", style={"fontSize":14,"fontWeight":"bold"}),
        html.P(id='proj-xz', children=f"XZ: {info['proj_xz']:.6f}", style={"fontSize":14,"fontWeight":"bold"}),
        html.P(id='proj-yz', children=f"YZ: {info['proj_yz']:.6f}", style={"fontSize":14,"fontWeight":"bold"}),
        html.P(id='bbox-center', children=f"BBox : {info['xmax']-info['xmin']:.4f}, {info['ymax']-info['ymin']:.4f}, {info['zmax']-info['zmin']:.4f}", style={"fontSize":14,"fontWeight":"bold"}),
        html.P(id='center-mass', children=f"CG : {info['cm_x']:.4f}, {info['cm_y']:.4f}, {info['cm_z']:.4f}", style={"fontSize":14,"fontWeight":"bold"}),

        # Find Tip button
        html.Button('🎯 Find Tip', id='btn-find-tip', n_clicks=0,
                    style={'width':'100%','padding':'8px','fontSize':13,'backgroundColor':'#4a90d9','color':'white',
                           'border':'none','borderRadius':'5px','cursor':'pointer','marginTop':8,'fontWeight':'bold'}),
        # Reset button
        html.Button('↺ Reset', id='btn-reset', n_clicks=0,
                    style={'width':'100%','padding':'8px','fontSize':13,'backgroundColor':'#e0e0e0','border':'none',
                           'borderRadius':'5px','cursor':'pointer','marginTop':4}),
        # Export Tip button
        dcc.Download(id='download-tips'),
        html.Button('💾 Export Tip CSV', id='btn-export-tip', n_clicks=0,
                    style={'width':'100%','padding':'8px','fontSize':13,'backgroundColor':'#28a745','color':'white',
                           'border':'none','borderRadius':'5px','cursor':'pointer','marginTop':4,'fontWeight':'bold'}),
        # TOL slider
        html.Div(id='tol-label', children="TOL: 0.500", style={"textAlign":"center","fontWeight":"bold","fontSize":13,"marginTop":8,"marginBottom":4}),
        dcc.Slider(id='tol-slider', min=0.01, max=0.99, step=0.01, value=0.5,
                    marks={0.01: '0.01', 0.5: '0.5', 0.99: '0.99'}),
        # Tip list panel
        html.Div(id='tip-list', children="", style={'width':'100%','height':'80px','overflowY':'auto','fontSize':11,
            'fontFamily':'monospace','backgroundColor':'#1e1e1e','color':'#d4d4d4',
            'padding':'8px','borderRadius':'5px','whiteSpace':'pre-wrap','wordBreak':'break-all','marginTop':4}),

        html.Div(id='x-label', children=f"X: {(info['xmin']+info['xmax'])/2:.4f}", style={"textAlign":"center","fontWeight":"bold","fontSize":14,"marginTop":8,"marginBottom":8}),
        dcc.Slider(id='x-slider', min=info['xmin'], max=info['xmax'],
                    step=(info['xmax']-info['xmin'])/100, value=(info['xmin']+info['xmax'])/2),
        html.Div(id='y-label', children=f"Y: {(info['ymin']+info['ymax'])/2:.4f}", style={"textAlign":"center","fontWeight":"bold","fontSize":14,"marginTop":8,"marginBottom":8}),
        dcc.Slider(id='y-slider', min=info['ymin'], max=info['ymax'],
                    step=(info['ymax']-info['ymin'])/100, value=(info['ymin']+info['ymax'])/2),
        html.Div(id='z-label', children=f"Z: {(info['zmin']+info['zmax'])/2:.4f}", style={"textAlign":"center","fontWeight":"bold","fontSize":14,"marginTop":8,"marginBottom":8}),
        dcc.Slider(id='z-slider', min=info['zmin'], max=info['zmax'],
                    step=(info['zmax']-info['zmin'])/100, value=(info['zmin']+info['zmax'])/2),
    ], style={'width':'20%','padding':'10px','overflowY':'scroll','height':'100vh','borderRight':'1px solid gray'}),

    html.Div([
        html.Div([dcc.Graph(id='slice-2d', style={'height':'100%','width':'100%'})],
                 style={'height':'45vh','width':'100%','padding':'0 10px','boxSizing':'border-box'}),
        html.Div([
            html.Div("Slice Axis", style={'textAlign':'center','fontSize':11,'color':'#555','marginBottom':4}),
            html.Div([
                html.Button('X', id='axis-x', n_clicks=0, style=btn_active()),
                html.Button('Y', id='axis-y', n_clicks=0, style=btn_inactive()),
                html.Button('Z', id='axis-z', n_clicks=0, style=btn_inactive()),
            ], style={'display':'flex','justifyContent':'center','gap':'4px'}),
        ], style={'height':'5vh','width':'100%','display':'flex','flexDirection':'column',
                   'justifyContent':'center','borderBottom':'1px solid #ddd','background':'rgba(255,255,255,0.9)',
                   'boxSizing':'border-box','padding':'0 10px'}),
        html.Div([dcc.Graph(id='slice-3d', style={'height':'100%','width':'100%'})],
                 style={'height':'50vh','width':'100%','overflow':'auto','boxSizing':'border-box','padding':'0 10px'}),
    ], style={'display':'flex','flexDirection':'column','alignItems':'center','flex':1,'overflow':'hidden'}),
], style={'display':'flex'})


# slider marks
@app.callback(Output('x-slider', 'marks'), Input('x-slider', 'max'), Input('x-slider', 'min'))
def show_x_marks(xmax, xmin):
    step = (xmax - xmin) / 100; center = (xmin + xmax) / 2
    return {xmin: f"{xmin:.4f}", center: f"{center:.4f}", xmax: f"{xmax:.4f}"}

@app.callback(Output('y-slider', 'marks'), Input('y-slider', 'max'), Input('y-slider', 'min'))
def show_y_marks(ymax, ymin):
    center = (ymin + ymax) / 2
    return {ymin: f"{ymin:.4f}", center: f"{center:.4f}", ymax: f"{ymax:.4f}"}

@app.callback(Output('z-slider', 'marks'), Input('z-slider', 'max'), Input('z-slider', 'min'))
def show_z_marks(zmax, zmin):
    center = (zmin + zmax) / 2
    return {zmin: f"{zmin:.4f}", center: f"{center:.4f}", zmax: f"{zmax:.4f}"}


# === MAIN CALLBACK — 30 outputs, early-return per triggered_id (same as step-viewer) ===
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
    Output('x-label', 'children'),
    Output('y-label', 'children'),
    Output('z-label', 'children'),
    Output('x-slider', 'min'),
    Output('x-slider', 'max'),
    Output('x-slider', 'value'),
    Output('y-slider', 'min'),
    Output('y-slider', 'max'),
    Output('y-slider', 'value'),
    Output('z-slider', 'min'),
    Output('z-slider', 'max'),
    Output('z-slider', 'value'),
    Output('axis-x', 'n_clicks'),
    Output('axis-y', 'n_clicks'),
    Output('axis-z', 'n_clicks'),
    Output('axis-x', 'style'),
    Output('axis-y', 'style'),
    Output('axis-z', 'style'),
    Output('tip-list', 'children'),
    Output('tol-label', 'children'),
    Output('download-tips', 'data'),
    Input('x-slider', 'value'),
    Input('y-slider', 'value'),
    Input('z-slider', 'value'),
    Input('axis-x', 'n_clicks'),
    Input('axis-y', 'n_clicks'),
    Input('axis-z', 'n_clicks'),
    Input('file-upload', 'contents'),
    Input('btn-find-tip', 'n_clicks'),
    Input('btn-reset', 'n_clicks'),
    Input('btn-export-tip', 'n_clicks'),
    Input('tol-slider', 'value'),
    State('file-upload', 'filename'),
)
def unified_update(x_val, y_val, z_val, nx, ny, nz, file_contents,
                   find_tip_n, reset_n, export_tip_n, tol_val_input, file_filename):
    global info, _tip_points_store, _tip_text_store

    triggered = callback_context.triggered
    triggered_id = triggered[0]['prop_id'].split('.')[0] if triggered else None

    # Reset triggered flags
    export_tip_n = export_tip_n if export_tip_n else 0

    # === FILE UPLOAD ===
    if triggered_id == 'file-upload':
        if file_contents is None: return tuple([no_update]*30)
        content_type, content_string = file_contents.split(',')
        decoded = base64.b64decode(content_string)
        save_path = os.path.join('/tmp', file_filename)
        with open(save_path, 'wb') as f: f.write(decoded)
        new_info = load_stl(save_path)
        if new_info is None:
            return (no_update, no_update, '❌ Failed', no_update, no_update, no_update, no_update,
                    no_update, no_update,
                    no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    _tip_text_store, 'TOL: 0.500', None)
        info = new_info
        global stl_file
        stl_file = save_path
        _tip_points_store = []; _tip_text_store = ''
        cx = (new_info['xmin']+new_info['xmax'])/2
        cy = (new_info['ymin']+new_info['ymax'])/2
        cz = (new_info['zmin']+new_info['zmax'])/2
        data = extract_slice(new_info['mesh'], 'x', cx)
        return (build_2d_figure(data, 'x', 0, cx, new_info['xmin'],new_info['xmax'],new_info['ymin'],new_info['ymax'],new_info['zmin'],new_info['zmax']),
                build_3d_figure(new_info['mesh'], 'x', cx),
                f"📄 {os.path.basename(save_path)}",
                f"Surface Area = {new_info['total_surface_area']:.6f}",
                f"XY: {new_info['proj_xy']:.6f}", f"XZ: {new_info['proj_xz']:.6f}", f"YZ: {new_info['proj_yz']:.6f}",
                f"BBox : {new_info['xmax']-new_info['xmin']:.4f}, {new_info['ymax']-new_info['ymin']:.4f}, {new_info['zmax']-new_info['zmin']:.4f}",
                f"CG : {new_info['cm_x']:.4f}, {new_info['cm_y']:.4f}, {new_info['cm_z']:.4f}",
                f"X: {cx:.4f}", f"Y: {cy:.4f}", f"Z: {cz:.4f}",
                new_info['xmin'],new_info['xmax'],cx,
                new_info['ymin'],new_info['ymax'],cy,
                new_info['zmin'],new_info['zmax'],cz,
                1,0,0,btn_active(),btn_inactive(),btn_inactive(), _tip_text_store, "TOL: 0.500", None)

    # === AXIS BUTTON CLICKS — handle directly ===
    if triggered_id == 'axis-x':
        value = x_val
        data = extract_slice(info['mesh'], 'x', value)
        fig2d = build_2d_figure(data, 'x', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)

    if triggered_id == 'axis-y':
        value = y_val
        data = extract_slice(info['mesh'], 'y', value)
        fig2d = build_2d_figure(data, 'y', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'y', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 1, 0
        xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        tol_curr = f"TOL: {tol_val_input:.3f}"
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, tol_curr, None)

    if triggered_id == 'axis-z':
        value = z_val
        data = extract_slice(info['mesh'], 'z', value)
        fig2d = build_2d_figure(data, 'z', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'z', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 0, 1
        xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        tol_curr = f"TOL: {tol_val_input:.3f}"
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, tol_curr, None)

    # === SLIDER CLICKS — handle directly ===
    if triggered_id == 'x-slider':
        value = x_val
        data = extract_slice(info['mesh'], 'x', value)
        fig2d = build_2d_figure(data, 'x', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)

    if triggered_id == 'y-slider':
        value = y_val
        data = extract_slice(info['mesh'], 'y', value)
        fig2d = build_2d_figure(data, 'y', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'y', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 1, 0
        xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)

    if triggered_id == 'z-slider':
        value = z_val
        data = extract_slice(info['mesh'], 'z', value)
        fig2d = build_2d_figure(data, 'z', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'z', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 0, 1
        xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)

    # === FIND TIP ===
    if triggered_id == 'btn-find-tip' and find_tip_n and find_tip_n > 0:
        try:
            tip_points = find_tip_points(info['mesh'], tol=0.5)
        except Exception:
            tip_points = []
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        # Determine current axis from trigger or slider position
        if triggered_id == 'x-slider': value = x_val; cur_axis = 'x'
        elif triggered_id == 'y-slider': value = y_val; cur_axis = 'y'
        elif triggered_id == 'z-slider': value = z_val; cur_axis = 'z'
        elif triggered_id == 'axis-x': value = x_val; cur_axis = 'x'
        elif triggered_id == 'axis-y': value = y_val; cur_axis = 'y'
        elif triggered_id == 'axis-z': value = z_val; cur_axis = 'z'
        else: value = x_val; cur_axis = 'x'
        data = extract_slice(info['mesh'], cur_axis, value)
        fig2d = build_2d_figure(data, cur_axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], cur_axis, value, tip_points=tip_points)
        if cur_axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif cur_axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)

    # === EXPORT TIP CSV ===
    if triggered_id == 'btn-export-tip' and export_tip_n and export_tip_n > 0:
        # Determine current button state from sliders
        if x_val >= y_val and x_val >= z_val: cur_axis = 'x'
        elif y_val >= x_val and y_val >= z_val: cur_axis = 'y'
        else: cur_axis = 'z'
        if cur_axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif cur_axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()

        if not _tip_points_store or len(_tip_points_store) == 0:
            return (no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update,
                    f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update,
                    bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)
        export_dir = os.path.dirname(stl_file) if os.path.dirname(stl_file) else '/tmp'
        if not os.path.isdir(export_dir):
            export_dir = '/tmp'
        base_name = os.path.splitext(os.path.basename(stl_file))[0]
        csv_path = os.path.join(export_dir, f"{base_name}_tip_points.csv")
        with open(csv_path, 'w') as f:
            for t in _tip_points_store:
                f.write(f"{t[0]:.6f},{t[1]:.6f},{t[2]:.6f}\n")
        print(f"  Tip points exported to: {csv_path}")
        csv_text = open(csv_path).read()
        export_data = {'content': csv_text, 'filename': os.path.basename(csv_path)}
        return (no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                0,0,0,
                btn_inactive(),btn_inactive(),btn_active(),
                _tip_text_store, "TOL: 0.500", export_data)

    # === RESET ===
    if triggered_id == 'btn-reset' and reset_n and reset_n > 0:
        _tip_points_store = []; _tip_text_store = ''
        cx = (info['xmin']+info['xmax'])/2
        cy = (info['ymin']+info['ymax'])/2
        cz = (info['zmin']+info['zmax'])/2
        data = extract_slice(info['mesh'], 'x', cx)
        fig2d = build_2d_figure(data, 'x', 0, cx, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', cx)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        return (fig2d, fig3d,
                f"📄 {os.path.basename(stl_file)}",
                f"Surface Area = {info['total_surface_area']:.6f}",
                f"XY: {info['proj_xy']:.6f}", f"XZ: {info['proj_xz']:.6f}", f"YZ: {info['proj_yz']:.6f}",
                f"BBox : {info['xmax']-info['xmin']:.4f}, {info['ymax']-info['ymin']:.4f}, {info['zmax']-info['zmin']:.4f}",
                f"CG : {info['cm_x']:.4f}, {info['cm_y']:.4f}, {info['cm_z']:.4f}",
                f"X: {cx:.4f}", f"Y: {cy:.4f}", f"Z: {cz:.4f}",
                info['xmin'],info['xmax'],cx,
                info['ymin'],info['ymax'],cy,
                info['zmin'],info['zmax'],cz,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500", None)
    if triggered_id == 'tol-slider':
        tol_val = tol_val_input
        try:
            tip_points = find_tip_points(info['mesh'], tol=tol_val)
        except Exception:
            tip_points = []
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        tol_label = f"TOL: {tol_val:.3f}"
        if x_val >= y_val and x_val >= z_val: axis, value = 'x', x_val
        elif y_val >= x_val and y_val >= z_val: axis, value = 'y', y_val
        else: axis, value = 'z', z_val
        data = extract_slice(info['mesh'], axis, value)
        fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=tip_points)
        if axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, tol_label, None)

    # === SLIDER VALUE CHANGES (default) ===
    if x_val >= y_val and x_val >= z_val: axis = 'x'
    elif y_val >= x_val and y_val >= z_val: axis = 'y'
    else: axis = 'z'

    if axis == 'x': value = x_val
    elif axis == 'y': value = y_val
    else: value = z_val
    data = extract_slice(info['mesh'], axis, value)
    fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
    fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=_tip_points_store if _tip_points_store else None)
    if axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
    elif axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
    else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
    return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
            no_update, no_update,
            f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
            no_update, no_update, no_update, no_update, no_update, no_update,
            no_update, no_update, no_update,
            bx,by,bz,xs,ys,zs, _tip_text_store, f"TOL: {tol_val_input:.3f}", None)


# ============================================================
# Run
# ============================================================

app.run(host="0.0.0.0", port=8051, debug=False)
