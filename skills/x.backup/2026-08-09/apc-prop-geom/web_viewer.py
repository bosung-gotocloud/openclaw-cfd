import os
import pandas as pd
import plotly.graph_objects as go
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# Absolute base directory
BASE_DIR = "/home/bosung/.openclaw/workspace/skills/apc-prop-geom/test"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>APC Propeller 3D Viewer</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; background-color: #1e1e1e; color: white; }
        #header { background: #2d2d2d; padding: 15px 25px; display: flex; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); z-index: 10; }
        #controls { display: flex; gap: 15px; align-items: center; margin-left: auto; }
        #plot-container { flex: 1; position: relative; background: #1e1e1e; }
        #plot { width: 100%; height: 100%; }
        input[type="text"] { padding: 8px; width: 350px; border-radius: 4px; border: 1px solid #444; background: #3d3d3d; color: white; }
        button { padding: 8px 20px; cursor: pointer; background: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; transition: background 0.2s; }
        button:hover { background: #0056b3; }
        .status { font-size: 0.9em; color: #aaa; margin-left: 15px; }
    </style>
</head>
<body>
    <div id="header">
        <h3 style="margin:0">🦋 APC Propeller 3D Inspector</h3>
        <div id="controls">
            <span class="status" id="status">Ready</span>
            <input type="text" id="csvPath" placeholder="Filename (e.g. 10x4M-LH-PERF.csv)">
            <button onclick="loadPlot()">Visualize</button>
        </div>
    </div>
    <div id="plot-container">
        <div id="plot"></div>
    </div>

    <script>
        async function loadPlot() {
            const filename = document.getElementById('csvPath').value.trim();
            if (!filename) { alert('Please enter a filename'); return; }
            
            const statusEl = document.getElementById('status');
            statusEl.innerText = 'Loading...';
            
            try {
                const response = await fetch(`/plot?file=${encodeURIComponent(filename)}`);
                if (!response.ok) {
                    const err = await response.text();
                    throw new Error(err || 'File not found');
                }
                const data = await response.json();
                
                const layout = {
                    scene: {
                        xaxis: {title: 'X [m] (Axial/Shaft)', gridcolor: '#444', zerolinecolor: '#888', color: 'white'},
                        yaxis: {title: 'Y [m] (Span)', gridcolor: '#444', zerolinecolor: '#888', color: 'white'},
                        zaxis: {title: 'Z [m] (Chord)', gridcolor: '#444', zerolinecolor: '#888', color: 'white'},
                        aspectmode: 'data',
                        bgcolor: '#1e1e1e'
                    },
                    paper_bgcolor: '#1e1e1e',
                    plot_bgcolor: '#1e1e1e',
                    font: { color: 'white' },
                    margin: {l: 0, r: 0, b: 0, t: 0}
                };
                
                Plotly.newPlot('plot', data, layout, {responsive: true});
                statusEl.innerText = 'Success';
            } catch (e) {
                alert('Error: ' + e.message);
                statusEl.innerText = 'Error';
            }
        }

        window.onload = () => {
            document.getElementById('csvPath').value = '10x4M-LH-PERF.csv';
            loadPlot();
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/plot')
def get_plot():
    filename = request.args.get('file')
    if not filename:
        return "Missing filename", 400
    
    safe_filename = os.path.basename(filename)
    full_path = os.path.join(BASE_DIR, safe_filename)
    
    if not os.path.exists(full_path):
        return f"File not found: {full_path}", 404
    
    try:
        df = pd.read_csv(full_path)
        
        # Detect column names
        x_col = 'X' if 'X' in df.columns else 'x'
        y_col = 'Y' if 'Y' in df.columns else 'y'
        z_col = 'Z' if 'Z' in df.columns else 'z'
        
        # Get unique stations and blades
        station_col = 'r_over_R' if 'r_over_R' in df.columns else 'station_idx'
        blade_col = 'blade_idx' if 'blade_idx' in df.columns else None
        
        figures = []
        
        # Group by blade first
        if blade_col:
            blades = df[blade_col].unique()
        else:
            blades = [0]
            df = df.assign(blade_idx=0)
            blade_col = 'blade_idx'
        
        for blade in sorted(df[blade_col].unique()):
            df_blade = df[df[blade_col] == blade]
            
            # Group by station within each blade
            stations = df_blade[station_col].unique()
            stations.sort()
            
            for i, r_val in enumerate(stations):
                section = df_blade[df_blade[station_col] == r_val]
                
                # Color based on r/R
                ratio = i / max(1, len(stations)-1)
                color = f'rgb({int(255*ratio)}, {int(255*(1-abs(ratio-0.5)*2))}, {int(255*(1-ratio))})'
                
                figures.append({
                    'type': 'scatter3d',
                    'mode': 'lines',
                    'x': section[x_col].tolist(),
                    'y': section[y_col].tolist(),
                    'z': section[z_col].tolist(),
                    'line': {'color': color, 'width': 3},
                    'name': f'r/R={r_val:.4f}'
                })
        
        return jsonify(figures)
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8053, debug=False)
