#!/usr/bin/env python3
"""Apply all VLM fixes to vlm-tip-detect.py"""
import shutil, py_compile

fpath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
shutil.copy('/home/bosung/.openclaw/workspace/skills/backups/2026-08-11b/vlm-tip-detect.py', fpath)

with open(fpath, 'r') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # === get_vlm ===
    if line.strip().startswith('def get_vlm('):
        out.append('def get_vlm(image_path, timeout_sec=60):\n')
        out.append('    if not HAS_OLLAMA or not os.path.exists(image_path): return None\n')
        out.append('    try:\n')
        out.append('        from PIL import Image as PILImage\n')
        out.append('        pil_img = PILImage.open(image_path)\n')
        out.append('        w, h = pil_img.size\n')
        out.append('        NL = chr(10)\n')
        out.append("        json_template = '{\"image_width\": W, \"image_height\": H, \"tips\": [{\"tip_id\": N, \"x1\": x1, \"y1\": y1, \"x2\": x2, \"y2\": y2}]}'\n")
        out.append('        prompt = "Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. Return JSON array only." + NL + NL\n')
        out.append('        prompt += "Image size: " + str(w) + "x" + str(h) + " pixels." + NL + NL\n')
        out.append('        prompt += "Format: " + json_template.replace("W", str(w)).replace("H", str(h)) + NL\n')
        out.append('        prompt += "- image_width, image_height: actual pixel dimensions (" + str(w) + "x" + str(h) + ")" + NL\n')
        out.append('        prompt += "- tip_id: unique integer starting from 1" + NL\n')
        out.append('        prompt += "- x1, y1: top-left corner of tip bbox (pixel from top-left)" + NL\n')
        out.append('        prompt += "- x2, y2: bottom-right corner of tip bbox (pixel from top-left)" + NL\n')
        out.append('        prompt += "- Return ONLY the JSON array, no backticks, no markdown."\n')
        out.append("        r = ollama.chat(model='qwen3.6:35b',\n")
        out.append('                        messages=[{"role":"user","content":prompt,"images":[image_path]}],\n')
        out.append('                        stream=False)\n')
        out.append("        return r['message']['content']\n")
        out.append('    except Exception as e:\n')
        out.append('        print(f"    [VLM error] {type(e).__name__}: {e}")\n')
        out.append('        return None\n')
        i += 1
        while i < len(lines) and not (lines[i].startswith('def ') and 'get_vlm' not in lines[i]):
            i += 1
        continue
    
    # === parse_vlm ===
    if line.strip().startswith('def parse_vlm('):
        out.append('def parse_vlm(raw):\n')
        out.append('    """Parse VLM response: returns (tips_list, image_width, image_height)."""\n')
        out.append('    if not raw: return [], 0, 0\n')
        out.append('    t = raw.strip()\n')
        out.append("    if '```' in t:\n")
        out.append("        t = t.split('```')[1]\n")
        out.append("        if '```' in t:\n")
        out.append("            t = t.split('```')[0]\n")
        out.append("        t = t.strip()\n")
        out.append("    bracket_start = t.find('[')\n")
        out.append("    brace_start = t.find('{')\n")
        out.append('    if bracket_start >= 0 and (brace_start < 0 or bracket_start <= brace_start):\n')
        out.append('        start = bracket_start\n')
        out.append('    elif brace_start >= 0:\n')
        out.append('        start = brace_start\n')
        out.append('    else:\n')
        out.append('        return [], 0, 0\n')
        out.append("    bracket_end = t.rfind(']')\n")
        out.append("    brace_end = t.rfind('}')\n")
        out.append('    if bracket_end >= 0 and (brace_end < 0 or bracket_end >= brace_end):\n')
        out.append('        end = bracket_end\n')
        out.append('    elif brace_end >= 0:\n')
        out.append('        end = brace_end\n')
        out.append('    else:\n')
        out.append('        return [], 0, 0\n')
        out.append('    if start >= end: return [], 0, 0\n')
        out.append('    t = t[start:end+1]\n')
        out.append('    try:\n')
        out.append('        d = json.loads(t)\n')
        out.append('    except:\n')
        out.append('        return [], 0, 0\n')
        out.append("    img_w = int(d.get('image_width', 0))\n")
        out.append("    img_h = int(d.get('image_height', 0))\n")
        out.append('    if isinstance(d, dict):\n')
        out.append("        if 'tips' in d: items = d['tips']\n")
        out.append('        else: items = [d]\n')
        out.append('    elif isinstance(d, list):\n')
        out.append('        items = d\n')
        out.append('    else:\n')
        out.append('        return [], img_w, img_h\n')
        out.append('    if not isinstance(items, list): return [], img_w, img_h\n')
        out.append('    res = []\n')
        out.append("    for tp in items:\n")
        out.append("        tid = tp.get('tip_id', tp.get('id'))\n")
        out.append("        x1 = tp.get('x1')\n")
        out.append("        y1 = tp.get('y1')\n")
        out.append("        x2 = tp.get('x2')\n")
        out.append("        y2 = tp.get('y2')\n")
        out.append('        try:\n')
        out.append('            if tid is not None:\n')
        out.append('                tid = int(tid)\n')
        out.append('            else:\n')
        out.append('                tid = len(res) + 1\n')
        out.append('        except:\n')
        out.append('            tid = len(res) + 1\n')
        out.append('        if x1 is not None: x1 = float(x1)\n')
        out.append('        if y1 is not None: y1 = float(y1)\n')
        out.append('        if x2 is not None: x2 = float(x2)\n')
        out.append('        if y2 is not None: y2 = float(y2)\n')
        out.append("        res.append({'tip_id': tid, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})\n")
        out.append('    return res, img_w, img_h\n')
        i += 1
        while i < len(lines):
            if lines[i].startswith('def ') or lines[i].startswith('# ---') or lines[i].startswith('# ---'):
                break
            i += 1
        continue
    
    # === Main VLM section ===
    if line.strip() == 'raw = get_vlm(op)':
        out.append('        raw = get_vlm(op)\n')
        out.append('        if raw:\n')
        out.append('            print(f"  VLM raw: {raw[:300]}...")\n')
        out.append('            tips_vlm, vlm_img_w, vlm_img_h = parse_vlm(raw)\n')
        out.append('            print(f"  VLM: {len(tips_vlm)} tip(s), reported size: {vlm_img_w}x{vlm_img_h}")\n')
        out.append('            # Draw VLM tips on the image (green bboxes)\n')
        out.append('            if tips_vlm:\n')
        out.append("                annot_path = op.replace('.png', '_annotated.png')\n")
        out.append('                try:\n')
        out.append('                    from PIL import Image, ImageDraw\n')
        out.append('                    img_pil = Image.open(op).convert("RGB")\n')
        out.append('                    draw = ImageDraw.Draw(img_pil)\n')
        out.append('                    width, height = img_pil.size\n')
        out.append('                    for tip in tips_vlm:\n')
        out.append("                        tx1, ty1 = int(tip['x1']), int(tip['y1'])\n")
        out.append("                        tx2, ty2 = int(tip['x2']), int(tip['y2'])\n")
        out.append('                        draw.rectangle([tx1, ty1, tx2, ty2], outline="green", width=2)\n')
        out.append("                        draw.text((tx1+2, ty1+2), f\"tip{tip['tip_id']}\", fill=\"green\")\n")
        out.append('                    img_pil.save(annot_path)\n')
        out.append('                    print(f"    annotated PNG saved: {annot_path}")\n')
        out.append('                except Exception as e:\n')
        out.append('                    print(f"  [annotate error] {e}")\n')
        out.append('        else:\n')
        out.append('            tips_vlm = []; vlm_img_w = 0; vlm_img_h = 0; print(f"  VLM: none")\n')
        out.append('\n')
        out.append('        # pixel -> CAD(mm): VLM reported size -> actual image size scaling\n')
        out.append('        tips = []\n')
        out.append('        for tp in tips_vlm:\n')
        out.append("            tid = tp['tip_id']\n")
        out.append('            scale_x = scale_y = 1.0\n')
        out.append('            if vlm_img_w > 0 and vlm_img_h > 0:\n')
        out.append('                scale_x = width / vlm_img_w\n')
        out.append('                scale_y = height / vlm_img_h\n')
        out.append('            px1 = tp[\'x1\'] * scale_x\n')
        out.append('            py1 = tp[\'y1\'] * scale_y\n')
        out.append('            px2 = tp[\'x2\'] * scale_x\n')
        out.append('            py2 = tp[\'y2\'] * scale_y\n')
        out.append('            px_center = (px1 + px2) / 2\n')
        out.append('            py_center = (py1 + py2) / 2\n')
        out.append("            CAD_h_mm = (px_center - di['offset_x']) / di['fit_scale']\n")
        out.append("            CAD_v_mm = (img_size - py_center - di['offset_y']) / di['fit_scale']\n")
        out.append('            tips.append(np.array([CAD_h_mm, CAD_v_mm, 0.0]))\n')
        out.append('            print(f"  tip#{tid}: pixel({int(px1)},{int(py1)})->({int(px2)},{int(py2)}) [scale {scale_x:.2f}x{scale_y:.2f}] -> CADmm({CAD_h_mm:.1f},{CAD_v_mm:.1f})")\n')
        out.append("        print(f\"  [{vn}] {len(tips)} snapped tip(s)\\n\")\n")
        i += 1
        # Skip old VLM lines in main
        while i < len(lines):
            l = lines[i].strip()
            if l == '':
                # Check if next non-empty line is not VLM-related
                j = i + 1
                while j < len(lines) and lines[j].strip() == '':
                    j += 1
                if j < len(lines) and not lines[j].strip().startswith('if not any'):
                    i = j
                    break
                i += 1
                break
            if 'No tips detected' in l or l.startswith('if not any'):
                break
            if not any(kw in l for kw in ['raw = get_vlm', 'tips_vlm = parse_vlm', 'VLM raw', 
                                            'VLM:', 'annot_path', 'print(f"  VLM', 'print(f"    annotated',
                                            'print(f"  [annotate', 'tips = []', 'for tp in tips_vlm',
                                            'tip#', 'snapped tip']):
                break
            i += 1
        continue
    
    out.append(line)
    i += 1

with open(fpath, 'w') as f:
    f.writelines(out)

py_compile.compile(fpath, doraise=True)
print("All fixes applied. Syntax OK.")
