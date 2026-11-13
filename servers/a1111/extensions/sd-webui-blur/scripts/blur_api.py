# sd-webui-blur: image blur and mask compositing routes for the AUTOMATIC1111 WebUI API.
#
# Written by the WebAPI-Workflows authors for the ImageBlur workload; not an upstream extension.
# License: Apache-2.0 (see LICENSE at the repository root).
#
# Routes (registered on app start, JSON in / JSON out, images as base64 strings):
#   GET  /blur/health    -> {"ok": true, "has_cv2": bool}
#   POST /blur/generate  {"input_image", "blur_ksize"=41, "output_format"="PNG", "jpeg_quality"=95}
#                        -> {"ok": true, "image": <Gaussian-blurred image>}
#   POST /compose        {"original_image", "blurred_image", "mask_image", "mask_feather"=7,
#                         "output_format"="PNG", "jpeg_quality"=95}
#                        -> {"ok": true, "image": <original outside the mask, blurred inside>}
# A missing image field returns {"ok": false, "error": "missing field: ..."} with status 200.
# "return_image" is accepted and ignored (the image is always returned).
#
# The blur uses OpenCV (cv2.GaussianBlur, kernel blur_ksize x blur_ksize, sigma from the kernel
# size) when cv2 can be imported, and falls back to PIL GaussianBlur(radius=blur_ksize // 6)
# otherwise; the two give different pixels. The development deployment had opencv-python 4.11.0.86.
import base64
from io import BytesIO
from typing import Any, Dict

import numpy as np
from PIL import Image

import modules.script_callbacks as script_callbacks

try:
    import cv2
except Exception:
    cv2 = None


def _strip_data_url(b64: str) -> str:
    if "," in b64 and "base64" in b64[:80]:
        return b64.split(",", 1)[1]
    return b64


def _b64_to_pil_rgb(b64: str) -> Image.Image:
    b64 = _strip_data_url(b64)
    data = base64.b64decode(b64)
    return Image.open(BytesIO(data)).convert("RGB")


def _b64_to_pil_l(b64: str) -> Image.Image:
    b64 = _strip_data_url(b64)
    data = base64.b64decode(b64)
    return Image.open(BytesIO(data)).convert("L")


def _pil_to_b64(img: Image.Image, fmt: str = "PNG", jpeg_quality: int = 95) -> str:
    buf = BytesIO()
    fmt = fmt.upper()
    kwargs = {}
    if fmt in ("JPG", "JPEG"):
        fmt = "JPEG"
        kwargs["quality"] = int(jpeg_quality)
        kwargs["optimize"] = True
    img.save(buf, format=fmt, **kwargs)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _ensure_odd(k: int) -> int:
    k = int(k)
    if k < 1:
        k = 1
    return k if (k % 2 == 1) else k + 1


def _gaussian_blur_pil(pil_img: Image.Image, blur_ksize: int = 41) -> Image.Image:
    if cv2 is None:
        from PIL import ImageFilter
        radius = max(1, int(blur_ksize // 6))
        return pil_img.filter(ImageFilter.GaussianBlur(radius=radius))

    k = _ensure_odd(blur_ksize)
    img = np.array(pil_img, dtype=np.uint8)  # RGB
    bgr = img[:, :, ::-1]
    bgr_blur = cv2.GaussianBlur(bgr, (k, k), 0)
    rgb_blur = bgr_blur[:, :, ::-1]
    return Image.fromarray(rgb_blur, mode="RGB")


def _compose_by_mask(original: Image.Image, blurred: Image.Image, mask_l: Image.Image, mask_feather: int = 7) -> Image.Image:
    if blurred.size != original.size:
        blurred = blurred.resize(original.size, Image.BILINEAR)
    if mask_l.size != original.size:
        mask_l = mask_l.resize(original.size, Image.NEAREST)

    orig = np.array(original, dtype=np.uint8)
    blur = np.array(blurred, dtype=np.uint8)
    mask = np.array(mask_l, dtype=np.uint8)

    if cv2 is not None and mask_feather > 0:
        fk = _ensure_odd(mask_feather * 2 + 1)
        mask = cv2.GaussianBlur(mask, (fk, fk), 0)

    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    out = orig.astype(np.float32) * (1.0 - alpha) + blur.astype(np.float32) * alpha
    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def on_app_started(demo: Any, app: Any):
    @app.get("/blur/health")
    async def blur_health():
        return {"ok": True, "has_cv2": cv2 is not None}

    @app.post("/blur/generate")
    async def api_blur_generate(payload: Dict[str, Any]) -> Dict[str, Any]:
        b64_img = payload.get("input_image")
        if not b64_img:
            return {"ok": False, "error": "missing field: input_image"}

        blur_ksize = int(payload.get("blur_ksize", 41))
        output_format = str(payload.get("output_format", "PNG")).upper()
        jpeg_quality = int(payload.get("jpeg_quality", 95))

        pil_img = _b64_to_pil_rgb(b64_img)
        out = _gaussian_blur_pil(pil_img, blur_ksize=blur_ksize)
        out_b64 = _pil_to_b64(out, fmt=output_format, jpeg_quality=jpeg_quality)
        return {"ok": True, "image": out_b64}

    @app.post("/compose")
    async def api_compose(payload: Dict[str, Any]) -> Dict[str, Any]:
        b64_orig = payload.get("original_image")
        b64_blur = payload.get("blurred_image")
        b64_mask = payload.get("mask_image")
        if not b64_orig:
            return {"ok": False, "error": "missing field: original_image"}
        if not b64_blur:
            return {"ok": False, "error": "missing field: blurred_image"}
        if not b64_mask:
            return {"ok": False, "error": "missing field: mask_image"}

        mask_feather = int(payload.get("mask_feather", 7))
        output_format = str(payload.get("output_format", "PNG")).upper()
        jpeg_quality = int(payload.get("jpeg_quality", 95))

        orig = _b64_to_pil_rgb(b64_orig)
        blur = _b64_to_pil_rgb(b64_blur)
        mask = _b64_to_pil_l(b64_mask)

        out = _compose_by_mask(orig, blur, mask, mask_feather=mask_feather)
        out_b64 = _pil_to_b64(out, fmt=output_format, jpeg_quality=jpeg_quality)
        return {"ok": True, "image": out_b64}

    print("[sd-webui-blur] registered /blur/generate and /compose")


script_callbacks.on_app_started(on_app_started)
