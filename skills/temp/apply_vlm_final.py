#!/usr/bin/env python3
fpath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
with open(fpath, 'r') as f:
    content = f.read()

# ===== 1. VLM 프롬프트 개선 =====
content = content.replace(
    'Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}")',
    'Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}")'
)

# ===== 2. dedup 함수 삽입 =====
dedup_code = """

def dedup_tips(tips_list, tol=50.0):
    \"\"\"Y와 Z가 tol内인 tip들을 그룹핑 -> 각 그룹에서 최대 X 선택
    X도近으면 동일 tip으로 간주.\"\"\"
    if not tips_list:
        return []
    
    groups = []
    for tip in tips_list:
        placed = False
        for g in groups:
            dy = abs(tip[1] - g['y'])
            dz = abs(tip[2] - g['z'])
            if dy < tol and dz < tol:
                g.append(tip)
                placed = True
                break
        if not placed:
            groups.append([tip])
    
    final = []
    for g in groups:
        best = max(g, key=lambda t: t[0])
        final.append(best)
    
    result = []
    for tip in final:
        is_dup = False
        for existing in result:
            if np.linalg.norm(tip - existing) < tol:
                is_dup = True
                break
        if not is_dup:
            result.append(tip)
    
    return result
"""

# find_tips_in_bbox 뒤 dedup_t 삽입
content = content.replace(
    '    return np.array([cad_h, cad_v, 0.0])\n\n\ndef triangulate',
    '    return np.array([cad_h, cad_v, 0.0])\n' + dedup_code + '\ndef triangulate'
)

# ===== 3. main에서 dedup 적용 =====
content = content.replace(
    '    # Triangulate (tips_by_view: mm, verts_mm: mm)\n    tips_3d = triangulate',
    '    # Dedup tips: Y/Z가近고 X가 다른 경우 -> 최대 X 선택\n    all_tips = []\n    for vn, tips in tips_by_view.items():\n        for t in tips:\n            all_tips.append(t)\n    \n    if all_tips:\n        deduped = dedup_tips(all_tips, tol=30.0)\n        print("Dedup: " + str(len(all_tips)) + " -> " + str(len(deduped)) + " tip(s)")\n        tips_by_view = {"dedup": deduped}\n    \n    # Triangulate (tips_by_view: mm, verts_mm: mm)\n    tips_3d = triangulate'
)

# ===== 4. annotation 원으로 =====
content = content.replace(
    '                    # Expand bbox significantly for visibility\n                    w = max(tx2-tx1, 1) + 20  # at least 20px wide\n                    h = max(ty2-ty1, 1) + 20  # at least 20px tall\n                    bx1, by1 = min(tx1, ty1) - 10, min(tx1, ty1) - 10\n                    bx2, by2 = max(tx2, ty2) + 10, max(tx2, ty2) + 10\n                    draw.rectangle([bx1, by1, bx2, by2], outline="green", width=3)\n                    # Draw center dot\n                    cx_box = (bx1+bx2)//2\n                    cy_box = (by1+by2)//2\n                    draw.ellipse([cx_box-3,cy_box-3,cx_box+3,cy_box+3], fill="green")',
    '                    # Draw sufficient size circle annotation\n                    cx_box = (tx1 + tx2) // 2\n                    cy_box = (ty1 + ty2) // 2\n                    box_w = max(tx2 - tx1, 10)\n                    box_h = max(ty2 - ty1, 10)\n                    radius = max(box_w, box_h) // 2 + 5\n                    radius = min(radius, 50)\n                    draw.ellipse([cx_box-radius, cy_box-radius, cx_box+radius, cy_box+radius],\n                                 outline="green", width=2)\n                    draw.ellipse([cx_box-3, cy_box-3, cx_box+3, cy_box+3], fill="green")'
)

# ===== 5. VLM prompt 개선 (tip + sharp corner만) =====
content = content.replace(
    '"Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. "\n                  "Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}"',
    '"Find ONLY wing tips, tail tips, and sharp corner points (extreme pointed ends) in this image. "\n                  "Return JSON: {image_width, image_height, tips: [{tip_id, x1, y1, x2, y2}]}"'
)

with open(fpath, 'w') as f:
    f.write(content)

import py_compile
py_compile.compile(fpath, doraise=True)
print('OK')
