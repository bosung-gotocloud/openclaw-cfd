#!/usr/bin/env python3
"""Fix vlm-tip-detect.py: get_vlm, parse_vlm, and main VLM section."""
import re

filepath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
with open(filepath, 'r') as f:
    content = f.read()

# --- 1. Replace get_vlm ---
old_get_vlm = r'''def get_vlm\(image_path, timeout_sec=60\):
    if not HAS_OLLAMA or not os\.path\.exists\(image_path\): return None
    try:
        r = ollama\.chat\(model='qwen3\.6:35b',
                        messages=\[\{"role":"user","content":VL_PROMPT,"images":\[image_path\]\}\],
                        stream=False\)
        return r\['message'\]\['content'\]
    except Exception as e:
        print\(f"    \[VLM error\] \{type\(e\).__name__\}: \{e\}"\)
        return None'''

new_get_vlm = """def get_vlm(image_path, timeout_sec=60):
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(image_path)
        w, h = pil_img.size
        prompt = (
            "Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. "
            "Return JSON array only.\\n\\n"
            "Image size: {}x{} pixels.\\n\\n"
            "Format: {{\\\"image_width\\\": {}, \\\"image_height\\\": {}, "
            "\\\"tips\\\":[{{\\\"tip_id\\\": N, \\\"x1\\\": x1, \\\"y1\\\": y1, \\\"x2\\\": x2, \\\"y2\\\": y2}}]}}\\n"
            "- image_width, image_height: actual pixel dimensions ({}x{})\\n"
            "- tip_id: unique integer starting from 1\\n"
            "- x1, y1: top-left corner of tip bbox (pixel from top-left)\\n"
            "- x2, y2: bottom-right corner of tip bbox (pixel from top-left)\\n"
            "- Return ONLY the JSON array, no backticks, no markdown."
            .format(w, h, w, h, w, h)
        )
        r = ollama.chat(model='qwen3.6:35b',
                        messages=[{"role":"user","content":prompt,"images":[image_path]}],
                        stream=False)
        return r['message']['content']
    except Exception as e:
        print(f"    [VLM error] {type(e).__name__}: {e}")
        return None"""

content = re.sub(old_get_vlm, new_get_vlm, content)

# --- 2. Replace parse_vlm ---
old_parse_start = '''def parse_vlm(raw):
    """Parse VLM response: returns list of tip candidate bboxes.
    Accepts {tips:[{tip_id,x1,y1,x2,y2}]} and {bbox_2d:[minX,minY,maxX,maxY]} formats."""'''

new_parse_start = '''def parse_vlm(raw):
    """Parse VLM response: returns (tips_list, image_width, image_height)."""'''

content = content.replace(old_parse_start, new_parse_start)

# Replace parse_vlm body - find and replace from "if not raw" to "return res"
old_parse_body = '''    if not raw: return []
    t = raw.strip()
    # Remove markdown code blocks
    if '```' in t:
        t = t.split('```')[1]
        if '```' in t:
            t = t.split('```')[0]
        t = t.strip()
    # Find JSON array [ or object {
    bracket_start = t.find('[')
    brace_start = t.find('{')
    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):
        start = bracket_start
    elif brace_start >= 0:
        start = brace_start
    else:
        return []
    # Find matching end bracket
    bracket_end = t.rfind(']')
    brace_end = t.rfind('}')
    if bracket_end >= 0 and (brace_end < 0 or bracket_end >= brace_end):
        end = bracket_end
    elif brace_end >= 0:
        end = brace_end
    else:
        return []
    if start >= end: return []
    t = t[start:end+1]
    try:
        d = json.loads(t)
    except:
        return []
    # Normalize to list
    if isinstance(d, dict):
        if 'tips' in d: items = d['tips']
        elif 'bbox_2d' in d: items = [d]
        else: items = [d]
    elif isinstance(d, list):
        items = d
    else:
        return []
    if not isinstance(items, list): return []
    res = []
    for tp in items:
        tid = tp.get('tip_id', tp.get('id'))
        x1 = tp.get('x1')
        y1 = tp.get('y1')
        x2 = tp.get('x2')
        y2 = tp.get('y2')
        # Handle x, y format (single pixel point from VLM)
        x = tp.get('x')
        y = tp.get('y')
        if x is not None and y is not None and x1 is None:
            # {tip_id, x, y} -> {tip_id, x1, y1, x2, y2} as point bbox
            x1 = y1 = x2 = y2 = None
            if x1 is None: x1 = x
            if y1 is None: y1 = y
            if x2 is None: x2 = x
            if y2 is None: y2 = y
        # Handle bbox_2d: [minX, minY, maxX, maxY]
        bb2d = tp.get('bbox_2d', tp.get('box_2d'))
        if bb2d and len(bb2d) == 4 and x1 is None:
            bbox = bb2d
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
            tid = tp.get('tip_id', tp.get('id', len(res) + 1))
        try:
            if tid is not None:
                tid = int(tid)
            else:
                tid = len(res) + 1
        except:
            tid = len(res) + 1
        res.append({'tip_id': tid, 'x1': float(x1), 'y1': float(y1), 'x2': float(x2), 'y2': float(y2)})
    return res'''

new_parse_body = '''    if not raw: return [], 0, 0
    t = raw.strip()
    # Remove markdown code blocks
    if '```' in t:
        t = t.split('```')[1]
        if '```' in t:
            t = t.split('```')[0]
        t = t.strip()
    # Find JSON
    bracket_start = t.find('[')
    brace_start = t.find('{')
    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):
        start = bracket_start
    elif brace_start >= 0:
        start = brace_start
    else:
        return [], 0, 0
    bracket_end = t.rfind(']')
    brace_end = t.rfind('}')
    if bracket_end >= 0 and (brace_end < 0 or bracket_end >= brace_end):
        end = bracket_end
    elif brace_end >= 0:
        end = brace_end
    else:
        return [], 0, 0
    if start >= end: return [], 0, 0
    t = t[start:end+1]
    try:
        d = json.loads(t)
    except:
        return [], 0, 0
    # Extract image dimensions
    img_w = int(d.get('image_width', 0))
    img_h = int(d.get('image_height', 0))
    # Normalize to list
    if isinstance(d, dict):
        if 'tips' in d: items = d['tips']
        else: items = [d]
    elif isinstance(d, list):
        items = d
    else:
        return [], img_w, img_h
    if not isinstance(items, list): return [], img_w, img_h
    res = []
    for tp in items:
        tid = tp.get('tip_id', tp.get('id'))
        x1 = tp.get('x1')
        y1 = tp.get('y1')
        x2 = tp.get('x2')
        y2 = tp.get('y2')
        try:
            if tid is not None:
                tid = int(tid)
            else:
                tid = len(res) + 1
        except:
            tid = len(res) + 1
        if x1 is not None: x1 = float(x1)
        if y1 is not None: y1 = float(y1)
        if x2 is not None: x2 = float(x2)
        if y2 is not None: y2 = float(y2)
        res.append({'tip_id': tid, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
    return res, img_w, img_h'''

content = content.replace(old_parse_body, new_parse_body)

# --- 3. Replace main VLM section ---
old_vlm_main = '''        raw = get_vlm(op)
        if raw:
            print(f"  VLM raw: {raw[:200]}...")
            tips_vlm = parse_vlm(raw)
            print(f"  VLM: {len(tips_vlm)} tip(s)")
            # Draw VLM tips on the image (green dots)
            if tips_vlm:
                annot_path = op.replace('.png', '_annotated.png')
                try:
                    from PIL import Image, ImageDraw
                    img_pil = Image.open(op).convert("RGB")
                    draw = ImageDraw.Draw(img_pil)
                    width, height = img_pil.size
                    for tip in tips_vlm:
                        tx, ty = int(tip['x']), int(tip['y'])
                        draw.ellipse([tx-8, ty-8, tx+8, ty+8], outline="green", width=2)
                        draw.text((tx+10, ty), f"tip{tip['tip_id']}", fill="green")
                    img_pil.save(annot_path)
                    print(f"    annotated PNG saved: {annot_path}")
                except Exception as e:
                    print(f"  [annotate error] {e}")
        else:
            tips_vlm = []; print(f"  VLM: none")
        
        # pixel -> CAD(mm): direct conversion
        tips = []
        for tp in tips_vlm:
            tid = tp['tip_id']
            px = tp['x']
            py = tp['y']
            CAD_h_mm = (px - di['offset_x']) / di['fit_scale']
            CAD_v_mm = (img_size - py - di['offset_y']) / di['fit_scale']
            tips.append(np.array([CAD_h_mm, CAD_v_mm, 0.0]))  # placeholder z
            print(f"  tip#{tid}: pixel({px:.0f},{py:.0f}) -> CADmm({CAD_h_mm:.1f},{CAD_v_mm:.1f})")
        print(f"  [{vn}] {len(tips)} snapped tip(s)\\n")'''

new_vlm_main = '''        raw = get_vlm(op)
        if raw:
            print(f"  VLM raw: {raw[:300]}...")
            tips_vlm, vlm_img_w, vlm_img_h = parse_vlm(raw)
            print(f"  VLM: {len(tips_vlm)} tip(s), reported size: {vlm_img_w}x{vlm_img_h}")
            # Draw VLM tips on the image (green bboxes)
            if tips_vlm:
                annot_path = op.replace('.png', '_annotated.png')
                try:
                    from PIL import Image, ImageDraw
                    img_pil = Image.open(op).convert("RGB")
                    draw = ImageDraw.Draw(img_pil)
                    width, height = img_pil.size
                    for tip in tips_vlm:
                        tx1, ty1 = int(tip['x1']), int(tip['y1'])
                        tx2, ty2 = int(tip['x2']), int(tip['y2'])
                        draw.rectangle([tx1, ty1, tx2, ty2], outline="green", width=2)
                        draw.text((tx1+2, ty1+2), f"tip{tip['tip_id']}", fill="green")
                    img_pil.save(annot_path)
                    print(f"    annotated PNG saved: {annot_path}")
                except Exception as e:
                    print(f"  [annotate error] {e}")
        else:
            tips_vlm = []; vlm_img_w = 0; vlm_img_h = 0; print(f"  VLM: none")
        
        # pixel -> CAD(mm): VLM reported size -> actual image size scaling correction
        tips = []
        for tp in tips_vlm:
            tid = tp['tip_id']
            scale_x = scale_y = 1.0
            if vlm_img_w > 0 and vlm_img_h > 0:
                actual_w = width
                actual_h = height
                scale_x = actual_w / vlm_img_w
                scale_y = actual_h / vlm_img_h
            # bbox center -> CAD coordinates
            px1 = tp['x1'] * scale_x
            py1 = tp['y1'] * scale_y
            px2 = tp['x2'] * scale_x
            py2 = tp['y2'] * scale_y
            px_center = (px1 + px2) / 2
            py_center = (py1 + py2) / 2
            CAD_h_mm = (px_center - di['offset_x']) / di['fit_scale']
            CAD_v_mm = (img_size - py_center - di['offset_y']) / di['fit_scale']
            tips.append(np.array([CAD_h_mm, CAD_v_mm, 0.0]))
            print(f"  tip#{tid}: pixel({int(px1)},{int(py1)})->({int(px2)},{int(py2)}) [scale {scale_x:.2f}x{scale_y:.2f}] -> CADmm({CAD_h_mm:.1f},{CAD_v_mm:.1f})")
        print(f"  [{vn}] {len(tips)} snapped tip(s)\\n")'''

content = content.replace(old_vlm_main, new_vlm_main)

with open(filepath, 'w') as f:
    f.write(content)

print("Done. All 3 sections updated.")
