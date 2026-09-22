#!/usr/bin/env python3
fpath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
with open(fpath, 'r') as f:
    lines = f.readlines()

out = []
skip = False

for i, line in enumerate(lines):
    s = line.strip()
    if s == 'raw = get_vlm(op)':
        skip = True
        out.append('        raw = get_vlm(op)\n')
        out.append('        if raw:\n')
        out.append('            tips_vlm, vlm_w, vlm_h = parse_vlm(raw)\n')
        out.append('        else:\n')
        out.append('            tips_vlm = []; vlm_w = 0; vlm_h = 0\n')
        out.append('        if tips_vlm:\n')
        out.append('            aw = 1100; ah = 1100\n')
        out.append('            sx = aw/vlm_w if vlm_w > 0 else 1.0\n')
        out.append('            sy = ah/vlm_h if vlm_h > 0 else 1.0\n')
        out.append('            tips = []\n')
        out.append('            for tip in tips_vlm:\n')
        out.append('                bx1 = tip["x1"]*sx if tip["x1"] else None\n')
        out.append('                by1 = tip["y1"]*sy if tip["y1"] else None\n')
        out.append('                bx2 = tip["x2"]*sx if tip["x2"] else None\n')
        out.append('                by2 = tip["y2"]*sy if tip["y2"] else None\n')
        out.append('                tx1 = int(bx1) if bx1 else 0\n')
        out.append('                ty1 = int(by1) if by1 else 0\n')
        out.append('                tx2 = int(bx2) if bx2 else 0\n')
        out.append('                ty2 = int(by2) if by2 else 0\n')
        out.append('                ap = op.replace(".png","_annotated.png")\n')
        out.append('                try:\n')
        out.append('                    from PIL import Image, ImageDraw\n')
        out.append('                    img_pil = Image.open(op).convert("RGB")\n')
        out.append('                    draw = ImageDraw.Draw(img_pil)\n')
        out.append('                    draw.rectangle([tx1,ty1,tx2,ty2], outline="green", width=2)\n')
        out.append('                    draw.text((tx1+2,ty1+2),"tip"+str(tip["tip_id"]),fill="green")\n')
        out.append('                    img_pil.save(ap)\n')
        out.append('                    print("    annotated: "+ap)\n')
        out.append('                except Exception as e:\n')
        out.append('                    print("  [ann err] "+str(e))\n')
        out.append('                cx = (tx1+tx2)/2\n')
        out.append('                cy = (ty1+ty2)/2\n')
        out.append('                ch = (cx-di["offset_x"])/di["fit_scale"]\n')
        out.append('                cv = (img_size-cy-di["offset_y"])/di["fit_scale"]\n')
        out.append('                tips.append(np.array([ch,cv,0.0]))\n')
        # Print using vars to avoid long line
        out.append('                p = "  tip#"+str(tip["tip_id"])\n')
        out.append('                p += ": VLM["+str(int(tip["x1"]))+","+str(int(tip["y1"]))+"]"\n')
        out.append('                p += "->["+str(int(tip["x2"]))+","+str(int(tip["y2"]))+"]"\n')
        out.append('                p += " CADmm("+format(ch,".1f")+","+format(cv,".1f")+")"\n')
        out.append('                print(p)\n')
        out.append('            tips_by_view[vn] = tips\n')
        out.append('            print("  ["+vn+"] "+str(len(tips))+" tip(s)")\n')
        out.append('        else:\n')
        out.append('            tips_by_view[vn] = []\n')
        out.append('            print("  ["+vn+"] VLM: none")\n')
        out.append('        print()\n')
        continue
    if skip:
        if s.startswith('if not any'):
            skip = False
            out.append('\n')
            out.append(line)
        continue
    out.append(line)

with open(fpath, 'w') as f:
    f.writelines(out)

import py_compile
py_compile.compile(fpath, doraise=True)
print('OK')
