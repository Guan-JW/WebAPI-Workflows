"""CaptionCompare client: three identical captioning requests for one image.

The client reads the image once, base64-encodes it, and sends the same
POST /sdapi/v1/interrogate request (model "clip") three times to an
AUTOMATIC1111 WebUI server. Each request carries the full image. The three
captions are written to captions.txt in the output directory.
"""
from __future__ import annotations

import base64
import os
from typing import List

import requests

MODEL = "clip"
REPEAT = 3
TIMEOUT_S = 600


def load_input(img_path: str) -> str:
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def interrogate(base_url: str, image_b64: str, model: str) -> str:
    payload = {"image": image_b64, "model": model}
    r = requests.post(f"{base_url}/sdapi/v1/interrogate", json=payload,
                      headers={"Content-Type": "application/json"}, timeout=TIMEOUT_S)
    r.raise_for_status()
    caption = r.json().get("caption", "")
    if not isinstance(caption, str):
        caption = str(caption)
    return caption


def caption_repeat(image_b64: str, base_url: str, out_dir: str, model: str = MODEL, repeat: int = REPEAT) -> List[str]:
    base_url = base_url.rstrip("/")
    os.makedirs(out_dir, exist_ok=True)
    captions = [interrogate(base_url, image_b64, model) for _ in range(repeat)]
    with open(os.path.join(out_dir, "captions.txt"), "w", encoding="utf-8") as f:
        for i, cap in enumerate(captions, start=1):
            f.write(f"#{i}\t{cap.strip()}\n")
    return captions
