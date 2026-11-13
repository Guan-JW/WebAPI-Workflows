# AUTOMATIC1111 WebUI server (head_fashion, caption_compare, image_blur, segment_ocr)

One self-hosted HTTP server, the AUTOMATIC1111 Stable Diffusion WebUI in API-only mode, with three
extensions. It serves every call of the four workloads.

| component | source | pinned at | license | changes |
|---|---|---|---|---|
| stable-diffusion-webui | https://github.com/AUTOMATIC1111/stable-diffusion-webui | `82a973c04367123ae98bd9abdf80d9eda9b910e2` (tag v1.10.1) | AGPL-3.0 | none |
| sd-webui-segment-anything | https://github.com/continue-revolution/sd-webui-segment-anything | `982138cfb505de61a3cbb257b2fa9d461d9b5493` | no license file in the repository | `patches/sd-webui-segment-anything/0001`, `0002` |
| sd-webui-ocr | https://github.com/SpenserCai/sd-webui-ocr | `5c75383ce6f0389e7d3521c5481f5bdddea8e167` | no license file in the repository | `patches/sd-webui-ocr/0001` |
| sd-webui-blur | `extensions/sd-webui-blur/` (this directory) | | Apache-2.0 | part of this suite |

The upstream code is cloned at the commits above by `setup.sh`; only the patches are kept here.
The pinned commits were found by comparing the copies deployed in development with every commit
of the upstream repositories: outside the files listed below, the deployed copies are
byte-identical to these commits.

## Patches

* `sd-webui-segment-anything/0001-sam-predict-output-mode.patch`: two optional request fields on
  `POST /sam/sam-predict`. `output_mode` = `"all"` (default; the upstream response with `msg` and
  three each of `blended_images`, `masks`, `masked_images`), `"masks"` (only the three masks) or
  `"mask_top1"` (only the mask at `mask_index`, as `{"masks": [mask]}`, or `{}` when nothing is
  segmented). The ImageBlur and SegmentOCR clients send `output_mode="mask_top1"`,
  `mask_index=0`, as they did in development. HeadFashion does not send the fields and gets the
  upstream response.
* `sd-webui-segment-anything/0002-dino-unload-after-call.patch`: adds the `DINO_UNLOAD_AFTER_CALL`
  server option, set on the 7861 instance below.
* `sd-webui-ocr/0001-ocr-detection-parameters.patch`: the text-detection settings used in
  development (`det_limit_side_len` 960 -> 3200, `det_db_thresh` 0.3 -> 0.2, `det_db_box_thresh`
  0.6 -> 0.2, `det_db_unclip_ratio` 1.5 -> 2.5, `drop_score` 0.5 -> 0.2, `use_angle_cls` False ->
  True; the last one has no effect on `/ocr/predict`). They decide which text regions are kept and
  so the OCR text SegmentOCR returns.

## Instances used in development

One install, two server processes on the same GPU, started with the same flags:

| port | environment | served (baseline runs and input selection) |
|---|---|---|
| 7860 | (none) | caption_compare |
| 7861 | `DINO_UNLOAD_AFTER_CALL=1` | head_fashion, image_blur, segment_ocr |

The routing above is taken from the recorded URL of every measured request; the environment of
each process is taken from the process list recorded when the services started. The switch has no
effect on `/sdapi/v1/interrogate`, so caption_compare would behave the same on either instance.
The workloads' default `--a1111-url` follows this table.

## Set-up and start

```bash
bash servers/a1111/setup.sh a1111          # clone, patch, models (~12 GB), venv; no GPU needed
bash servers/a1111/start.sh a1111 both     # ports 7860 and 7861; or `unload` / `default`
curl http://127.0.0.1:7861/sam/heartbeat        # {"msg":"Success!"}
```

`setup.sh` runs four steps (`STEPS="clone models venv hf"`): clone the pinned code and apply the
patches, copy `extensions/sd-webui-blur`, write `config.json`; download the model files below and
check their sha256; create `webui/venv` with a few pinned pre-installs (`opencv-python==4.11.0.86`,
`onnxruntime-gpu==1.23.2`, `segment-anything==1.0`, `lmdb`, and openai/CLIP built without build
isolation) and run the WebUI's own installer (`webui.sh --skip-torch-cuda-test --exit --nowebui
--api --no-download-sd-model`, which installs torch 2.1.2+cu121, `requirements_versions.txt`, the
`repositories/` at their pinned commits and the extensions' requirements); prefetch
`bert-base-uncased` and the `openai/clip-vit-large-patch14` tokenizer files from the Hugging Face
hub. `STABLE_DIFFUSION_REPO` is set to `https://github.com/w-e-w/stablediffusion.git`, because the
repository the installer clones by default is no longer available; the mirror holds the pinned
commit `cf1d67a6`.

Launch command, as deployed (from the WebUI directory):

```bash
[DINO_UNLOAD_AFTER_CALL=1] venv_dir=venv bash webui.sh --skip-prepare-environment --nowebui --api \
    --server-name 127.0.0.1 --port 7860|7861
```

No other flags were used for the measured runs. `config.json` contains only
`"sam_use_local_groundingdino": true` (segment-anything uses its bundled GroundingDINO code, with
no compiled CUDA operators); every other WebUI setting is the default. The WebUI picked the
Doggettx cross-attention implementation; xformers and tcmalloc were not installed.

## Endpoints per workload

| workload | calls per unit |
|---|---|
| head_fashion | `POST /sam/sam-predict` (hat), `POST /sdapi/v1/img2img`, `POST /sam/sam-predict` (hair), `POST /sdapi/v1/img2img` |
| caption_compare | `POST /sdapi/v1/interrogate` x 3 (model `clip`) |
| image_blur | `POST /sam/sam-predict` (human face, `mask_top1`), `POST /sam/sam-predict` (car, `mask_top1`), `POST /blur/generate`, `POST /compose` |
| segment_ocr | `POST /sdapi/v1/extra-single-image`, `POST /sam/sam-predict` (car, `mask_top1`), `POST /sam/sam-predict` (license plate, `mask_top1`; once more with "plate" if empty), `POST /ocr/predict` |

`GET /sam/heartbeat` and `GET /blur/health` answer health checks.

## Models

| file (under `webui/` unless noted) | used by | bytes | sha256 | license |
|---|---|---|---|---|
| `models/Stable-diffusion/v1-5-pruned-emaonly.safetensors` (SD v1.5) | img2img | 4,265,146,304 | `6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa` | CreativeML OpenRAIL-M |
| `extensions/sd-webui-segment-anything/models/sam/sam_vit_h_4b8939.pth` (SAM ViT-H) | sam-predict | 2,564,550,879 | `a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e` | Apache-2.0 |
| `extensions/sd-webui-segment-anything/models/grounding-dino/groundingdino_swint_ogc.pth` | sam-predict | 693,997,677 | `3b3ca2563c77c69f651d7bd133e97139c186df06231157a64c507099c52bc799` | Apache-2.0 |
| `models/ESRGAN/ESRGAN_4x.pth` | extra-single-image | 66,929,193 | `65fece06e1ccb48853242aa972bdf00ad07a7dd8938d2dcbdf4221b59f6372ce` | not stated for the file (cszn/KAIR release asset; KAIR is MIT, ESRGAN is Apache-2.0) |
| `models/BLIP/model_base_caption_capfilt_large.pth` | interrogate | 896,081,425 | `96ac8749bd0a568c274ebe302b3a3748ab9be614c737f3d8c529697139174086` | BSD-3-Clause |
| `~/.cache/clip/ViT-L-14.pt` (CLIP ViT-L/14) | interrogate | 932,768,134 | `b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836` | MIT |
| `interrogate/{artists,flavors,mediums,movements}.txt` | interrogate | small | in `setup.sh` | MIT |
| `models/ocr/ch_PP-OCRv4_server_det.onnx` | ocr | 113,189,862 | `1fc804d5eb8021509160f7c580759ca58f5737e1b3e32260813fb057a1607e71` | Apache-2.0 |
| `models/ocr/ch_PP-OCRv4_server_rec.onnx` | ocr | 90,377,463 | `ce322ce7f5f1296b02d84b9414a2f014f54eca05d7560e27ecfc4cf3d8be085b` | Apache-2.0 |

Download URLs (pinned revisions) are in `setup.sh`. Every sha256 above equals the hash recorded
for the file on the development server. Also loaded by name from the Hugging Face hub:
`bert-base-uncased` (GroundingDINO text encoder) and the `openai/clip-vit-large-patch14`
tokenizer/config (SD v1.5); their revisions in development were not recorded.

## What stays loaded

* SD v1.5 is loaded at start-up and stays on the GPU.
* SAM ViT-H is loaded on the first `/sam/sam-predict` call and stays on the GPU.
* GroundingDINO: per instance; the 7861 instance runs with `DINO_UNLOAD_AFTER_CALL=1`.
* ESRGAN_4x is loaded from disk on every `/sdapi/v1/extra-single-image` call (WebUI behaviour). A
  resize factor of 2 runs the 4x model once and resizes the result to 2x (rounded down to a
  multiple of 8) with Lanczos; tiles of 192 px, overlap 8 (defaults).
* The OCR models: a new ONNX Runtime session for detection and recognition is created on every
  `/ocr/predict` call (sd-webui-ocr behaviour).
* BLIP and CLIP are moved to the GPU for each `/sdapi/v1/interrogate` call and back to CPU memory
  after it (WebUI default `interrogate_keep_models_in_memory = false`).
* No server-side response caches.

## Hardware and software in development

* One NVIDIA A40 (46,068 MiB visible), driver 595.71.05; AMD EPYC 7763 host, RHEL 9.6, 16 CPU
  cores and 60 GB RAM allocated. Both instances ran on this one GPU, together with the services of
  other workloads of this suite. GPU memory used on the whole card, sampled every 15 s, peaked at
  14.9 to 19.2 GB in the five sessions of measured runs. VRAM of a single instance was not
  measured separately.
* Server venv: Python 3.10.22, torch 2.1.2+cu121, torchvision 0.16.2+cu121, Pillow 9.5.0,
  numpy 1.26.2, opencv-python 4.11.0.86, onnxruntime-gpu 1.23.2, transformers 4.30.2,
  fastapi 0.94.0, pydantic 1.10.27, gradio 3.41.2, segment-anything 1.0, uvicorn 0.54.0.
  Server Pillow encodes the PNGs in the responses, so a different version changes response bytes.
* The clients ran on a different machine (a macOS laptop, Python 3.10.18) and reached the server
  through an SSH tunnel; a trivial request (`GET /sam/heartbeat`) took 90 to 120 ms (median of 20
  probes, per session). Measured latencies include this network path.
* The measured units of these workloads were interleaved, unit by unit, with other experiments
  that sent requests to the same instances and GPU (one request in flight at a time).

## Differences from the development deployment

The release drops research instrumentation and code not used by these workloads. None of the
following changes a request a client sends; only the `/ocr/predict` item changes response bytes.

* The development WebUI was v1.10.1 plus tracing in `modules/api/api.py` (a middleware that read
  every request body and wrote a log record, and per-endpoint trace records; the records went to
  `/dev/null` in the measured runs) and `export XFORMERS_VERBOSE=1` in `webui.sh`. The release
  uses unmodified v1.10.1.
* The development segment-anything copy had the same trace records, debug prints, a timing
  wrapper around `sam_predict` with the same computation, and further routes not used here. Its
  model loader skipped the cache clear before loading GroundingDINO when fewer than two models
  were cached; patch 0002 skips it only while the switch is on, which is the same behaviour for
  these workloads (one GroundingDINO model).
* The development `/ocr/predict` route was a modified version that added a `score` field to each
  result item and re-encoded the decoded image as PNG before OCR (the pixels OCR sees are the
  same). The release uses the upstream route, so each item has only `text` and `box`, and the
  response is roughly 15-20 bytes shorter per detected text.
* sd-webui-blur in development had three script files that registered the same routes; the one
  that served the requests is the one released here, without its trace records. Its image code
  is identical (checked function by function).
