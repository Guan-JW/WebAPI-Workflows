#!/usr/bin/env bash
# Set up the AUTOMATIC1111 WebUI server used by head_fashion, caption_compare, image_blur and
# segment_ocr: pinned WebUI and extensions, the patches in patches/, the sd-webui-blur extension
# from extensions/, the Python environment and every model file (checked by sha256).
#
#   bash setup.sh [DIR]          # default DIR=./a1111 ; the WebUI ends up in DIR/webui
#
# Steps can be run on their own:  STEPS="clone models" bash setup.sh DIR
#   clone    WebUI v1.10.1 + extensions at pinned commits, patches, sd-webui-blur, config.json
#   models   model weights and data files (about 12 GB), sha256-checked (before venv, so the
#            sd-webui-ocr installer finds its models and does not fetch the latest ones)
#   venv     Python venv, pinned pre-installs, then the WebUI's own installer (--exit)
#   hf       Hugging Face files loaded by name at run time (needs the venv)
#
# Needs: git, curl, sha256sum or shasum, Python 3.10 (PYTHON=..., default python3.10), and for the
# venv step network access to PyPI and download.pytorch.org. No GPU is needed for set-up.
# Downloads go to DIR/webui/... except the CLIP ViT-L/14 weights, which go where the clip package
# looks for them (~/.cache/clip), and the Hugging Face files, which go to the Hugging Face cache
# ($HF_HOME, default ~/.cache/huggingface).
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DIR=$(mkdir -p "${1:-./a1111}" && cd "${1:-./a1111}" && pwd)
W=$DIR/webui
PY=${PYTHON:-python3.10}
STEPS=${STEPS:-clone models venv hf}

# ---- pinned upstream code ---------------------------------------------------------------------
A1111_REPO=https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
A1111_COMMIT=82a973c04367123ae98bd9abdf80d9eda9b910e2        # tag v1.10.1, AGPL-3.0
SAM_REPO=https://github.com/continue-revolution/sd-webui-segment-anything.git
SAM_COMMIT=982138cfb505de61a3cbb257b2fa9d461d9b5493          # master, 2024-02-24; no license file
OCR_REPO=https://github.com/SpenserCai/sd-webui-ocr.git
OCR_COMMIT=5c75383ce6f0389e7d3521c5481f5bdddea8e167          # main, 2024-01-04; no license file
# The WebUI installer clones Stability-AI/stablediffusion at cf1d67a6, but that repository is no
# longer available; this mirror contains the same commit.
export STABLE_DIFFUSION_REPO=${STABLE_DIFFUSION_REPO:-https://github.com/w-e-w/stablediffusion.git}
CLIP_ZIP=https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip
CI_COMMIT=bc07ce62c179d3aab3053a623d96a071101d11cb          # pharmapsychotic/clip-interrogator (MIT)

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

clone_at() {  # url dir commit
  if [ ! -d "$2/.git" ]; then
    git init -q "$2"
    git -C "$2" remote add origin "$1"
  fi
  git -C "$2" fetch -q --depth 1 origin "$3"
  git -C "$2" -c advice.detachedHead=false checkout -q "$3"
  [ "$(git -C "$2" rev-parse HEAD)" = "$3" ] || { echo "$2 is not at $3" >&2; exit 1; }
  echo "$2 @ $3"
}

apply_patches() {  # repo dir, patch dir
  local p
  for p in "$2"/*.patch; do
    if git -C "$1" apply --reverse --check "$p" 2>/dev/null; then
      echo "already applied: $(basename "$p")"
    else
      git -C "$1" apply --whitespace=nowarn "$p" && echo "applied: $(basename "$p")"
    fi
  done
}

fetch() {  # url dest sha256 [bytes]
  if [ -s "$2" ] && [ "$(sha256 "$2")" = "$3" ]; then echo "ok    $2"; return 0; fi
  mkdir -p "$(dirname "$2")"
  curl -fL --retry 3 -sS -o "$2.part" "$1"
  local got; got=$(sha256 "$2.part")
  if [ "$got" != "$3" ]; then echo "SHA256 MISMATCH $1: $got (expected $3)" >&2; rm -f "$2.part"; exit 1; fi
  mv "$2.part" "$2"; echo "got   $2"
}

for step in $STEPS; do case $step in
clone)
  clone_at "$A1111_REPO" "$W" "$A1111_COMMIT"
  clone_at "$SAM_REPO" "$W/extensions/sd-webui-segment-anything" "$SAM_COMMIT"
  clone_at "$OCR_REPO" "$W/extensions/sd-webui-ocr" "$OCR_COMMIT"
  apply_patches "$W/extensions/sd-webui-segment-anything" "$HERE/patches/sd-webui-segment-anything"
  apply_patches "$W/extensions/sd-webui-ocr" "$HERE/patches/sd-webui-ocr"
  mkdir -p "$W/extensions/sd-webui-blur"
  cp -R "$HERE/extensions/sd-webui-blur/." "$W/extensions/sd-webui-blur/"
  echo "installed sd-webui-blur"
  # segment-anything: use its bundled GroundingDINO implementation (no compiled CUDA ops), as deployed.
  if [ ! -f "$W/config.json" ]; then
    printf '{\n    "sam_use_local_groundingdino": true\n}\n' > "$W/config.json"
  else
    "$PY" - "$W/config.json" <<'EOF'
import json, sys
p = sys.argv[1]; c = json.load(open(p)); c["sam_use_local_groundingdino"] = True
json.dump(c, open(p, "w"), indent=4)
EOF
  fi
  echo "config.json: sam_use_local_groundingdino = true" ;;

venv)
  [ -x "$W/venv/bin/python" ] || "$PY" -m venv "$W/venv"
  # openai/CLIP does not build under pip's isolated build with current setuptools; pre-install it
  # with the setuptools version the WebUI pins, without build isolation.
  "$W/venv/bin/python" -c "import clip" 2>/dev/null || {
    "$W/venv/bin/pip" install -q "setuptools==69.5.1" wheel
    "$W/venv/bin/pip" install -q --no-build-isolation "$CLIP_ZIP"; }
  # Versions recorded in the development environment for packages that the extension installers
  # would otherwise take at their latest release (they only install what is missing).
  # opencv-python decides the blur output of sd-webui-blur; onnxruntime-gpu runs the OCR models.
  "$W/venv/bin/pip" install -q "opencv-python==4.11.0.86" "onnxruntime-gpu==1.23.2" "segment-anything==1.0"
  # sd-webui-ocr imports lmdb but its installer does not list it.
  "$W/venv/bin/pip" install -q lmdb
  # The WebUI's installer: torch 2.1.2+cu121, requirements_versions.txt, repositories/ at their
  # pinned commits, extension installers; then exit.
  ( cd "$W" && python_cmd="$PY" venv_dir=venv bash ./webui.sh --skip-torch-cuda-test --exit --nowebui --api \
      --no-download-sd-model ) ;;

models)
  SAMX=$W/extensions/sd-webui-segment-anything/models
  # Stable Diffusion v1.5 (CreativeML OpenRAIL-M), used by /sdapi/v1/img2img (HeadFashion)
  fetch https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors \
        "$W/models/Stable-diffusion/v1-5-pruned-emaonly.safetensors" 6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa
  # SAM ViT-H (Apache-2.0), used by /sam/sam-predict
  fetch https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth \
        "$SAMX/sam/sam_vit_h_4b8939.pth" a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e
  # GroundingDINO SwinT-OGC (Apache-2.0), used by /sam/sam-predict with dino_enabled
  fetch https://huggingface.co/ShilongLiu/GroundingDINO/resolve/a94c9b567a2a374598f05c584e96798a170c56fb/groundingdino_swint_ogc.pth \
        "$SAMX/grounding-dino/groundingdino_swint_ogc.pth" 3b3ca2563c77c69f651d7bd133e97139c186df06231157a64c507099c52bc799
  # ESRGAN 4x (the WebUI's default ESRGAN_4x download), used by /sdapi/v1/extra-single-image
  fetch https://github.com/cszn/KAIR/releases/download/v1.0/ESRGAN.pth \
        "$W/models/ESRGAN/ESRGAN_4x.pth" 65fece06e1ccb48853242aa972bdf00ad07a7dd8938d2dcbdf4221b59f6372ce
  # BLIP captioner + CLIP ViT-L/14 + category lists, used by /sdapi/v1/interrogate (model "clip")
  fetch https://storage.googleapis.com/sfr-vision-language-research/BLIP/models/model_base_caption_capfilt_large.pth \
        "$W/models/BLIP/model_base_caption_capfilt_large.pth" 96ac8749bd0a568c274ebe302b3a3748ab9be614c737f3d8c529697139174086
  fetch https://openaipublic.azureedge.net/clip/models/b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836/ViT-L-14.pt \
        "$HOME/.cache/clip/ViT-L-14.pt" b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836
  CI=https://raw.githubusercontent.com/pharmapsychotic/clip-interrogator/$CI_COMMIT/clip_interrogator/data
  fetch "$CI/artists.txt"   "$W/interrogate/artists.txt"   01e4b30f6d7cfdb62f4582c5bec658e02d79bf9c19052949ce3336d6eff4d395
  fetch "$CI/flavors.txt"   "$W/interrogate/flavors.txt"   c99d83a7a435157339f3b60a34794c524de37159a9b72f3a2034df8245c4a2f1
  fetch "$CI/mediums.txt"   "$W/interrogate/mediums.txt"   91f26b9d0d7d93f8e30139a94f895ba5a97744033ec0b174539f3a88bc49cd2c
  fetch "$CI/movements.txt" "$W/interrogate/movements.txt" 16d60ecb48901885e877ca9243b3c32bc84a2477c4d3f0a1cf6d66086ce47483
  # PP-OCRv4 server detection + recognition, ONNX (Apache-2.0), used by /ocr/predict
  OCR=https://huggingface.co/spensercai/ppocr_v4_torch/resolve/5ac86e1097904916ff9af76a6ed9fdf6fa3420ee
  fetch "$OCR/ch_PP-OCRv4_server_det.onnx" "$W/models/ocr/ch_PP-OCRv4_server_det.onnx" 1fc804d5eb8021509160f7c580759ca58f5737e1b3e32260813fb057a1607e71
  fetch "$OCR/ch_PP-OCRv4_server_rec.onnx" "$W/models/ocr/ch_PP-OCRv4_server_rec.onnx" ce322ce7f5f1296b02d84b9414a2f014f54eca05d7560e27ecfc4cf3d8be085b
  ;;

hf)
  # Hugging Face files loaded by name at run time: the BERT text encoder of GroundingDINO and the
  # CLIP tokenizer/config of SD v1.5. (The revisions used in development were not recorded; these
  # are the current ones.)
  "$W/venv/bin/python" - <<'EOF'
from huggingface_hub import snapshot_download
print(snapshot_download("bert-base-uncased", revision="86b5e0934494bd15c9632b12f734a8a67f723594",
                        allow_patterns=["*.json", "*.txt", "model.safetensors"]))
print(snapshot_download("openai/clip-vit-large-patch14", revision="32bd64288804d66eefd0ccbe215aa642df71cc41",
                        allow_patterns=["*.json", "*.txt"]))
EOF
  ;;
*) echo "unknown step $step" >&2; exit 1 ;;
esac; done
echo "done: $W   (start with: bash $HERE/start.sh $DIR)"
