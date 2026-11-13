# IOPaint server

The self-hosted service of `workloads/iopaint`: upstream
[IOPaint](https://github.com/Sanster/IOPaint) 1.6.0 at commit
`61a759fb3f332bacdce8b2813f4837495c9b86e0` (Apache-2.0), unmodified, with
three models loaded.

| File | Purpose |
|---|---|
| `setup.sh` | fetch the pinned commit into `upstream/IOPaint`, create `.venv`, install PyTorch and IOPaint, download and check the weights |
| `start.sh` | start one server: `bash start.sh OUTPUT_DIR [PORT]` (default port 8380) |
| `constraints.txt` | package versions used by `setup.sh` (`USE_CONSTRAINTS=0` to resolve freely) |

## Set up and start

```bash
bash servers/iopaint/setup.sh                         # Linux + CUDA 12.1 wheels by default
bash servers/iopaint/start.sh runs/iopaint/server_out 8380
```

Both scripts read `VENV`, `MODEL_DIR` (default `${XDG_CACHE_HOME:-$HOME/.cache}`,
IOPaint's own default) and, for `setup.sh`, `PYTHON` (default `python3.10`),
`SRC_DIR` and `TORCH_SPEC` (default
`torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121`).
For a CPU smoke test on macOS (arm64):
`TORCH_SPEC="torch==2.4.1 torchvision==0.19.1" bash setup.sh`, then
`DEVICE=cpu bash start.sh OUT`.

The server is ready when its log prints `Uvicorn running on http://HOST:PORT`.
Model loading takes a few seconds.

## Configuration

`start.sh` runs upstream's `iopaint start` with:

| Option | Value | Note |
|---|---|---|
| `--model` | `lama` | erase model |
| `--device` | `cuda` | `DEVICE=cpu` for smoke tests |
| `--output-dir` | first argument | required: it turns on auto-saving, so the web client saves through `POST /api/v1/save_image` |
| `--quality` | `100` | default; encoder quality of returned images |
| `--enable-interactive-seg`, `--interactive-seg-model`, `--interactive-seg-device` | on, `sam2_1_tiny`, `cuda` | |
| `--enable-realesrgan`, `--realesrgan-model`, `--realesrgan-device` | on, `realesr-general-x4v3`, `cuda` | fp16 on CUDA (`no_half` false) |
| `--host`, `--port` | `127.0.0.1`, `8380` | `HOST`, second argument |
| `--model-dir` | `MODEL_DIR` | weights are read from `$MODEL_DIR/torch/hub/checkpoints` (`start.sh` sets `TORCH_HOME=$MODEL_DIR/torch`) |

All other options keep their defaults: no `--input`, no `--mask-dir`, remove-bg,
anime-seg, GFPGAN and RestoreFormer off, `low_mem`, `cpu_offload`,
`disable_nsfw_checker`, `local_files_only` false. One uvicorn process serves
all requests; the API endpoints run in its worker threads.

Two settings differ from a plain `pip install` + `iopaint start`:

1. **Placeholder web UI.** `iopaint/api.py` mounts `iopaint/web_app/` as static
   files and fails at start-up if the directory is missing. The built web UI
   ships only in the PyPI wheel; the git tree has its source (`web_app/`).
   `setup.sh` writes a one-line `index.html` there. The benchmark client never
   requests it. To use the real UI in a browser, build `web_app/` with npm and
   copy `web_app/dist` to `iopaint/web_app`, as upstream's `publish.sh` does.
2. **SAM 2 attention kernels.** IOPaint's vendored SAM 2
   (`iopaint/plugins/segment_anything2/utils/misc.py:get_sdpa_settings`) enables
   only the flash attention kernel on GPUs of compute capability 8.0 or newer
   with PyTorch 2.2 or newer. The flash kernel has no fp32 path, so every
   interactive segmentation call fails with "No available kernel". `start.sh`
   sets `OLD_GPU = MATH_KERNEL_ON = True` in
   `iopaint/plugins/segment_anything2/modeling/sam/transformer.py` before the
   CLI starts, which allows every kernel: the same set upstream SAM 2 falls
   back to when flash attention fails. No IOPaint file is changed. On CPU both
   flags are already true.

## Weights

`setup.sh` downloads these to `$MODEL_DIR/torch/hub/checkpoints/`, where
IOPaint looks for them, and checks md5 (the value IOPaint's code checks) and
sha256.

| File | URL | md5 | sha256 | License |
|---|---|---|---|---|
| `big-lama.pt` (205,669,692 B) | https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt | `e3aa4aaa15225a33ec84f9f4bc47e500` | `344c77bbcb158f17dd143070d1e789f38a66c04202311ae3a258ef66667a9ea9` | LaMa, Apache-2.0 |
| `sam2.1_hiera_tiny.pt` (156,008,466 B) | https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt, mirror https://huggingface.co/facebook/sam2.1-hiera-tiny/resolve/main/sam2.1_hiera_tiny.pt | `6aa6761c9da74fbaa74b4c790a0a2007` | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69` | SAM 2, Apache-2.0 |
| `realesr-general-x4v3.pth` (4,885,111 B) | https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth | `91a7644643c884ee00737db24e478156` | `8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292` | Real-ESRGAN, BSD-3-Clause |

On 2026-11-12 the certificate of `dl.fbaipublicfiles.com` had expired, so the
SAM 2.1 file came from the Hugging Face mirror; its md5 matches IOPaint's.

## State

All three models load at start-up and stay loaded. The InteractiveSeg plugin
keeps the embedding of the last segmented image. Saved images accumulate in
`OUTPUT_DIR`. The server is not safe for concurrent clients (see the
workload card); run one server per client. On an A100 40 GB, eight idle
servers used 6.8 GB of GPU memory.

## Versions used in development

Python 3.10 and PyTorch 2.4 with CUDA 12.1 wheels. The patch version was not
recorded; the line numbers in a development server traceback match torch
2.4.1, fastapi 0.108.0 (pinned by IOPaint) and starlette 0.32.0.post1. The
other packages were resolved at install time and not recorded. `constraints.txt` was resolved on 2026-11-12 (Python 3.10,
torch 2.4.1, macOS arm64) and used for the CPU smoke test.
