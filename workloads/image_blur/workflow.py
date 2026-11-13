"""ImageBlur client: blur faces and cars in a photo before it is shared.

Four HTTP calls to one AUTOMATIC1111 WebUI server with the
sd-webui-segment-anything and sd-webui-blur extensions, over one keep-alive
session:

  1. POST /sam/sam-predict   GroundingDINO("human face") + SAM -> face mask (selected mask only)
  2. POST /sam/sam-predict   GroundingDINO("car") + SAM        -> car mask (selected mask only)
     (client) union of the two masks
  3. POST /blur/generate     Gaussian blur of the whole photo  -> blurred photo
  4. POST /compose           original + blurred + union mask   -> final photo

Calls 1, 2 and 3 all carry the same photo; call 4 carries the photo, the
blurred photo and the mask. The original command-line application could ask
the user to confirm before blurring; that prompt is not part of the benchmark.
"""
from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from typing import Any, Dict, Optional

import numpy as np
import requests
from PIL import Image

SAM_MODEL_NAME = "sam_vit_h_4b8939.pth"
DINO_MODEL_NAME = "GroundingDINO_SwinT_OGC (694MB)"
DINO_BOX_THRESHOLD = 0.3
FACE_PROMPT = "human face"
CAR_PROMPT = "car"
BLUR_KSIZE = 41
TIMEOUT_S = 600


# ---------------- base64 helpers ----------------
def _strip_data_url(b64: str) -> str:
    if "," in b64 and "base64" in b64[:80]:
        return b64.split(",", 1)[1]
    return b64


def pil_to_b64(img: Image.Image, fmt: str = "PNG", jpeg_quality: int = 95) -> str:
    buf = BytesIO()
    fmt_u = fmt.upper()
    kwargs = {}
    if fmt_u in ("JPG", "JPEG"):
        fmt_u = "JPEG"
        kwargs["quality"] = int(jpeg_quality)
        kwargs["optimize"] = True
    img.save(buf, format=fmt_u, **kwargs)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def b64_to_pil_rgb(b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(_strip_data_url(b64)))).convert("RGB")


def b64_to_pil_l(b64: str) -> Image.Image:
    return Image.open(BytesIO(base64.b64decode(_strip_data_url(b64)))).convert("L")


def read_image_as_b64(path: str) -> str:
    """Decode the photo and re-encode it (JPEG q95 for .jpg/.jpeg, PNG otherwise)."""
    img = Image.open(path).convert("RGB")
    ext = os.path.splitext(path)[1].lower()
    fmt = "PNG" if ext == ".png" else "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
    return pil_to_b64(img, fmt=fmt)


def save_b64_image(b64: str, out_path: str) -> None:
    b64_to_pil_rgb(b64).save(out_path)


def save_b64_mask(b64: str, out_path: str) -> None:
    b64_to_pil_l(b64).save(out_path)


# ---------------- http ----------------
def post_json(session: requests.Session, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = session.post(url, data=body, headers={"Content-Type": "application/json"}, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def union_masks_b64(mask1_b64: str, mask2_b64: str, thr: int = 127) -> str:
    """Union of two masks (white = selected), as an L-mode PNG."""
    m1 = b64_to_pil_l(mask1_b64)
    m2 = b64_to_pil_l(mask2_b64)
    if m2.size != m1.size:
        m2 = m2.resize(m1.size, Image.NEAREST)
    a = np.array(m1, dtype=np.uint8)
    b = np.array(m2, dtype=np.uint8)
    u = (np.maximum(a, b) > thr).astype(np.uint8) * 255
    return pil_to_b64(Image.fromarray(u, mode="L"), fmt="PNG")


def sam_mask_top1(session: requests.Session, base_url: str, image_b64: str, text_prompt: str) -> str:
    """/sam/sam-predict asking for the first candidate mask only (output_mode=mask_top1)."""
    payload = {
        "sam_model_name": SAM_MODEL_NAME,
        "input_image": image_b64,
        "output_mode": "mask_top1",
        "mask_index": 0,
        "sam_positive_points": [],
        "sam_negative_points": [],
        "dino_enabled": True,
        "dino_model_name": DINO_MODEL_NAME,
        "dino_text_prompt": text_prompt,
        "dino_box_threshold": DINO_BOX_THRESHOLD,
        "dino_preview_checkbox": False,
        "dino_preview_boxes_selection": None,
    }
    resp = post_json(session, base_url + "/sam/sam-predict", payload)
    if not resp:
        raise RuntimeError(f"SAM returned empty response (server error) for prompt={text_prompt!r}")
    masks = resp.get("masks", [])
    if not masks:
        raise RuntimeError(f"SAM returned no masks for prompt={text_prompt!r}. resp keys={list(resp.keys())}")
    return masks[0]


def _first(resp: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        if resp.get(k):
            return resp[k]
    return None


def blur_faces_and_cars(image_b64: str, base_url: str, out_dir: str, blur_ksize: int = BLUR_KSIZE) -> Dict[str, str]:
    """Returns the base64 strings of the masks, the blurred photo and the final photo."""
    base_url = base_url.rstrip("/")
    os.makedirs(out_dir, exist_ok=True)
    sess = requests.Session()

    face_mask_b64 = sam_mask_top1(sess, base_url, image_b64, FACE_PROMPT)
    car_mask_b64 = sam_mask_top1(sess, base_url, image_b64, CAR_PROMPT)
    save_b64_mask(face_mask_b64, os.path.join(out_dir, "mask_face.png"))
    save_b64_mask(car_mask_b64, os.path.join(out_dir, "mask_car.png"))

    union_b64 = union_masks_b64(face_mask_b64, car_mask_b64)
    save_b64_mask(union_b64, os.path.join(out_dir, "mask_union.png"))

    blur_resp = post_json(sess, base_url + "/blur/generate", {
        "input_image": image_b64,
        "blur_ksize": int(blur_ksize),
        "output_format": "PNG",
        "return_image": True,
    })
    blurred_b64 = _first(blur_resp, "image", "blurred_image", "output_image")
    if not blurred_b64:
        raise RuntimeError(f"/blur/generate returned no image field. keys={list(blur_resp.keys())}")
    save_b64_image(blurred_b64, os.path.join(out_dir, "blurred.png"))

    comp_resp = post_json(sess, base_url + "/compose", {
        "original_image": image_b64,
        "blurred_image": blurred_b64,
        "mask_image": union_b64,
        "output_format": "PNG",
        "return_image": True,
    })
    final_b64 = _first(comp_resp, "image", "final_image", "output_image")
    if not final_b64:
        raise RuntimeError(f"/compose returned no image field. keys={list(comp_resp.keys())}")
    save_b64_image(final_b64, os.path.join(out_dir, "final.png"))

    return {"mask_face": face_mask_b64, "mask_car": car_mask_b64, "mask_union": union_b64,
            "blurred": blurred_b64, "final_image": final_b64}
