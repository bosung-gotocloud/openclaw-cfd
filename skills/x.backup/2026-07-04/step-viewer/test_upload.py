#!/usr/bin/env python3
import base64, json, urllib.request

STEP_FILE = "/home/bosung/WinD/0.cfd/1.AI-agent/07.MQ9-Reaper-salome/MQ9-reaper.stp"
FNAME = "MQ9-reaper.stp"

with open(STEP_FILE, "rb") as f:
    data = f.read()

b64 = base64.b64encode(data).decode()

# Dash 4.x format: inputs is a list of objects
payload = {
    "outputs": {
        "slice-2d.figure": {"type": "component", "id": "slice-2d", "property": "figure"},
        "slice-3d.figure": {"type": "component", "id": "slice-3d", "property": "figure"},
        "file-name.children": {"type": "component", "id": "file-name", "property": "children"},
    },
    "inputs": [
        {"id": {"type": "component", "id": "file-upload", "name": "file-upload"}, "property": "contents", "value": f"data:application/octet-stream;base64,{b64}"},
        {"id": {"type": "component", "id": "x-slider", "name": "x-slider"}, "property": "value", "value": 0.0},
        {"id": {"type": "component", "id": "y-slider", "name": "y-slider"}, "property": "value", "value": 0.0},
        {"id": {"type": "component", "id": "z-slider", "name": "z-slider"}, "property": "value", "value": 0.0},
        {"id": {"type": "component", "id": "axis-x", "name": "axis-x"}, "property": "n_clicks", "value": 1},
        {"id": {"type": "component", "id": "axis-y", "name": "axis-y"}, "property": "n_clicks", "value": 0},
        {"id": {"type": "component", "id": "axis-z", "name": "axis-z"}, "property": "n_clicks", "value": 0},
        {"id": {"type": "component", "id": "btn-find-tip", "name": "btn-find-tip"}, "property": "n_clicks", "value": 0},
        {"id": {"type": "component", "id": "btn-reset", "name": "btn-reset"}, "property": "n_clicks", "value": 0},
        {"id": {"type": "component", "id": "tol-slider", "name": "tol-slider"}, "property": "value", "value": 0.5},
    ],
    "state": [
        {"id": {"type": "component", "id": "file-upload", "name": "file-upload"}, "property": "filename", "value": FNAME},
    ],
    "callback": "slice-2d.figure|slice-3d.figure|file-name.children",
}

url = "http://127.0.0.1:8052/_dash-update-component"
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read().decode())
    print("STATUS: 200 OK")
    for k, v in result.items():
        if isinstance(v, dict) and "error" in v:
            print(f"  {k}: ERROR - {v['error']}")
        elif isinstance(v, dict) and "props" in v:
            print(f"  {k}: OK (props count={len(v['props'])})")
        else:
            print(f"  {k}: {str(v)[:200]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    # Extract traceback info
    import re
    tb_match = re.search(r'TypeError: ([^<]+)', body)
    if tb_match:
        print(f"HTTP {e.code}: TypeError: {tb_match.group(1)}")
    else:
        print(f"HTTP {e.code}: {body[:500]}")
except Exception as e:
    print(f"ERROR: {e}")
