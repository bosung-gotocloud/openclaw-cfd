#!/usr/bin/env python3
"""Apply all VLM + CAD features to vlm-tip-detect.py."""
import shutil

src = '/home/bosung/.openclaw/workspace/skills/backups/2026-08-11b/vlm-tip-detect.py'
dst = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
shutil.copy(src, dst)

with open(dst, 'r') as f:
    lines = f.readlines()

out = []
for i, line in enumerate(lines):
    s = line.strip()
    
    # === 1. base64 import ===
    if s == 'import argparse, json, os, sys, numpy as np, cv2, tempfile':
        out.append('import argparse, json, os, sys, numpy as np, cv2, tempfile, base64\n')
        continue
    
    # === 2. get_vlm replace ===
    if s == 'def get_vlm(image_path, timeout_sec=60):':
        out.append('def get_vlm(image_path, timeout_sec=60):\n')
        out.append('    if not HAS_OLLAMA or not os.path.exists(image_path): return None\n')
        out.append('    try:\n')
        out.append('        with open(image_path, "rb") as f:\n')
        out.append('            b64 = base64.b64encode(f.read()).decode("utf-8")\n')
        out.append('        prompt = ("Find ONLY wing tips, tail tips, and sharp corner points (extreme pointed ends) in this image. "\n')
        out.append('                  "Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}")\n')
        out.append('        r = ollama.chat(model="qwen3.6:35b",\n')
        out.append('                        messages=[{"role": "user", "content": prompt, "images": [b64]}],\n')
        out.append('                        stream=False)\n')
        out.append('        return r["message"]["content"]\n')
        out.append('    except Exception as e:\n')
        out.append('        print("    [VLM error] " + str(e))\n')
        out.append('        return None\n')
        # Skip original get_vlm body
        j = i + 1
        while j < len(lines) and not (lines[j].strip() == '' and j > i + 3):
            if lines[j].strip().startswith('def ') or (lines[j].strip() == '' and j > i + 3):
                break
            j += 1
        # Skip to next function or blank line
        while j < len(lines) and lines[j].strip() != '':
            j += 1
        out.append('\n')
        continue
    
    # === 3. parse_vlm replace ===
    if s == 'def parse_vlm(raw):':
        out.append('def parse_vlm(raw):\n')
        out.append('    if not raw: return [], 0, 0\n')
        out.append('    t = raw.strip()\n')
        out.append('    if "`" in t:\n')
        out.append('        t = t.split("`")[1]\n')
        out.append('        if "`" in t: t = t.split("`")[0]\n')
        out.append('        t = t.strip()\n')
        out.append('    bs = t.find("["); brs = t.find("{")\n')
        out.append('    if bs >= 0 and (brs < 0 or bs <= brs): start = bs\n')
        out.append('    elif brs >= 0: start = brs\n')
        out.append('    else: return [], 0, 0\n')
        out.append('    be = t.rfind("]"); bre = t.rfind("}")\n')
        out.append('    if be >= 0 and (bre < 0 or be >= bre): end = be\n')
        out.append('    elif bre >= 0: end = bre\n')
        out.append('    else: return [], 0, 0\n')
        out.append('    if start >= end: return [], 0, 0\n')
        out.append('    t = t[start:end+1]\n')
        out.append('    try: d = json.loads(t)\n')
        out.append('    except: return [], 0, 0\n')
        out.append('    vlm_w = int(d.get("image_width", 0))\n')
        out.append('    vlm_h = int(d.get("image_height", 0))\n')
        out.append('    if isinstance(d, dict):\n')
        out.append('        items = d["tips"] if "tips" in d else []\n')
        out.append('    elif isinstance(d, list): items = d\n')
        out.append('    else: return [], vlm_w, vlm_h\n')
        out.append('    if not isinstance(items, list): return [], vlm_w, vlm_h\n')
        out.append('    res = []\n')
        out.append('    for tp in items:\n')
        out.append('        if not isinstance(tp, dict): continue\n')
        out.append('        tid = tp.get("tip_id", tp.get("id"))\n')
        out.append('        x1 = tp.get("x1"); y1 = tp.get("y1")\n')
        out.append('        x2 = tp.get("x2"); y2 = tp.get("y2")\n')
        out.append('        bb2d = tp.get("bbox_2d", tp.get("box_2d"))\n')
        out.append('        if bb2d and len(bb2d) == 4 and x1 is None:\n')
        out.append('            x1, y1, x2, y2 = bb2d[0], bb2d[1], bb2d[2], bb2d[3]\n')
        out.append('        try: tid = int(tid) if tid is not None else len(res) + 1\n')
        out.append('        except: tid = len(res) + 1\n')
        out.append('        if x1 is not None: x1 = float(x1)\n')
        out.append('        if y1 is not None: y1 = float(y1)\n')
        out.append('        if x2 is not None: x2 = float(x2)\n')
        out.append('        if y2 is not None: y2 = float(y2)\n')
        out.append('        res.append({"tip_id": tid, "x1": x1, "y1": y1, "x2": x2, "y2": y2})\n')
        out.append('    return res, vlm_w, vlm_h\n')
        out.append('\n')
        # Skip original parse_vlm body
        j = i + 1
        while j < len(lines) and lines[j].strip() != '':
            j += 1
        out.append('\n')
        continue
    
    # === 4. Insert dedup_tips + find_tips_in_bbox before triangulate ===
    if s == 'def triangulate(tips_by_view, verts_mm):':
        dedup = '''
def find_tips_in_bbox(edges_3d, view_name, bbox_px, di, bbox_mm, img_size=1100):
    """VLM bbox 중심을 CAD로 변환하고 snap_to_edges로 정밀 tip 찾기"""
    cx_px = (bbox_px["x0"] + bbox_px["x1"]) / 2
    cy_px = (bbox_px["y0"] + bbox_px["y1"]) / 2
    cad_h = (cx_px - di["offset_x"]) / di["fit_scale"]
    cad_v = (img_size - cy_px - di["offset_y"]) / di["fit_scale"]
    snapped = snap_to_edges(edges_3d, view_name, cad_h, cad_v, bbox_mm, tol=0.1)
    if snapped is not None:
        return np.array([snapped[0], snapped[1], snapped[2]])
    return np.array([cad_h, cad_v, 0.0])

def dedup_tips(tips_list, tol=50.0):
    """Y와 Z가 tol内인 tip들 그룹핑 -> 각 그룹에서 최대 X 선택."""
    if not tips_list:
        return []
    groups = []
    for tip in tips_list:
        placed = False
        for g in groups:
            if abs(tip[1] - g["ref"][1]) < tol and abs(tip[2] - g["ref"][2]) < tol:
                g["tips"].append(tip)
                placed = True
                break
        if not placed:
            groups.append({"ref": tip, "tips": [tip]})
    result = []
    for g in groups:
        best = max(g["tips"], key=lambda t: t[0])
        is_dup = any(np.linalg.norm(best - e) < tol for e in result)
        if not is_dup:
            result.append(best)
    return result


'''
        out.append(dedup)
        out.append(line)
        continue
    
    # === 5. Replace main VLM section ===
    if s == 'raw = get_vlm(op)':
        out.append('        raw = get_vlm(op)\n')
        out.append('        if raw:\n')
        out.append('            tips_vlm, vlm_w, vlm_h = parse_vlm(raw)\n')
        out.append('        else:\n')
        out.append('            tips_vlm = []; vlm_w = 0; vlm_h = 0\n')
        out.append('        print("  [" + vn + "] VLM: " + str(len(tips_vlm)) + " tips")\n')
        out.append('        if tips_vlm:\n')
        out.append('            aw = 1100; ah = 1100\n')
        out.append('            sx = aw / vlm_w if vlm_w > 0 else 1.0\n')
        out.append('            sy = ah / vlm_h if vlm_h > 0 else 1.0\n')
        out.append('            tips = []\n')
        out.append('            for tip in tips_vlm:\n')
        out.append('                bx1 = tip["x1"] * sx if tip["x1"] is not None else 0\n')
        out.append('                by1 = tip["y1"] * sy if tip["y1"] is not None else 0\n')
        out.append('                bx2 = tip["x2"] * sx if tip["x2"] is not None else 0\n')
        out.append('                by2 = tip["y2"] * sy if tip["y2"] is not None else 0\n')
        out.append('                tx1 = min(int(bx1), int(bx2))\n')
        out.append('                ty1 = min(int(by1), int(by2))\n')
        out.append('                tx2 = max(int(bx1), int(bx2))\n')
        out.append('                ty2 = max(int(by1), int(by2))\n')
        out.append('                bbox_px = {"x0": tx1, "x1": tx2, "y0": ty1, "y1": ty2}\n')
        out.append('                refined_tip = find_tips_in_bbox(edges, vn, bbox_px, di, bbox_mm, img_size)\n')
        out.append('                ref_cx = int(round((refined_tip[0] - di["offset_x"]) / di["fit_scale"]))\n')
        out.append('                ref_cy = int(round(img_size - (refined_tip[1] - di["offset_y"]) / di["fit_scale"]))\n')
        out.append('                tips.append(refined_tip)\n')
        out.append('                ap = op.replace(".png", "_annotated.png")\n')
        out.append('                try:\n')
        out.append('                    from PIL import Image, ImageDraw\n')
        out.append('                    img_pil = Image.open(op).convert("RGB")\n')
        out.append('                    draw = ImageDraw.Draw(img_pil)\n')
        out.append('                    r = max(12, int(max(tx2 - tx1, ty2 - ty1) / 2) + 5)\n')
        out.append('                    draw.ellipse([ref_cx-r, ref_cy-r, ref_cx+r, ref_cy+r], outline="green", width=2)\n')
        out.append('                    draw.ellipse([ref_cx-3, ref_cy-3, ref_cx+3, ref_cy+3], fill="green")\n')
        out.append('                    draw.text((ref_cx+15, ref_cy-10), "tip"+str(tip["tip_id"]), fill="green")\n')
        out.append('                    img_pil.save(ap)\n')
        out.append('                    print("    annotated: " + ap)\n')
        out.append('                except Exception as e:\n')
        out.append('                    print("  [ann err] " + str(e))\n')
        out.append('                p = "  tip#" + str(tip["tip_id"]) + ": CADmm(" + format(refined_tip[0], ".1f") + "," + format(refined_tip[1], ".1f") + ")"\n')
        out.append('                print(p)\n')
        out.append('            tips_by_view[vn] = tips\n')
        out.append('            print("  [" + vn + "] " + str(len(tips)) + " tip(s)")\n')
        out.append('        else:\n')
        out.append('            tips_by_view[vn] = []\n')
        out.append('            print("  [" + vn + "] VLM: none")\n')
        out.append('        print()\n')
        # Skip until "if not any"
        j = i + 1
        while j < len(lines):
            if lines[j].strip().startswith('if not any'):
                break
            j += 1
        continue
    
    # === 6. Insert dedup before triangulate ===
    if s.startswith('if not any(tips_by_view.values())'):
        out.append(line)
        out.append('    \n')
        out.append('    # Dedup: Y/Z가近고 X가 다른 경우 -> 최대 X 선택\n')
        out.append('    all_tips = []\n')
        out.append('    for vn2, tips in tips_by_view.items():\n')
        out.append('        for t in tips:\n')
        out.append('            all_tips.append(t)\n')
        out.append('    if all_tips:\n')
        out.append('        deduped = dedup_tips(all_tips, tol=30.0)\n')
        out.append('        print("Dedup: " + str(len(all_tips)) + " -> " + str(len(deduped)) + " tip(s)")\n')
        out.append('        tips_by_view = {"dedup": deduped}\n')
        out.append('    \n')
        out.append('    # Triangulate\n')
        out.append('    tips_3d = triangulate(tips_by_view, verts_mm)\n')
        # Skip old triangulate line
        j = i + 1
        while j < len(lines) and 'triangulate' in lines[j]:
            j += 1
        continue
    
    out.append(line)

with open(dst, 'w') as f:
    f.writelines(out)

import py_compile
py_compile.compile(dst, doraise=True)
print('OK')
