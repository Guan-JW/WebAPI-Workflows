#!/usr/bin/env bash
# Install the IOPaint server used by workloads/iopaint and fetch its model weights.
#
#   bash servers/iopaint/setup.sh
#
# Steps: fetch Sanster/IOPaint at the pinned commit, add a placeholder for the
# built web UI (not part of the git tree), create a venv, install PyTorch and
# IOPaint (editable), download the three model weights and check their hashes.
#
# Optional environment variables:
#   PYTHON          interpreter for the venv (default: python3.10)
#   VENV            venv directory (default: servers/iopaint/.venv)
#   SRC_DIR         upstream checkout (default: servers/iopaint/upstream/IOPaint)
#   MODEL_DIR       IOPaint's --model-dir; weights go to $MODEL_DIR/torch/hub/checkpoints
#                   (default: IOPaint's own default, ${XDG_CACHE_HOME:-$HOME/.cache})
#   TORCH_SPEC      pip arguments for PyTorch
#                   (default: CUDA 12.1 wheels of torch 2.4.1 / torchvision 0.19.1)
#   USE_CONSTRAINTS 1 (default) installs with constraints.txt; 0 lets pip resolve freely
#   SKIP_WEIGHTS    1 skips the weight download
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL=https://github.com/Sanster/IOPaint.git
COMMIT=61a759fb3f332bacdce8b2813f4837495c9b86e0   # IOPaint 1.6.0 (setup.py), 2025-04-29

PYTHON=${PYTHON:-python3.10}
VENV=${VENV:-$HERE/.venv}
SRC_DIR=${SRC_DIR:-$HERE/upstream/IOPaint}
MODEL_DIR=${MODEL_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}
TORCH_SPEC=${TORCH_SPEC:-"torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121"}
USE_CONSTRAINTS=${USE_CONSTRAINTS:-1}

echo "== 1/4 upstream source -> $SRC_DIR"
if [ ! -d "$SRC_DIR/.git" ]; then
  mkdir -p "$SRC_DIR"
  git -C "$SRC_DIR" init -q
  git -C "$SRC_DIR" remote add origin "$REPO_URL"
fi
if [ "$(git -C "$SRC_DIR" rev-parse -q --verify HEAD 2>/dev/null || true)" != "$COMMIT" ]; then
  git -C "$SRC_DIR" fetch -q --depth 1 origin "$COMMIT"
  git -C "$SRC_DIR" checkout -q --detach "$COMMIT"
fi
test "$(git -C "$SRC_DIR" rev-parse HEAD)" = "$COMMIT"
echo "IOPaint at $(git -C "$SRC_DIR" rev-parse HEAD)"

# The server mounts iopaint/web_app as static files and refuses to start if the
# directory is missing. The built web UI is published only in the PyPI wheel, not
# in the git tree. The benchmark client never loads it, so a placeholder page is
# enough. (To use the real UI in a browser, build web_app/ with npm and copy
# web_app/dist to iopaint/web_app, as upstream's publish.sh does.)
WEB="$SRC_DIR/iopaint/web_app"
if [ ! -e "$WEB/index.html" ]; then
  mkdir -p "$WEB"
  printf '<!doctype html><title>IOPaint</title><p>Web UI not built; this server is driven by the benchmark client.</p>\n' \
    > "$WEB/index.html"
fi

echo "== 2/4 venv -> $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
# shellcheck disable=SC2086
"$VENV/bin/python" -m pip install $TORCH_SPEC

echo "== 3/4 IOPaint (editable install of the pinned checkout)"
CONS=()
if [ "$USE_CONSTRAINTS" = 1 ] && [ -f "$HERE/constraints.txt" ]; then
  CONS=(-c "$HERE/constraints.txt")
fi
# setup.py reads requirements.txt from the working directory
(cd "$SRC_DIR" && "$VENV/bin/python" -m pip install -e . ${CONS[@]+"${CONS[@]}"})
"$VENV/bin/python" -m pip freeze --exclude-editable > "$VENV/freeze.txt"
"$VENV/bin/python" -c "import sys, torch, iopaint; print('python', sys.version.split()[0], 'torch', torch.__version__, 'cuda', torch.cuda.is_available())"

echo "== 4/4 model weights -> $MODEL_DIR/torch/hub/checkpoints"
if [ "${SKIP_WEIGHTS:-0}" = 1 ]; then
  echo "skipped (SKIP_WEIGHTS=1)"
  exit 0
fi
CK="$MODEL_DIR/torch/hub/checkpoints"
mkdir -p "$CK"
# name | md5 (the value IOPaint's code checks) | sha256 | URLs, first = the one in IOPaint's code.
# The second SAM 2.1 URL is the same checkpoint on Hugging Face (same md5 and sha256),
# used only if the first download fails.
WEIGHTS="
big-lama.pt|e3aa4aaa15225a33ec84f9f4bc47e500|344c77bbcb158f17dd143070d1e789f38a66c04202311ae3a258ef66667a9ea9|https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt
sam2.1_hiera_tiny.pt|6aa6761c9da74fbaa74b4c790a0a2007|7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69|https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt https://huggingface.co/facebook/sam2.1-hiera-tiny/resolve/main/sam2.1_hiera_tiny.pt
realesr-general-x4v3.pth|91a7644643c884ee00737db24e478156|8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292|https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
"
echo "$WEIGHTS" | while IFS='|' read -r name md5 sha urls; do
  [ -n "$name" ] || continue
  f="$CK/$name"
  for url in $urls; do
    [ -f "$f" ] && break
    if curl -fL --retry 3 -o "$f.part" "$url"; then
      mv "$f.part" "$f"
    else
      rm -f "$f.part"
      echo "download failed: $url"
    fi
  done
  [ -f "$f" ] || { echo "could not download $name"; exit 1; }
  "$VENV/bin/python" - "$f" "$md5" "$sha" <<'PY'
import hashlib, sys
path, md5, sha = sys.argv[1:4]
h_md5, h_sha = hashlib.md5(), hashlib.sha256()
with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h_md5.update(chunk)
        h_sha.update(chunk)
ok = h_md5.hexdigest() == md5 and h_sha.hexdigest() == sha
print(("ok      " if ok else "MISMATCH"), path, h_md5.hexdigest(), h_sha.hexdigest())
sys.exit(0 if ok else 1)
PY
done
echo "done. Start a server with: bash $HERE/start.sh <output_dir> [port]"
