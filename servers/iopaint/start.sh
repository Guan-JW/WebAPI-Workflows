#!/usr/bin/env bash
# Start one IOPaint server configured as for the workload's development runs.
#
#   bash servers/iopaint/start.sh OUTPUT_DIR [PORT]
#
# OUTPUT_DIR is IOPaint's --output-dir: with it set, the web client saves the
# final image through POST /api/v1/save_image, which the workload requires.
# PORT defaults to 8380.
#
# Optional environment variables:
#   VENV       venv made by setup.sh (default: servers/iopaint/.venv)
#   MODEL_DIR  same value as for setup.sh (default: ${XDG_CACHE_HOME:-$HOME/.cache})
#   HOST       bind address (default: 127.0.0.1)
#   DEVICE     cuda (default, as developed) or cpu (smoke tests only; outputs differ from cuda)
#
# The command is upstream's `iopaint start` with the flags below. One setting is
# applied before the CLI runs (see the launcher at the bottom): on CUDA GPUs of
# compute capability 8.0 or newer, IOPaint's vendored SAM 2 enables only the
# flash attention kernel, which has no fp32 path, so every interactive
# segmentation call fails ("No available kernel"). The launcher allows all
# scaled-dot-product-attention kernels, the same set upstream SAM 2 falls back
# to when flash attention fails. On CPU these flags are already set and the
# launcher changes nothing.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=${1:?usage: start.sh OUTPUT_DIR [PORT]}
PORT=${2:-8380}
VENV=${VENV:-$HERE/.venv}
MODEL_DIR=${MODEL_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}
HOST=${HOST:-127.0.0.1}
DEVICE=${DEVICE:-cuda}

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
# IOPaint reads its weights from the torch hub cache, $TORCH_HOME/hub/checkpoints.
export TORCH_HOME="$MODEL_DIR/torch"

exec "$VENV/bin/python" - start \
  --host "$HOST" --port "$PORT" \
  --model lama --model-dir "$MODEL_DIR" --device "$DEVICE" \
  --output-dir "$OUT" --quality 100 \
  --enable-interactive-seg --interactive-seg-model sam2_1_tiny --interactive-seg-device "$DEVICE" \
  --enable-realesrgan --realesrgan-model realesr-general-x4v3 --realesrgan-device "$DEVICE" \
  <<'PY'
import sys

from iopaint.plugins.segment_anything2.modeling.sam import transformer

transformer.OLD_GPU = transformer.MATH_KERNEL_ON = True  # allow every SDPA kernel (see start.sh)

from iopaint import entry_point  # noqa: E402

sys.argv[0] = "iopaint"
entry_point()
PY
