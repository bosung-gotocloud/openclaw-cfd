#!/usr/bin/env python3
"""Rewrite main() VLM section in vlm-tip-detect.py with base64 + scaling."""
import shutil, py_compile

fpath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
shutil.copy('/home/bosung/.openclaw/workspace/skills/backups/2026-08-11b/vlm-tip-detect.py', fpath)

with open(fpath, 'r') as f:
    content = f.read()

# ========== 1. Replace get_vlm to use base64 + dynamic prompt ==========
old_get = '''def get_vlm(image_path, timeout_sec=60):
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        r = ollama.chat(model='qwen3.6:35b',
                        messages=[{"role":"user","content":VL_PROMPT,"images":[image_path]}],
                        stream=False)
        return r['message']['content']
    except Exception as e:
        print(f"    [VLM error] {type(e).__name__}: {e}")
        return None'''

new_get = '''def get_vlm(image_path, timeout_sec=60):
    """Send image as base64 to VLM. VLM returns JSON with image_width, image_height, tips."""
    if not HAS_OLLAMA or not os.path.exists(image_path): return None
    try:
        # Convert PNG to base64
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        # Prompt: ask VLM to also return the image dimensions it received
        prompt = ("Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. "
                  "Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}")
        r = ollama.chat(
            model='qwen3.6:35b',
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "image": b64
                }
            ],
            stream=False
        )
        return r['message']['content']
    except Exception as e:
        print(f"    [VLM error] {type(e).__name__}: {e}")
        return None'''

content = content.replace(old_get, new_get)

# ========== 2. Replace parse_vlm to return (tips, vlm_w, vlm_h) ==========
old_parse_sig = '''def parse_vlm(raw):
    """Parse VLM response: returns list of tip candidate bboxes.
    Accepts {tips:[{tip_id,x1,y1,x2,y2}]} and {bbox_2d:[minX,minY,maxX,maxY]} formats."""'''
new_parse_sig = '''def parse_vlm(raw):
    """Parse VLM response: returns (tips_list, vlm_image_width, vlm_image_height).
    VLM must return: {image_width: W, image_height: H, tips: [{tip_id, x1, y1, x2, y2}]}.
    x1,y1 = top-left, x2,y2 = bottom-right (from top-left of the image the VLM received).
    If VLM image size differs from actual image, caller should scale: actual/returned.
    """'''
content = content.replace(old_parse_sig, new_parse_sig)

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
    # Find JSON array [ or object {
    bracket_start = t.find('[')
    brace_start = t.find('{')
    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):
        start = bracket_start
    elif brace_start >= 0:
        start = brace_start
    else:
        return [], 0, 0
    # Find matching end bracket
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
    # Extract VLM-reported image dimensions
    vlm_w = int(d.get('image_width', 0))
    vlm_h = int(d.get('image_height', 0))
    # Normalize to list
    if isinstance(d, dict):
        if 'tips' in d: items = d['tips']
        else: items = [d]
    elif isinstance(d, list):
        items = d
    else:
        return [], vlm_w, vlm_h
    if not isinstance(items, list): return [], vlm_w, vlm_h
    res = []
    for tp in items:
        tid = tp.get('tip_id', tp.get('id'))
        x1 = tp.get('x1')
        y1 = tp.get('y1')
        x2 = tp.get('x2')
        y2 = tp.get('y2')
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
        if x1 is not None: x1 = float(x1)
        if y1 is not None: y1 = float(y1)
        if x2 is not None: x2 = float(x2)
        if y2 is not None: y2 = float(y2)
        res.append({'tip_id': tid, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
    return res, vlm_w, vlm_h'''

content = content.replace(old_parse_body, new_parse_body)

# ========== 3. Replace main VLM section ==========
# The section we want to replace: from "raw = get_vlm(op)" to the print(f"  [{vn}]") before next iteration
old_main_vlm = '''        raw = get_vlm(op)
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
        
        # pixel -> CAD(mm): 직결 변환 (snap 없음)
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

new_main_vlm = '''        raw = get_vlm(op)
        if raw:
            print(f"  VLM raw: {raw[:300]}...")
        
        if raw:
            tips_vlm, vlm_w, vlm_h = parse_vlm(raw)
        else:
            tips_vlm = []; vlm_w = 0; vlm_h = 0
        
        if tips_vlm:
            print(f"  VLM: {len(tips_vlm)} tip(s), reported image: {vlm_w}x{vlm_h}")
            # Scale VLM bbox from VLM's image size to actual image size
            actual_w = 1100; actual_h = 1100  # our rendering produces 1100x1100
            scale_x = actual_w / vlm_w if vlm_w > 0 else 1.0
            scale_y = actual_h / vlm_h if vlm_h > 0 else 1.0
            tips = []
            for tip in tips_vlm:
                # Scale VLM's bbox to actual image pixels
                bx1 = tip['x1'] * scale_x if tip['x1'] is not None else None
                by1 = tip['y1'] * scale_y if tip['y1'] is not None else None
                bx2 = tip['x2'] * scale_x if tip['x2'] is not None else None
                by2 = tip['y2'] * scale_y if tip['y2'] is not None else None
                tx1 = int(bx1) if bx1 is not None else 0
                ty1 = int(by1) if by1 is not None else 0
                tx2 = int(bx2) if bx2 is not None else 0
                ty2 = int(by2) if by2 is not None else 0
                
                # Draw green bbox on actual image
                annot_path = op.replace('.png', '_annotated.png')
                try:
                    from PIL import Image, ImageDraw
                    img_pil = Image.open(op).convert("RGB")
                    draw = ImageDraw.Draw(img_pil)
                    draw.rectangle([tx1, ty1, tx2, ty2], outline="green", width=2)
                    draw.text((tx1+2, ty1+2), "tip" + str(tip['tip_id']), fill="green")
                    img_pil.save(annot_path)
                    print(f"    annotated PNG saved: {annot_path}")
                except Exception as e:
                    print(f"  [annotate error] {e}")
                
                # bbox center -> CAD(mm) using di's projection
                cx = (tx1 + tx2) / 2
                cy = (ty1 + ty2) / 2
                CAD_h_mm = (cx - di['offset_x']) / di['fit_scale']
                CAD_v_mm = (img_size - cy - di['offset_y']) / di['fit_scale']
                tips.append(np.array([CAD_h_mm, CAD_v_mm, 0.0]))
                print(f"  tip#{tip['tip_id']}: VLM[{int(tip['x1'])},{int(tip['y1'])}]->[{int(tip['x2'])},{int(tip['y2'])}] "
                      f"scale {scale_x:.3f}x{scale_y:.3f} -> pixel({tx1},{ty1})->({tx2},{ty2}) -> CADmm({CAD_h_mm:.1f},{CAD_v_mm:.1f})")
            tips_by_view[vn] = tips
            print(f"  [{vn}] {len(tips)} tip(s)")
        else:
            tips_by_view[vn] = []
            print(f"  [{vn}] VLM: none")
        print()'''

content = content.replace(old_main_vlm, new_main_vlm)

# Add base64 import if not present
if 'import base64' not in content:
    content = content.replace('import argparse, json, os, sys, numpy as np, cv2, tempfile',
                              'import argparse, json, os, sys, numpy as np, cv2, tempfile, base64')

with open(fpath, 'w') as f:
    f.write(content)

py_compile.compile(fpath, doraise=True)
print("All rewritten. Syntax OK.")
