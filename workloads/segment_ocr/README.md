# SegmentOCR

Reading a license plate from a low-quality camera frame. The application upscales a blurred
frame, checks that a car is present, segments the plate, crops it on the client and runs OCR on
the crop. One unit is one frame.

| | |
|---|---|
| Domain | Image understanding (segmentation + OCR) |
| Source | Derived from license-plate recognition; built on AUTOMATIC1111 WebUI v1.10.1, sd-webui-segment-anything, sd-webui-ocr (PP-OCRv4) and ESRGAN |
| Services | AUTOMATIC1111 WebUI v1.10.1 with sd-webui-segment-anything and sd-webui-ocr, self-hosted (`servers/a1111`) |
| Calls per unit | 4 (5 when the first plate query returns no mask) |
| Inputs | OpenALPR benchmark photos, blurred locally, 10 profiling / 20 test / 20 test2 |
| Unit | one frame |

## Source

The workload is derived from license-plate recognition. The client, with its prompts and
thresholds, is part of this suite; the services are upstream.

The same call pattern appears in public code, for example in [the CodeProject.AI ALPR module](https://github.com/codeproject/CodeProject.AI-ALPR/blob/450f6c96996e15069619237251db663b03f87d86/ALPR.py#L86); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

* Server: AUTOMATIC1111 stable-diffusion-webui, tag v1.10.1
  (`82a973c04367123ae98bd9abdf80d9eda9b910e2`, AGPL-3.0), unmodified; sd-webui-segment-anything
  at `982138cfb505de61a3cbb257b2fa9d461d9b5493` with patches `0001-sam-predict-output-mode` and
  `0002-dino-unload-after-call`; sd-webui-ocr at `5c75383ce6f0389e7d3521c5481f5bdddea8e167` with
  patch `0001-ocr-detection-parameters` (neither extension has a license file upstream).
  Details: `servers/a1111/README.md`, `source.json`.
* Models: ESRGAN 4x, SAM ViT-H, GroundingDINO SwinT-OGC, PP-OCRv4 server detection and
  recognition (ONNX).
* Client: `workflow.py`, a cleaned copy of the original client. The request
  sequence and bodies are unchanged; this was checked against the original on a deterministic
  mock server, including the retry path (same method, path and body sha256 for every request,
  same output hashes).

Adaptations:

* Inputs. The original application processed one blurred photo whose origin is not recorded. The
  benchmark uses photos of the OpenALPR benchmark set, blurred locally with a Gaussian of radius
  1.0 (see Inputs) to stand in for a low-quality frame.
* The frame comes from a manifest row instead of a fixed file path.
* Request-ID headers and the client's request logging were removed (they did not change request
  bodies).
* The client asks `/sam/sam-predict` for the selected mask only (`output_mode="mask_top1"`,
  `mask_index=0`), as the original client did; patch 0001 adds these fields to the upstream
  extension. The OCR thresholds are the ones deployed in development (patch for sd-webui-ocr).

## Workflow

| # | call | sends | returns | used by |
|---|---|---|---|---|
| 1 | `POST /sdapi/v1/extra-single-image` | frame (PNG), `upscaler_1` "ESRGAN_4x", `resize_mode` 0, `upscaling_resize` 2.0 | frame at 2x (PNG) | calls 2, 3, crop |
| 2 | `POST /sam/sam-predict` | 2x frame (PNG), prompt "car", box threshold 0.30, SAM ViT-H, `mask_top1` | `{"masks": [car mask]}` | stop if empty |
| 3 | `POST /sam/sam-predict` | 2x frame, prompt "license plate", box threshold 0.25, `mask_top1` | `{"masks": [plate mask]}` or `{}` | crop |
| 3b | `POST /sam/sam-predict` | only if call 3 returned no mask: same with prompt "plate" | plate mask | crop |
| - | client | bounding box of the plate mask (threshold 128) plus 8 px, crop of the 2x frame, PNG | | call 4 |
| 4 | `POST /ocr/predict` | `{"image": <crop PNG>}` | `{"result": [{"text", "box"}, ...]}` | output: texts joined by spaces |

Calls 2 and 3 each carry the full 2x frame (1.5 to 4.5 MB in development). The unit fails if
there is no car mask, no plate mask or no crop. The ESRGAN 4x model runs once and the WebUI
resizes its output to 2x. In development every unit used 4 calls. The client writes the 2x frame,
the mask overlays and the crop to its work directory, as the original application does.

## Inputs

The `endtoend/us` photos of https://github.com/openalpr/benchmarks at commit
`9790ed20d475be1e940a7e2a3f492a97c2ebed9b` with a non-empty ground-truth plate, ordered with seed
20261034. Each input is the photo converted to RGB, blurred with
`PIL.ImageFilter.GaussianBlur(radius=1.0)` and saved as PNG; `prepare_data.py` downloads the
JPEGs, checks their sha256, rebuilds the PNGs and checks those against the manifest. The PNG
hashes come from Pillow 12.1.0 and change with other Pillow versions. Each split keeps the
candidates on which the workflow returned a non-empty OCR text in development. Rules, the history
of the blur radius (2.0 was tried first) and dropped candidates: `manifests/segment_ocr/SELECTION.md`.
Splits: 10 `profiling`, 20 `test`, 20 `test2`. License: the repository is AGPL-3.0 and states no
separate license for the photos.

## Deployment

`servers/a1111` (`setup.sh`, `start.sh`). The workload's default `--a1111-url` is
`http://127.0.0.1:7861`, the instance started with `DINO_UNLOAD_AFTER_CALL=1`, which served every
development run of this workload.

SAM stays on the GPU between requests. The WebUI loads ESRGAN from disk for every upscale, and
sd-webui-ocr creates new ONNX Runtime sessions for every OCR call (upstream behaviour of both).
No caches in the client and no response caches in the server. Development hardware: one NVIDIA
A40 shared with the other services of the suite; the client ran on a laptop that reached the
server through an SSH tunnel (90 to 120 ms for a trivial request). See `servers/a1111/README.md`.

## Measurement

The timed window runs from the first request to the OCR text; decoding the frame and encoding it
for call 1 is outside it. Outputs: `ocr_text` (main, UTF-8), `car_mask`, `plate_mask`,
`plate_crop` (PNG bytes), `plate_bbox` (JSON `[x1, y1, x2, y2]` in the 2x frame, inclusive).
No `extra` fields.

Equivalence rule (`check.py`): `ocr_text` matches when it is equal after collapsing whitespace and
upper-casing; identical hashes always match. Masks can be added with `--outputs` (IoU >= 0.99).
In development every output was bit-identical across rounds.

The development runs used the runner's defaults: one warm-up round and three timed rounds, with the unit order reshuffled every round.

## Running

```bash
bash servers/a1111/setup.sh a1111 && bash servers/a1111/start.sh a1111 unload
pip install -r workloads/segment_ocr/requirements.txt      # Pillow 12.1.0 rebuilds the inputs exactly
python -I workloads/segment_ocr/prepare_data.py
python workloads/segment_ocr/run.py --split test --save-outputs runs/segment_ocr/out \
    --out runs/segment_ocr/test.jsonl
python -m wbench.summarize runs/segment_ocr/test.jsonl
python workloads/segment_ocr/check.py REF.jsonl runs/segment_ocr/test.jsonl \
    --ref-outputs REF_OUT --cand-outputs runs/segment_ocr/out
```

## Known limitations

* The inputs are derived (blurred) photos, not frames from a real camera pipeline, and the blur
  radius was chosen after a first selection pass at radius 2.0 left too few usable inputs.
* Input bytes depend on the Pillow version used by `prepare_data.py`; the client also re-encodes
  images with Pillow before sending them.
* The OCR text is not compared with the ground-truth plate; the ground truth is in the manifest
  rows for reference only.
* `/ocr/predict` responses are slightly smaller than in development (the development route also
  returned a `score` per item; see `servers/a1111/README.md`).
* The upstream extensions have no license files; the patches contain a few lines of their code as
  context.
