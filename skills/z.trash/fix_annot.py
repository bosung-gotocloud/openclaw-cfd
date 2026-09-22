#!/usr/bin/env python3
"""Fix annotation to draw circles at refined tip positions (not bbox)."""
fpath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
with open(fpath, 'r') as f:
    lines = f.readlines()

out = []
skip = False

for i, line in enumerate(lines):
    s = line.strip()
    if s == '# CAD edge-based refinement within bbox':
        skip = True
        out.append('                # CAD edge-based refinement within bbox\n')
        out.append('                bbox_px = {"x0": tx1, "x1": tx2, "y0": ty1, "y1": ty2}\n')
        out.append('                refined_tip = find_tips_in_bbox(edges, vn, bbox_px, di, bbox_mm, img_size)\n')
        out.append('                \n')
        out.append('                if refined_tip is not None:\n')
        out.append('                    tips.append(refined_tip)\n')
        out.append('                    # Draw circle at refined position (pixel coords)\n')
        out.append('                    ref_px_h = (refined_tip[0] - di["offset_x"]) / di["fit_scale"] + di["offset_x"]\n')
        out.append('                    ref_px_v = img_size - ((refined_tip[1] - di["offset_y"]) / di["fit_scale"] + di["offset_y"])\n')
        out.append('                    ref_cx = int(round(ref_px_h))\n')
        out.append('                    ref_cy = int(round(ref_px_v))\n')
        out.append('                    \n')
        out.append('                    ap = op.replace(".png","_annotated.png")\n')
        out.append('                    try:\n')
        out.append('                        from PIL import Image, ImageDraw\n')
        out.append('                        img_pil = Image.open(op).convert("RGB")\n')
        out.append('                        draw = ImageDraw.Draw(img_pil)\n')
        out.append('                        # Draw circle at refined tip position\n')
        out.append('                        r = 12\n')
        out.append('                        draw.ellipse([ref_cx-r, ref_cy-r, ref_cx+r, ref_cy+r], outline="green", width=2)\n')
        out.append('                        draw.ellipse([ref_cx-3, ref_cy-3, ref_cx+3, ref_cy+3], fill="green")\n')
        out.append('                        lbl = "tip" + str(tip["tip_id"])\n')
        out.append('                        draw.text((ref_cx+15, ref_cy-10), lbl, fill="green")\n')
        out.append('                        img_pil.save(ap)\n')
        out.append('                        print("    annotated: "+ap)\n')
        out.append('                    except Exception as e:\n')
        out.append('                        print("  [ann err] "+str(e))\n')
        out.append('                    p = "  tip#"+str(tip["tip_id"]) + ": CADmm("+format(refined_tip[0],".1f")+","+format(refined_tip[1],".1f")+")"\n')
        out.append('                    print(p)\n')
        out.append('                else:\n')
        out.append('                    tips.append(np.array([ch,cv,0.0]))\n')
        out.append('                    p = "  tip#"+str(tip["tip_id"]) + ": CADmm("+format(ch,".1f")+","+format(cv,".1f")+")"\n')
        out.append('                    p += " [no CAD refine]"\n')
        out.append('                    print(p)\n')
        continue
    
    if skip:
        if s.startswith('cx = (tx1+tx2)/2') or s.startswith('cx = (tx1 + tx2)/2'):
            skip = False
            continue  # skip this line and all old annotation code
        if s.startswith('p = "  tip#"+str(tip["tip_id"]'):
            skip = False
            continue
        continue
    
    out.append(line)

with open(fpath, 'w') as f:
    f.writelines(out)

import py_compile
py_compile.compile(fpath, doraise=True)
print('OK')
