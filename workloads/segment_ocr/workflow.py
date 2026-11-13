"""SegmentOCR client: read the license plate in a low-quality camera frame.

Four HTTP calls (five when the first plate query finds nothing) to one
AUTOMATIC1111 WebUI server with the sd-webui-segment-anything and sd-webui-ocr
extensions:

  1. POST /sdapi/v1/extra-single-image  ESRGAN_4x upscaler, resize factor 2   -> upscaled frame
  2. POST /sam/sam-predict              GroundingDINO("car") + SAM, threshold 0.30
                                        -> car mask; the workflow stops if there is no car
  3. POST /sam/sam-predict              GroundingDINO("license plate") + SAM, threshold 0.25
                                        -> plate mask (retried once with the prompt "plate" if empty)
     (client) crop the plate from the upscaled frame using the mask's bounding box (+8 px)
  4. POST /ocr/predict                  PP-OCRv4 detection + recognition on the crop -> text

Calls 2 and 3 both carry the full upscaled frame. The client also writes the
upscaled frame, mask overlays and the crop to its output directory, as the
original application does.
"""
from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Any, Dict, List, Optional

import numpy as np
import requests
from PIL import Image

UPSCALER_NAME = "ESRGAN_4x"
SAM_MODEL_NAME = "sam_vit_h_4b8939.pth"
DINO_MODEL_NAME = "GroundingDINO_SwinT_OGC (694MB)"
SCALE = 2.0
CAR_BOX_THR = 0.30
PLATE_BOX_THR = 0.25
PLATE_PAD = 8
TIMEOUT_S = 600


# ---------------- image helpers ----------------
def pil_to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def b64_to_pil(b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(b64))).convert("RGBA")


def b64_to_mask01(b64: str) -> np.ndarray:
    """SAM returns the mask as an image; binarize it to 0/1."""
    arr = np.array(b64_to_pil(b64).convert("L"))
    return (arr > 128).astype(np.uint8)


def overlay_mask(img_rgba: Image.Image, mask01: np.ndarray) -> Image.Image:
    rgb = np.array(img_rgba.convert("RGB"), dtype=np.float32)
    m = mask01.astype(np.float32)[..., None]
    tint = np.zeros_like(rgb)
    tint[..., 1] = 255  # green
    out = rgb * (1 - 0.35 * m) + tint * (0.35 * m)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def mask_bbox_padded(mask01: np.ndarray, width: int, height: int, pad: int) -> Optional[List[int]]:
    """(x1, y1, x2, y2), inclusive, of the mask's bounding box grown by `pad`; None if the mask is empty."""
    ys, xs = np.where(mask01 > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None
    x1, x2 = xs.min(), xs.max()
    y1, y2 = ys.min(), ys.max()
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(width - 1, x2 + pad)
    y2 = min(height - 1, y2 + pad)
    return [int(x1), int(y1), int(x2), int(y2)]


def masked_crop_rgba(img_rgba: Image.Image, mask01: np.ndarray, pad: int = 8) -> Optional[Image.Image]:
    """Crop the padded bounding box of the mask; pixels outside the mask become transparent."""
    box = mask_bbox_padded(mask01, img_rgba.width, img_rgba.height, pad)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    crop = img_rgba.crop((x1, y1, x2 + 1, y2 + 1)).convert("RGBA")
    arr = np.array(crop)
    arr[..., 3] = (mask01[y1:y2 + 1, x1:x2 + 1] * 255).astype(np.uint8)
    return Image.fromarray(arr)


def ocr_text_from_response(resp_json: Dict[str, Any]) -> str:
    """/ocr/predict returns {"result": [{"text": ..., "box": [...]}, ...]}."""
    texts = []
    for it in resp_json.get("result", []) or []:
        t = (it.get("text") or "").strip()
        if t:
            texts.append(t)
    return " ".join(texts).strip()


# ---------------- API calls ----------------
def extras_payload(img: Image.Image, scale: float = SCALE) -> Dict[str, Any]:
    return {
        "resize_mode": 0,               # scale by factor
        "upscaling_resize": float(scale),
        "upscaler_1": UPSCALER_NAME,
        "image": pil_to_b64(img),
    }


def call_extras(base_url: str, payload: Dict[str, Any]) -> Image.Image:
    r = requests.post(f"{base_url}/sdapi/v1/extra-single-image", json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    return b64_to_pil(r.json()["image"])


def call_sam_mask_top1(base_url: str, img_rgba: Image.Image, text_prompt: str, box_thresh: float) -> Optional[str]:
    payload = {
        "sam_model_name": SAM_MODEL_NAME,
        "input_image": pil_to_b64(img_rgba),
        "output_mode": "mask_top1",
        "mask_index": 0,
        "sam_positive_points": [],
        "sam_negative_points": [],
        "dino_enabled": True,
        "dino_model_name": DINO_MODEL_NAME,
        "dino_text_prompt": text_prompt,
        "dino_box_threshold": float(box_thresh),
        "dino_preview_checkbox": False,
        "dino_preview_boxes_selection": None,
    }
    r = requests.post(f"{base_url}/sam/sam-predict", json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    masks = r.json().get("masks") or []
    return masks[0] if masks else None


def call_ocr(base_url: str, img_rgb: Image.Image) -> str:
    r = requests.post(f"{base_url}/ocr/predict", json={"image": pil_to_b64(img_rgb)}, timeout=TIMEOUT_S)
    r.raise_for_status()
    return ocr_text_from_response(r.json())


# ---------------- workflow ----------------
def load_input(img_path: str) -> Image.Image:
    return Image.open(img_path).convert("RGB")


def read_plate(first_payload: Dict[str, Any], base_url: str, out_dir: str) -> Dict[str, Any]:
    """Runs the workflow from the upscale request (built by extras_payload) to the OCR text."""
    base_url = base_url.rstrip("/")
    os.makedirs(out_dir, exist_ok=True)

    upscaled = call_extras(base_url, first_payload).convert("RGBA")
    upscaled.convert("RGB").save(os.path.join(out_dir, "01_deblur.png"))

    car_mask_b64 = call_sam_mask_top1(base_url, upscaled, "car", CAR_BOX_THR)
    if not car_mask_b64:
        raise RuntimeError("No car detected")
    overlay_mask(upscaled, b64_to_mask01(car_mask_b64)).save(os.path.join(out_dir, "02_car_overlay.png"))

    plate_mask_b64 = call_sam_mask_top1(base_url, upscaled, "license plate", PLATE_BOX_THR)
    if not plate_mask_b64:
        plate_mask_b64 = call_sam_mask_top1(base_url, upscaled, "plate", PLATE_BOX_THR)
    if not plate_mask_b64:
        raise RuntimeError("No plate detected")
    plate_mask01 = b64_to_mask01(plate_mask_b64)
    overlay_mask(upscaled, plate_mask01).save(os.path.join(out_dir, "03_plate_overlay.png"))

    plate_crop_rgba = masked_crop_rgba(upscaled, plate_mask01, pad=PLATE_PAD)
    if plate_crop_rgba is None:
        raise RuntimeError("Plate crop failed")
    plate_crop_rgb = plate_crop_rgba.convert("RGB")
    plate_crop_rgb.save(os.path.join(out_dir, "04_plate_crop.png"))

    text = call_ocr(base_url, plate_crop_rgb)
    return {
        "car_mask": car_mask_b64,
        "plate_mask": plate_mask_b64,
        "plate_bbox": mask_bbox_padded(plate_mask01, upscaled.width, upscaled.height, PLATE_PAD),
        "plate_crop": pil_to_b64(plate_crop_rgb),
        "ocr_text": text,
    }
