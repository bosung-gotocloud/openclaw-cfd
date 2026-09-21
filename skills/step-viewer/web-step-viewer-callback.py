def unified_update(x_val, y_val, z_val, nx, ny, nz, file_contents,
                   file_filename, find_tip_n, reset_n, export_tip_n, tol_val_input):
    global info, _tip_points_store, _tip_text_store, _tol_current
    global step_file, _tol_default, _tol_max

    triggered = callback_context.triggered
    triggered_id = triggered[0]['prop_id'].split('.')[0] if triggered else None

    export_tip_n = export_tip_n if export_tip_n else 0
    tol_val = tol_val_input if tol_val_input else _tol_default

    # Helper to build 37-item return for axis operations
    def _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, tip_text, tol_text):
        return (fig2d, fig3d,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx, by, bz, xs, ys, zs,
                tip_text, tol_text, None,
                no_update, no_update, no_update, no_update,
                {0: no_update, 1: no_update},
                {0: no_update, 1: no_update},
                {0: no_update, 1: no_update})

    def _ret_default():
        if x_val >= y_val and x_val >= z_val: axis, value = 'x', x_val
        elif y_val >= x_val and y_val >= z_val: axis, value = 'y', y_val
        else: axis, value = 'z', z_val
        data = extract_slice(info['mesh'], axis, value)
        fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=_tip_points_store if _tip_points_store else None)
        if axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        tol_text = f"TOL: {_tol_current if _tol_current else _tol_default:.4f}m"
        return (fig2d, fig3d,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx, by, bz, xs, ys, zs,
                _tip_text_store if _tip_text_store else '', tol_text, None,
                no_update, no_update, no_update, no_update,
                {0.01: '0.01', _tol_current if _tol_current else _tol_default: f'{(_tol_current if _tol_current else _tol_default):.4f}', _tol_max: f'{_tol_max:.4f}'},
                {info['xmin']: f"{info['xmin']:.4f}", cx: f"{cx:.4f}", info['xmax']: f"{info['xmax']:.4f}"},
                {info['ymin']: f"{info['ymin']:.4f}", cy: f"{cy:.4f}", info['ymax']: f"{info['ymax']:.4f}"},
                {info['zmin']: f"{info['zmin']:.4f}", cz: f"{cz:.4f}", info['zmax']: f"{info['zmax']:.4f}"})

    # === FILE UPLOAD ===
    if triggered_id == 'file-upload':
        if file_contents is None:
            return tuple([no_update]*37)
        content_type, content_string = file_contents.split(',')
        decoded = base64.b64decode(content_string)
        save_path = os.path.join('/tmp', file_filename)
        with open(save_path, 'wb') as f: f.write(decoded)
        new_info = load_step(save_path)
        if new_info is None:
            return (no_update, no_update, '❌ Failed', no_update, no_update, no_update, no_update,
                    no_update, no_update,
                    no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    _tip_text_store, 'TOL: 0.5000m', None,
                    no_update, no_update, no_update, no_update,
                    {0: no_update, 1: no_update}, {0: no_update, 1: no_update}, {0: no_update, 1: no_update})

        info = new_info
        step_file = save_path
        _tol_default = max(new_info['xmax']-new_info['xmin'], new_info['ymax']-new_info['ymin'], new_info['zmax']-new_info['zmin']) * 0.5
        _tol_max = max(new_info['xmax']-new_info['xmin'], new_info['ymax']-new_info['ymin'], new_info['zmax']-new_info['zmin'])
        _tol_current = _tol_default
        _tip_points_store = []
        _tip_text_store = ''
        cx = (new_info['xmin']+new_info['xmax'])/2
        cy = (new_info['ymin']+new_info['ymax'])/2
        cz = (new_info['zmin']+new_info['zmax'])/2
        data = extract_slice(new_info['mesh'], 'x', cx)
        fig2d = build_2d_figure(data, 'x', 0, cx, new_info['xmin'],new_info['xmax'],new_info['ymin'],new_info['ymax'],new_info['zmin'],new_info['zmax'])
        fig3d = build_3d_figure(new_info['mesh'], 'x', cx)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        tol_text = f"TOL: {_tol_default:.4f}m"
        return (fig2d, fig3d,
                f"📄 {os.path.basename(save_path)}",
                f"Surface Area = {new_info['total_surface_area']:.6f}",
                f"XY: {new_info['proj_xy']:.6f}", f"XZ: {new_info['proj_xz']:.6f}", f"YZ: {new_info['proj_yz']:.6f}",
                f"BBox : {new_info['xmax']-new_info['xmin']:.4f}, {new_info['ymax']-new_info['ymin']:.4f}, {new_info['zmax']-new_info['zmin']:.4f}",
                f"CG : {new_info['cm_x']:.4f}, {new_info['cm_y']:.4f}, {new_info['cm_z']:.4f}",
                f"X: {cx:.4f}", f"Y: {cy:.4f}", f"Z: {cz:.4f}",
                new_info['xmin'], new_info['xmax'], cx,
                new_info['ymin'], new_info['ymax'], cy,
                new_info['zmin'], new_info['zmax'], cz,
                bx, by, bz, xs, ys, zs,
                _tip_text_store, tol_text, None,
                0.01, _tol_max, _tol_default,
                {0.01: '0.01', _tol_default: f'{_tol_default:.4f}', _tol_max: f'{_tol_max:.4f}'},
                {new_info['xmin']: f"{new_info['xmin']:.4f}", cx: f"{cx:.4f}", new_info['xmax']: f"{new_info['xmax']:.4f}"},
                {new_info['ymin']: f"{new_info['ymin']:.4f}", cy: f"{cy:.4f}", new_info['ymax']: f"{new_info['ymax']:.4f}"},
                {new_info['zmin']: f"{new_info['zmin']:.4f}", cz: f"{cz:.4f}", new_info['zmax']: f"{new_info['zmax']:.4f}"})

    # === AXIS BUTTONS ===
    if triggered_id == 'axis-x':
        value = x_val
        data = extract_slice(info['mesh'], 'x', value)
        fig2d = build_2d_figure(data, 'x', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    if triggered_id == 'axis-y':
        value = y_val
        data = extract_slice(info['mesh'], 'y', value)
        fig2d = build_2d_figure(data, 'y', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'y', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 1, 0
        xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    if triggered_id == 'axis-z':
        value = z_val
        data = extract_slice(info['mesh'], 'z', value)
        fig2d = build_2d_figure(data, 'z', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'z', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 0, 1
        xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    # === SLIDER BUTTONS ===
    if triggered_id == 'x-slider':
        value = x_val
        data = extract_slice(info['mesh'], 'x', value)
        fig2d = build_2d_figure(data, 'x', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    if triggered_id == 'y-slider':
        value = y_val
        data = extract_slice(info['mesh'], 'y', value)
        fig2d = build_2d_figure(data, 'y', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'y', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 1, 0
        xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    if triggered_id == 'z-slider':
        value = z_val
        data = extract_slice(info['mesh'], 'z', value)
        fig2d = build_2d_figure(data, 'z', 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'z', value, tip_points=_tip_points_store if _tip_points_store else None)
        bx, by, bz = 0, 0, 1
        xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, f"TOL: {(_tol_current if _tol_current else _tol_default):.4f}m")

    # === FIND TIP ===
    if triggered_id == 'btn-find-tip' and find_tip_n and find_tip_n > 0:
        tol_use = _tol_current if _tol_current else _tol_default
        try:
            tip_points = find_tip_points(info['mesh'], tol=tol_use)
        except Exception:
            tip_points = []
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        if triggered_id == 'x-slider': value, cur_axis = x_val, 'x'
        elif triggered_id == 'y-slider': value, cur_axis = y_val, 'y'
        elif triggered_id == 'z-slider': value, cur_axis = z_val, 'z'
        elif triggered_id == 'axis-x': value, cur_axis = x_val, 'x'
        elif triggered_id == 'axis-y': value, cur_axis = y_val, 'y'
        elif triggered_id == 'axis-z': value, cur_axis = z_val, 'z'
        else: value, cur_axis = x_val, 'x'
        data = extract_slice(info['mesh'], cur_axis, value)
        fig2d = build_2d_figure(data, cur_axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], cur_axis, value, tip_points=tip_points)
        if cur_axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif cur_axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        tol_text = f"TOL: {_tol_current if _tol_current else _tol_default:.4f}m"
        return _ret_axis(fig2d, fig3d, bx, by, bz, xs, ys, zs, _tip_text_store, tol_text)

    # === EXPORT TIP CSV ===
    if triggered_id == 'btn-export-tip' and export_tip_n and export_tip_n > 0:
        if x_val >= y_val and x_val >= z_val: cur_axis = 'x'
        elif y_val >= x_val and y_val >= z_val: cur_axis = 'y'
        else: cur_axis = 'z'
        if cur_axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif cur_axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()

        tol_text = f"TOL: {_tol_current if _tol_current else _tol_default:.4f}m"

        if not _tip_points_store or len(_tip_points_store) == 0:
            return (no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update,
                    f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update,
                    bx, by, bz, xs, ys, zs,
                    _tip_text_store, tol_text, None,
                    no_update, no_update, no_update, no_update,
                    {0: no_update, 1: no_update}, {0: no_update, 1: no_update}, {0: no_update, 1: no_update})

        export_dir = os.path.dirname(step_file) if os.path.dirname(step_file) else '/tmp'
        if not os.path.isdir(export_dir):
            export_dir = '/tmp'
        base_name = os.path.splitext(os.path.basename(step_file))[0]
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
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                0, 0, 0,
                btn_inactive(), btn_inactive(), btn_active(),
                _tip_text_store, tol_text, export_data,
                no_update, no_update, no_update, no_update,
                {0: no_update, 1: no_update}, {0: no_update, 1: no_update}, {0: no_update, 1: no_update})

    # === RESET ===
    if triggered_id == 'btn-reset' and reset_n and reset_n > 0:
        _tip_points_store = []
        _tip_text_store = ''
        cx = (info['xmin']+info['xmax'])/2
        cy = (info['ymin']+info['ymax'])/2
        cz = (info['zmin']+info['zmax'])/2
        data = extract_slice(info['mesh'], 'x', cx)
        fig2d = build_2d_figure(data, 'x', 0, cx, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], 'x', cx)
        bx, by, bz = 1, 0, 0
        xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        tol_text = f"TOL: {_tol_default:.4f}m"
        return (fig2d, fig3d,
                f"📄 {os.path.basename(step_file)}",
                f"Surface Area = {info['total_surface_area']:.6f}",
                f"XY: {info['proj_xy']:.6f}", f"XZ: {info['proj_xz']:.6f}", f"YZ: {info['proj_yz']:.6f}",
                f"BBox : {info['xmax']-info['xmin']:.4f}, {info['ymax']-info['ymin']:.4f}, {info['zmax']-info['zmin']:.4f}",
                f"CG : {info['cm_x']:.4f}, {info['cm_y']:.4f}, {info['cm_z']:.4f}",
                f"X: {cx:.4f}", f"Y: {cy:.4f}", f"Z: {cz:.4f}",
                info['xmin'], info['xmax'], cx,
                info['ymin'], info['ymax'], cy,
                info['zmin'], info['zmax'], cz,
                bx, by, bz, xs, ys, zs,
                _tip_text_store, tol_text, None,
                no_update, no_update, no_update, no_update,
                {info['xmin']: f"{info['xmin']:.4f}", cx: f"{cx:.4f}", info['xmax']: f"{info['xmax']:.4f}"},
                {info['ymin']: f"{info['ymin']:.4f}", cy: f"{cy:.4f}", info['ymax']: f"{info['ymax']:.4f}"},
                {info['zmin']: f"{info['zmin']:.4f}", cz: f"{cz:.4f}", info['zmax']: f"{info['zmax']:.4f}"})

    # === TOL SLIDER ===
    if triggered_id == 'tol-slider':
        _tol_current = tol_val
        try:
            tip_points = find_tip_points(info['mesh'], tol=tol_val)
        except Exception:
            tip_points = []
        _tip_points_store = tip_points
        _tip_text_store = '\n'.join([f'[{len(tip_points)} tips found]'] +
                                     [f'tip{j+1}: ({t[0]:8.4f}, {t[1]:8.4f}, {t[2]:8.4f})' for j, t in enumerate(tip_points)])
        if x_val >= y_val and x_val >= z_val: axis, value = 'x', x_val
        elif y_val >= x_val and y_val >= z_val: axis, value = 'y', y_val
        else: axis, value = 'z', z_val
        data = extract_slice(info['mesh'], axis, value)
        fig2d = build_2d_figure(data, axis, 0, value, info['xmin'],info['xmax'],info['ymin'],info['ymax'],info['zmin'],info['zmax'])
        fig3d = build_3d_figure(info['mesh'], axis, value, tip_points=tip_points)
        if axis == 'x': bx, by, bz = 1, 0, 0; xs, ys, zs = btn_active(), btn_inactive(), btn_inactive()
        elif axis == 'y': bx, by, bz = 0, 1, 0; xs, ys, zs = btn_inactive(), btn_active(), btn_inactive()
        else: bx, by, bz = 0, 0, 1; xs, ys, zs = btn_inactive(), btn_inactive(), btn_active()
        tol_text = f"TOL: {_tol_current:.4f}m"
        return (fig2d, fig3d,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update,
                f"X: {x_val:.4f}", f"Y: {y_val:.4f}", f"Z: {z_val:.4f}",
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                bx, by, bz, xs, ys, zs,
                _tip_text_store, tol_text, None,
                no_update, no_update, no_update, no_update,
                {0.01: '0.01', _tol_current: f'{_tol_current:.4f}', _tol_max: f'{_tol_max:.4f}'},
                {info['xmin']: f"{info['xmin']:.4f}", cx: f"{cx:.4f}", info['xmax']: f"{info['xmax']:.4f}"},
                {info['ymin']: f"{info['ymin']:.4f}", cy: f"{cy:.4f}", info['ymax']: f"{info['ymax']:.4f}"},
                {info['zmin']: f"{info['zmin']:.4f}", cz: f"{cz:.4f}", info['zmax']: f"{info['zmax']:.4f}"})

    # === DEFAULT (slider value changes) ===
    return _ret_default()
