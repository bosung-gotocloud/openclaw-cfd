#!/usr/bin/env python3
"""Fix vlm-tip-detect.py: replace broken newlines in get_vlm prompt."""

filepath = '/home/bosung/.openclaw/workspace/skills/tip-detect/vlm-tip-detect.py'
with open(filepath, 'r') as f:
    content = f.read()

# The get_vlm prompt has real newlines in string concatenation - fix them
# Find and replace the broken get_vlm section
old = '''        prompt = (
            "Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. "
            "Return JSON array only.

"
            "Image size: {}x{} pixels.

"
            "Format: {{\\\"image_width\\\": {}, \\\"image_height\\\": {}, "
            "\\\"tips\\\":[{{\\\"tip_id\\\": N, \\\"x1\\\": x1, \\\"y1\\\": y1, \\\"x2\\\": x2, \\\"y2\\\": y2}}]}}
"
            "- image_width, image_height: actual pixel dimensions ({}x{})
"
            "- tip_id: unique integer starting from 1
"
            "- x1, y1: top-left corner of tip bbox (pixel from top-left)
"
            "- x2, y2: bottom-right corner of tip bbox (pixel from top-left)
"
            "- Return ONLY the JSON array, no backticks, no markdown."
            .format(w, h, w, h, w, h)
        )'''

# The issue: \\\\n became real newlines in the file. We need to fix the format strings.
# Since the file is already broken, let's just rewrite get_vlm entirely.

lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'def get_vlm(image_path' in line:
        # Start of get_vlm - write the entire fixed function
        new_lines.append('def get_vlm(image_path, timeout_sec=60):')
        new_lines.append('    if not HAS_OLLAMA or not os.path.exists(image_path): return None')
        new_lines.append('    try:')
        new_lines.append('        from PIL import Image as PILImage')
        new_lines.append('        pil_img = PILImage.open(image_path)')
        new_lines.append('        w, h = pil_img.size')
        new_lines.append("        NL = chr(10)")
        new_lines.append("        prompt = (")
        new_lines.append('            "Find sharp pointed tips (wing tips, tail tips, canard tips, etc.) in this image. "')
        new_lines.append('            "Return JSON array only." + NL + NL')
        new_lines.append('            "Image size: " + str(w) + "x" + str(h) + " pixels." + NL + NL')
        new_lines.append('            "Format: {\"image_width\": " + str(w) + ", \"image_height\": " + str(h)')
        new_lines.append('            + ", \"tips\":[{\"tip_id\": N, \"x1\": x1, \"y1\": y1, \"x2\": x2, \"y2\": y2}]}" + NL')
        new_lines.append('            + "- image_width, image_height: actual pixel dimensions (" + str(w) + "x" + str(h) + ")" + NL')
        new_lines.append('            + "- tip_id: unique integer starting from 1" + NL')
        new_lines.append('            + "- x1, y1: top-left corner of tip bbox (pixel from top-left)" + NL')
        new_lines.append('            + "- x2, y2: bottom-right corner of tip bbox (pixel from top-left)" + NL')
        new_lines.append('            + "- Return ONLY the JSON array, no backticks, no markdown."')
        new_lines.append('        )')
        new_lines.append("        r = ollama.chat(model='qwen3.6:35b',")
        new_lines.append('                        messages=[{"role":"user","content":prompt,"images":[image_path]}],')
        new_lines.append('                        stream=False)')
        new_lines.append("        return r['message']['content']")
        new_lines.append('    except Exception as e:')
        new_lines.append("        print(f\"    [VLM error] {type(e).__name__}: {e}\")")
        new_lines.append('        return None')
        # Skip old get_vlm lines until next def or class
        i += 1
        while i < len(lines) and not (lines[i].startswith('def ') or (lines[i].startswith('class ') and i > 0)):
            if lines[i].strip() == '' and i + 1 < len(lines) and lines[i+1].startswith('def '):
                break
            if lines[i].startswith('def draw_vlm_bbox'):
                break
            i += 1
        continue
    new_lines.append(line)
    i += 1

content = '\n'.join(new_lines)

with open(filepath, 'w') as f:
    f.write(content)

print("Fixed get_vlm newlines.")
