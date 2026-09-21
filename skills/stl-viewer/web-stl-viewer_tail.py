# === MAIN CALLBACK — 29 outputs, correct tuple lengths ===
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
    Input('x-slider', 'value'),
    Input('y-slider', 'value'),
    Input('z-slider', 'value'),
    Input('axis-x', 'n_clicks'),
    Input('axis-y', 'n_clicks'),
    Input('axis-z', 'n_clicks'),
    Input('file-upload', 'contents'),
    Input('btn-find-tip', 'n_clicks'),
    Input('btn-reset', 'n_clicks'),
    Input('tol-slider', 'value'),
    State('file-upload', 'filename'),
)
def unified_update(x_val, y_val, z_val, nx, ny, nz, file_contents,
                   find_tip_n, reset_n, tol_val_input, file_filename):
    global info, _tip_points_store, _tip_text_store

    triggered = callback_context.triggered
    triggered_id = triggered[0]['prop_id'].split('.')[0] if triggered else None

    # Determine active axis from triggered input
    if triggered_id == 'x-slider': axis = 'x'
    elif triggered_id == 'y-slider': axis = 'y'
    elif triggered_id == 'z-slider': axis = 'z'
    elif triggered_id == 'axis-x': axis = 'x'
    elif triggered_id == 'axis-y': axis = 'y'
    elif triggered_id == 'axis-z': axis = 'z'
    elif triggered_id == 'tol-slider':
        # Build button state for current axis first
        if axis == 'x': bx, by, bz = (nx if nx is not None else 0)+1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif axis == 'y': bx, by, bz = 0, (ny if ny is not None else 0)+1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, (nz if nz is not None else 0)+1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()

        tol_val = tol_val_input
        tip_points = find_tip_points(info['mesh'], tol=tol_val)
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        if axis == 'x': value = x_val
        elif axis == 'y': value = y_val
        else: value = z_val
        data = extract_slice(info['mesh'], axis, value)
        fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=tip_points)
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {tol_val:.3f}")
    elif nx is not None and ny is not None and nz is not None and (nx > 0 or ny > 0 or nz > 0):
        if nx > 0 and (ny == 0 or nx >= ny) and (nz == 0 or nx >= nz): axis = 'x'
        elif ny > 0 and (nx == 0 or ny >= nx) and (nz == 0 or ny >= nz): axis = 'y'
        else: axis = 'z'
    else:
        axis = 'x'

    # Build button outputs
    if axis == 'x': bx, by, bz = (nx if nx is not None else 0)+1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
    elif axis == 'y': bx, by, bz = 0, (ny if ny is not None else 0)+1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
    else: bx, by, bz = 0, 0, (nz if nz is not None else 0)+1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()

    # === FILE UPLOAD ===
    if triggered and 'file-upload.contents' in (triggered[0]['prop_id'] if triggered else ''):
        if file_contents is None: return tuple([no_update]*29)
        content_type, content_string = file_contents.split(',')
        decoded = base64.b64decode(content_string)
        save_path = os.path.join('/tmp', file_filename)
        with open(save_path, 'wb') as f: f.write(decoded)
        new_info = load_stl(save_path)
        if new_info is None:
            return (no_update, no_update, '❌ Failed', *([no_update]*24), _tip_text_store, "TOL: 0.500")
        info = new_info
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
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500")

    # === FIND TIP ===
    if triggered_id == 'btn-find-tip' and find_tip_n and find_tip_n > 0:
        tip_points = find_tip_points(info['mesh'], tol=0.5)
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        if axis == 'x': value = x_val
        elif axis == 'y': value = y_val
        else: value = z_val
        data = extract_slice(info['mesh'], axis, value)
        fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=tip_points)
        return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500")

    # === RESET ===
    if triggered_id == 'btn-reset' and reset_n and reset_n > 0:
        _tip_points_store = []; _tip_text_store = ''
        cx = (info['xmin']+info['xmax'])/2
        cy = (info['ymin']+info['ymax'])/2
        cz = (info['zmin']+info['zmax'])/2
        data = extract_slice(info['mesh'], 'x', cx)
        fig2d = build_2d_figure(data, 'x', 0, cx, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', cx)
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
                bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500")

    # === SLIDER / BUTTON → update graphs ===
    if axis == 'x': value = x_val
    elif axis == 'y': value = y_val
    else: value = z_val
    data = extract_slice(info['mesh'], axis, value)
    fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
    fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=_tip_points_store if _tip_points_store else None)
    return (fig2d, fig3d, no_update, no_update, no_update, no_update, no_update,
            no_update, no_update,
            f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
            no_update, no_update, no_update, no_update, no_update, no_tuple,
            no_update, no_update, no_update,
            bx,by,bz,xs,ys,zs, _tip_text_store, "TOL: 0.500")


# ============================================================
# Run
# ============================================================

app.run(host="0.0.0.0", port=8051, debug=True)
