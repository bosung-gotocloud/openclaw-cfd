#!/usr/bin/env python3
"""
OLLama VLM 기반 이미지 분석 스크립트
- 돌출부를 VLM으로 찾아서 빨간 동그라미로 표시
"""

import json
import argparse
import ollama
from PIL import Image, ImageDraw

MODEL_NAME = "qwen3.6:35b"


def get_vision_analysis(image_path, prompt):
    system_prompt = (
        "JSON only, no backticks.\n"
        "{\"objects\": [{\"name\": string, \"ty\": number, \"tx\": number}]}\n"
        "ty, tx = pixel coords (0,0=top-left).\n"
        "Find the 5 tips of aircraft in this image:\n"
        "  wingtip_left, wingtip_right, tail, stabilizer_left, stabilizer_right\n"
        "Each is the EXACT outermost pixel of the feature.\n"
        "Respond in same language as prompt."
    )

    response_stream = ollama.chat(
        model=MODEL_NAME,
        format="json",
        messages=[
            {
                "role": "user",
                "content": f"{system_prompt}\nTask: {prompt}",
                "images": [image_path]
            }
        ],
        options={
            "temperature": 0,
            "seed": 42
        },
        stream=True,
    )

    full_content = ""
    for chunk in response_stream:
        token = chunk['message']['content']
        print(token, end='', flush=True)
        full_content += token

    return full_content


def draw_circle(draw, px, py, radius=10):
    r = radius
    draw.ellipse([px - r, py - r, px + r, py + r], outline="red", width=2)
    draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill="red")


def process_and_visualize(image_path, ai_response_json):
    clean_json = ai_response_json.strip()
    if "```" in clean_json:
        clean_json = clean_json.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(clean_json)
    except json.JSONDecodeError:
        print("\nFailed to parse JSON.")
        return

    draw_img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(draw_img)

    objects = data.get("objects", [])
    radius = max(6, int(min(*draw_img.size) * 0.015))

    print(f"\n📍 {len(objects)}개:")
    for obj in objects:
        name = obj.get("name", "?")
        ty = obj.get("ty", obj.get("center", [None, None])[0])
        tx = obj.get("tx", obj.get("center", [None, None])[1])
        if ty is None or tx is None:
            print(f"  - {name}: missing")
            continue
        ty, tx = float(ty), float(tx)
        print(f"  - {name}: ({tx:.0f}, {ty:.0f})")
        draw_circle(draw, tx, ty, radius)

    out_path = image_path.rsplit(".", 1)[0] + "_annotated.png"
    draw_img.save(out_path)
    print(f"\n✅ {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("prompt", nargs="?", default=None)
    args = parser.parse_args()
    prompt = args.prompt or "이 기체의 날개끝(좌우), 테일, 미익 끝(좌우)를 빨간 동그라미로 마크해. 각 끝의 가장 바깥 픽셀만 마크해."
    raw = get_vision_analysis(args.image, prompt)
    process_and_visualize(args.image, raw)
