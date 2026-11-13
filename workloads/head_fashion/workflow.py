"""HeadFashion client: restyle the hat, then the hair, on one photo.

Four HTTP calls to one AUTOMATIC1111 WebUI server with the
sd-webui-segment-anything extension:

  1. POST /sam/sam-predict    GroundingDINO("hat") + SAM on the photo      -> hat mask
  2. POST /sdapi/v1/img2img   SD v1.5 inpainting of the hat region          -> photo with new hat
  3. POST /sam/sam-predict    GroundingDINO("hair") + SAM on the new photo  -> hair mask
  4. POST /sdapi/v1/img2img   SD v1.5 inpainting of the hair region         -> final photo

Each step consumes the output of the previous one. Images travel as base64
strings inside JSON bodies. The client also writes the intermediate images to
its output directory, as the original application does.
"""
from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Any, Dict

import requests
from PIL import Image

DINO_MODEL_NAME = "GroundingDINO_SwinT_OGC (694MB)"
DINO_BOX_THRESHOLD = 0.3

HAT_TEXT_PROMPT = "hat"
HAIR_TEXT_PROMPT = "hair"
HAT_PROMPT = "light, summery style, straw sunhat with a yellow ribbon"
HAIR_PROMPT = "loose, light, summery hairstyle"

INPAINT_STEPS = 30
INPAINT_CFG_SCALE = 7
INPAINT_DENOISING = 0.75
INPAINT_WIDTH = 512
INPAINT_HEIGHT = 512

MASK_INDEX = 0          # /sam/sam-predict returns three candidate masks; the first one is used
DEFAULT_SEED = 1234     # img2img seed used for every measured run
TIMEOUT_S = 600


def file_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def save_b64_image(b64: str, path: str) -> None:
    img = Image.open(BytesIO(base64.b64decode(b64)))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(path)


def _post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def sam_predict(base_url: str, image_b64: str, text_prompt: str) -> Dict[str, Any]:
    payload = {
        "input_image": image_b64,
        "dino_enabled": True,
        "dino_model_name": DINO_MODEL_NAME,
        "dino_text_prompt": text_prompt,
        "dino_box_threshold": DINO_BOX_THRESHOLD,
        "dino_preview_checkbox": False,
    }
    return _post(f"{base_url}/sam/sam-predict", payload)


def sd_inpaint(base_url: str, init_image_b64: str, mask_b64: str, prompt: str, seed: int) -> Dict[str, Any]:
    payload = {
        "prompt": prompt,
        "init_images": [init_image_b64],
        "mask": mask_b64,
        "steps": INPAINT_STEPS,
        "cfg_scale": INPAINT_CFG_SCALE,
        "denoising_strength": INPAINT_DENOISING,
        "width": INPAINT_WIDTH,
        "height": INPAINT_HEIGHT,
        "inpainting_fill": 1,
        "inpaint_full_res": True,
        "inpaint_full_res_padding": 32,
        "mask_blur": 4,
        "seed": seed,
    }
    return _post(f"{base_url}/sdapi/v1/img2img", payload)


def load_input(img_path: str, out_dir: str) -> str:
    """Read the photo (raw file bytes, base64) and keep a copy in the output directory."""
    os.makedirs(out_dir, exist_ok=True)
    orig_b64 = file_to_base64(img_path)
    save_b64_image(orig_b64, os.path.join(out_dir, "00_load1_input.jpg"))
    return orig_b64


def _save_sam_previews(resp: Dict[str, Any], out_dir: str, prefix: str) -> None:
    if resp.get("blended_images"):
        save_b64_image(resp["blended_images"][MASK_INDEX], os.path.join(out_dir, f"{prefix}_blended.png"))
    if resp.get("masked_images"):
        save_b64_image(resp["masked_images"][MASK_INDEX], os.path.join(out_dir, f"{prefix}_masked.png"))


def edit(orig_b64: str, base_url: str, out_dir: str, seed: int = DEFAULT_SEED) -> Dict[str, str]:
    """Hat edit, then hair edit. Returns the base64 strings of the consumed outputs."""
    base_url = base_url.rstrip("/")

    sam_hat = sam_predict(base_url, orig_b64, HAT_TEXT_PROMPT)
    if "masks" not in sam_hat or len(sam_hat["masks"]) == 0:
        raise RuntimeError(f"SAM hat failed: {sam_hat}")
    hat_mask_b64 = sam_hat["masks"][MASK_INDEX]
    save_b64_image(hat_mask_b64, os.path.join(out_dir, "01_mask_hat.png"))
    _save_sam_previews(sam_hat, out_dir, "01_hat")

    inpaint_hat = sd_inpaint(base_url, orig_b64, hat_mask_b64, HAT_PROMPT, seed)
    if "images" not in inpaint_hat or len(inpaint_hat["images"]) == 0:
        raise RuntimeError(f"Inpaint hat failed: {inpaint_hat}")
    inpaint_hat_b64 = inpaint_hat["images"][0]
    save_b64_image(inpaint_hat_b64, os.path.join(out_dir, "02_inpaint_hat.png"))

    sam_hair = sam_predict(base_url, inpaint_hat_b64, HAIR_TEXT_PROMPT)
    if "masks" not in sam_hair or len(sam_hair["masks"]) == 0:
        raise RuntimeError(f"SAM hair failed: {sam_hair}")
    hair_mask_b64 = sam_hair["masks"][MASK_INDEX]
    save_b64_image(hair_mask_b64, os.path.join(out_dir, "03_mask_hair.png"))
    _save_sam_previews(sam_hair, out_dir, "03_hair")

    inpaint_hair = sd_inpaint(base_url, inpaint_hat_b64, hair_mask_b64, HAIR_PROMPT, seed)
    if "images" not in inpaint_hair or len(inpaint_hair["images"]) == 0:
        raise RuntimeError(f"Inpaint hair failed: {inpaint_hair}")
    final_b64 = inpaint_hair["images"][0]
    save_b64_image(final_b64, os.path.join(out_dir, "04_final_inpaint_hair.png"))

    return {"mask_hat": hat_mask_b64, "inpaint_hat": inpaint_hat_b64, "mask_hair": hair_mask_b64,
            "final_image": final_b64}
