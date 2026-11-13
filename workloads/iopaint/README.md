# IOPaint

A user of IOPaint's web UI opens a photo and removes three objects from it.
For each object they choose the interactive segmentation tool, click once on
the object, accept the mask and erase the object. They then upscale the result
2x with the RealESRGAN plugin and save it. One unit is one such session: 11
HTTP requests to one IOPaint server, with the canvas held by the client and
sent back to the server at every step.

| | |
|---|---|
| Domain | Image editing: object removal, upscaling |
| Source | Sanster/IOPaint 1.6.0 at `61a759fb` (Apache-2.0), server run unmodified |
| Services | IOPaint 1.6.0 server, self-hosted: LaMa, SAM 2.1 tiny, Real-ESRGAN realesr-general-x4v3 |
| Calls per unit | 11: 2 page-load GETs, gen-info, 3 x (segment, erase), upscale, save |
| Inputs | COCO 2017 val, 5 profiling / 25 test |
| Unit | one session |

## Source

Upstream: [Sanster/IOPaint](https://github.com/Sanster/IOPaint) at commit
`61a759fb3f332bacdce8b2813f4837495c9b86e0` (2025-04-29, version 1.6.0 in
`setup.py`), Apache-2.0. The server is upstream code, unmodified, installed
from a checkout of that commit (`servers/iopaint/`). The workflow is the one a
user performs in IOPaint's own web UI; no step is added or removed.

Adaptations:

1. **Headless client.** The browser app (React, `web_app/src`) is replaced by
   `iopaint_web.py`, a Python port of its request path, so that sessions can
   run without a browser. The port reimplements the store actions
   (`lib/states.ts`), the API functions (`lib/api.ts`), the canvas helpers
   (`lib/utils.ts`) and the event handlers the session uses (`App.tsx`,
   `Workspace.tsx`, `Editor.tsx`, `Plugins.tsx`, `InteractiveSeg.tsx`). Each
   function cites the upstream lines it mirrors; the table under Workflow
   maps every request. Browser objects are modelled with bytes and Pillow: a
   `File` is bytes, a name and a MIME type; an image element keeps the bytes
   it was loaded from; a canvas is a Pillow RGBA bitmap.
2. **Requests the port does not send.** The static web UI (HTML, JS, CSS),
   the socket.io connection that the UI's progress bar opens on load (used
   only for progress events of generative models), and two
   page-load GETs whose responses no later request uses:
   `GET /api/v1/inputimage` (`App.tsx:28`, `hooks/useInputImage.tsx:12`; it
   returns no image when the server has no `--input`) and the Settings
   dialog's own `GET /api/v1/server-config` (`Settings.tsx:97-104`). The
   browser issues its page-load requests concurrently; the port sends
   server-config, then model.
3. **Two settings defaults.** These are kept as in the client the workload was
   developed and measured with, so that the request bodies match those runs.
   The browser sends `negative_prompt` = its 283-character default
   (`lib/const.ts:22-23`); the port sends `""`. The browser replaces
   `controlnetMethod` with server-config's value (null for LaMa,
   `lib/states.ts:797-803`) and sends `"controlnet_method": ""`; the port sends
   `"lllyasviel/control_v11p_sd15_canny"`. LaMa uses neither field, so the
   images are the same; a browser's `/inpaint` body is 249 bytes larger.
4. **Byte-level encoding.** The mask is a PNG encoded by the client's Pillow,
   not by a browser canvas, and multipart bodies use `requests`' framing, not
   the browser's `FormData`. The mask's compressed size also depends on the
   Pillow build: with Pillow 11.3.0, the x86_64 wheel (zlib) and the arm64
   wheel (zlib-ng) gave `/inpaint` bodies 64 to 400 bytes apart, with
   identical pixels and identical server responses. The port has not been
   compared request by request against a real browser.
5. **Erase button.** In the stock UI the toolbar's "Run Inpainting" button
   (`Editor.tsx:996-1008`) is shown when Settings > "Enable manual inpainting"
   is on (`Settings.tsx:403`); the scenario assumes the user turned it on. The
   setting stays in the browser and is not sent; the port calls
   `runInpainting()` as the button does.
6. **Server start-up** (details in `servers/iopaint/README.md`): a placeholder
   `iopaint/web_app/index.html`, because the built web UI is not in the git
   tree and the server will not start without that directory; and all
   scaled-dot-product-attention kernels allowed in IOPaint's vendored SAM 2,
   without which interactive segmentation fails on CUDA GPUs of compute
   capability 8.0 or newer. The server is started with upstream's
   `iopaint start`. The development runs built the same configuration in a
   small Python launcher: the configuration it printed equals the one
   `start.sh` prints, field by field (checked on CPU, where only the device
   fields and the output path differed). That launcher also served
   measurement-only routes, which this release does not include and the
   workload never calls.
7. **Saved-file check.** The development harness read the saved file back
   through such a route. Here `run.py` reads it from the server's output
   directory when that directory is reachable (`--server-output-dir`),
   outside the timed window.

## Workflow

The client keeps the canvas: every render the server returns. Each request
that works on "the current canvas" uploads the last render again as a data
URL.

| # | Request | Sent | Returned | Used by | Upstream (port) |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/server-config` | - | JSON; `enableAutoSaving: true` because the server has `--output-dir` | step 11 (save through the server) | `App.tsx:42-52`, `api.ts:105-108` (`WebApp.mount`) |
| 2 | `GET /api/v1/model` | - | JSON model info (lama) | editor settings | `Workspace.tsx:17-23`, `api.ts:122-125` (`WebApp.mount`) |
| 3 | `POST /api/v1/gen-info` | multipart: the photo (JPEG) | prompt and negative prompt from image metadata (empty for these photos) | settings | `states.ts:922-951`, `api.ts:217-222` (`Store.setFile`) |
| 4, 6, 8 | `POST /api/v1/run_plugin_gen_mask` | JSON: `name: InteractiveSeg`, `image`: data URL of the current canvas (the photo, then the previous erase result), `clicks: [[x, y, 1, 0]]` | PNG mask (RGBA) | Accept adds it to the masks of the next erase | `Plugins.tsx:78-84`, `Editor.tsx:442-454`, `:381-405`, `:210-217`, `api.ts:127-153` |
| 5, 7, 9 | `POST /api/v1/inpaint` | JSON: `image`: data URL of the current canvas, `mask`: PNG data URL of the accepted mask, and the settings fields (`sd_seed: -1`, `hd_strategy: Crop`, ...) | JPEG (the input's format, quality 100), `X-Seed` header | the next segmentation and erase; after the third, the upscale | Accept `InteractiveSeg.tsx:67-73` + `states.ts:894-905`; Erase `states.ts:422-564`, `api.ts:28-103` |
| 10 | `POST /api/v1/run_plugin_gen_image` | JSON: `name: RealESRGAN`, `image`: data URL of the last erase result, `scale: 2` | PNG at 2x size | step 11 | `Plugins.tsx:96-99`, `states.ts:566-618`, `:406-420`, `api.ts:127-153` |
| 11 | `POST /api/v1/save_image` | multipart: the PNG from step 10, under the photo's file name, type `image/jpeg` | empty | the server writes it unchanged to `OUTPUT_DIR/<file name>` | `Editor.tsx:527-549`, `api.ts:195-215` (`WebApp.download`) |

Notes:

- Data URLs carry the opened file's MIME type (`image/jpeg`) for every render,
  as in the browser. The saved file is a PNG under the photo's `.jpg` name
  (upstream behaviour).
- The server keeps no per-session state. It keeps the last segmented image's
  embedding (the InteractiveSeg plugin skips `set_image` when the same image
  string arrives again). In this workload consecutive segmentation calls never
  carry the same image, so this cache never hits.
- In development, one session moved about 3.9 MB up and 3.0 MB down (test
  split medians).

## Inputs

COCO 2017 val photos, each with three non-overlapping objects of 2-15 % of the
image area, and one click per object at the interior point farthest from the
object's boundary (distance-transform maximum of the instance mask). Selection
rule, exclusions and seed (`random.Random(20261103)`):
`manifests/iopaint/SELECTION.md`. Splits: 5 `profiling`, 25 `test`; there is
no validation split. Annotations are CC BY 4.0; each photo keeps its Flickr
license (manifest fields `license_name`, `license_url`), several of which are
NonCommercial or NoDerivs. `prepare_data.py` fetches the photos from
`images.cocodataset.org` and checks their sha256; the clicks are in the
manifest.

## Deployment

- **Service:** one IOPaint server (`servers/iopaint/start.sh OUTPUT_DIR
  [PORT]`) per client process. Configuration: `--model lama --device cuda
  --quality 100 --output-dir DIR --enable-interactive-seg
  --interactive-seg-model sam2_1_tiny --interactive-seg-device cuda
  --enable-realesrgan --realesrgan-model realesr-general-x4v3
  --realesrgan-device cuda`; every other option at its default (no input
  directory, no other plugins, `no_half` false).
- **Models:** LaMa (`big-lama.pt`, TorchScript, fp32), SAM 2.1 Hiera tiny
  (`sam2.1_hiera_tiny.pt`, fp32), Real-ESRGAN `realesr-general-x4v3.pth` (fp16
  on CUDA, 512-pixel tiles). URLs, md5 and sha256: `servers/iopaint/setup.sh`
  and `source.json`. All three load at start-up and stay loaded.
- **Caches and files:** the SAM 2 embedding of the last segmented image (per
  server process, see above). Saved images accumulate in the output
  directory; `run.py --server-output-dir` deletes a session's file before the
  session.
- **Development hardware:** server on one NVIDIA A100-SXM4-40GB with 16 CPU
  cores and 64 GB RAM allocated (Linux, Python 3.10, PyTorch 2.4 with CUDA
  12.1 wheels; the exact patch version was not recorded). Client on an Apple
  Mac (Python 3.11, `requirements.txt`), reaching the server through an SSH
  tunnel: median round trip 43-53 ms and 4.6-21 MB/s, depending on the day.
- **CPU:** `DEVICE=cpu` runs the same session for a smoke test (about 12 s per
  session on an Apple M4 Pro). CPU outputs differ from CUDA outputs.

## Measurement

- **Timed window:** from the page load (step 1) to the response of the save
  request (step 11), including the client's own work: base64 encoding, mask
  generation, image decoding. Reading the photo from disk, opening the HTTP
  session (a fresh `requests.Session` per unit, like a fresh page) and the
  saved-file check are outside it.
- **Output:** `saved_image`, the bytes sent to `/api/v1/save_image`. The
  server writes them unchanged (`api.py:186-203`); with
  `--server-output-dir` the run fails if the file on disk differs.
- **Equivalence rule:** the saved image bytes are identical
  (`python -m wbench.compare ref.jsonl cand.jsonl --outputs saved_image`).
  Compare runs on the same deployment: outputs differ between CPU and CUDA,
  and may differ between GPU models or library versions. In development,
  repeated sequential runs on A100 servers gave byte-identical saved images
  across rounds, days and machines.
- **Reference numbers from development** (test split, 25 photos x 3 rounds,
  sequential): p50 4575 ms, p95 6198 ms over a tunnel with about 50 ms round
  trip and 4.7 MB/s; p50 2059 ms with the client on the GPU host. Latency
  depends strongly on the network path, so record it (`python -m wbench.probe
  http://HOST:PORT/api/v1/model --upload-mb 2`).

## Running

```bash
# server host (GPU)
bash servers/iopaint/setup.sh
bash servers/iopaint/start.sh runs/iopaint/server_out 8380

# client
python3 -m venv .venv-iopaint
.venv-iopaint/bin/pip install -r workloads/iopaint/requirements.txt
.venv-iopaint/bin/python workloads/iopaint/prepare_data.py
.venv-iopaint/bin/python workloads/iopaint/run.py --split test --dry-run      # list units and requests
.venv-iopaint/bin/python workloads/iopaint/run.py --split test \
    --iopaint-url http://127.0.0.1:8380 \
    --server-output-dir runs/iopaint/server_out      # only if the client can read the server's output dir
.venv-iopaint/bin/python -m wbench.summarize runs/iopaint/test_*.jsonl
```

Client concurrency, one server per client (see Known limitations):

```bash
for i in 0 1 2 3; do bash servers/iopaint/start.sh runs/iopaint/server_out_$i $((8380 + i)) & done
.venv-iopaint/bin/python -m wbench.closed_loop iopaint --clients 4 --split test -- \
    --iopaint-url http://127.0.0.1:8380,http://127.0.0.1:8381,http://127.0.0.1:8382,http://127.0.0.1:8383
```

Client `i` uses the `i`-th URL (modulo the list length). `--unique-names`
gives every session its own file name, for deployments where sessions could
share an output directory.

## Known limitations

- **The IOPaint server is not safe for concurrent clients** (observed with the
  upstream server). Its endpoints are plain functions that FastAPI runs in a
  thread pool, and they share the SAM 2 predictor (`set_image`, then
  `predict`), the RealESRGAN helper (it keeps the current input and output in
  instance attributes) and the LaMa model without a lock (`Api.queue_lock` is
  created but never used). With C closed-loop clients on one shared server
  (A100):

  | C | timed sessions | failed (HTTP 500) | completed with a wrong image | correct |
  |---|---|---|---|---|
  | 1 | 16 | 0 | 0 | 16 |
  | 2 | 16 | 1 | 0 | 15 |
  | 4 | 16 | 6 | 5 | 5 |
  | 8 | 32 | 19 | 10 | 3 |

  "Wrong" means not byte-identical to the sequential run of the same photo
  (SSIM 0.87-0.95). Server errors included "An image must be set with
  .set_image(...) before mask prediction." (SAM 2), tensor size mismatches
  in RealESRGAN, and "'NoneType' object is not subscriptable". A run on
  another day showed the same pattern (C = 2: 2 failed; C = 4: 3 failed, 5
  wrong; C = 8: 16 failed, 12 wrong). **Deploy one server per client**, as
  above; IOPaint is a single-user application. With one server per client,
  all on the same A100, every session at C = 1, 2, 4 and 8 was correct (80 of
  80) and throughput grew from 0.36 to 2.37 sessions/s; eight idle servers
  used 6.8 GB of GPU memory. (Holding a lock around each model call inside
  one server also made every session correct, but capped that server at
  about 1 session/s; this release does not include such a change.)
- The port follows the upstream client's code, not a recording of a browser;
  see Source items 2-5 for what differs.
- On 2026-11-12 the TLS certificate of `dl.fbaipublicfiles.com`, the SAM 2.1
  URL in IOPaint's code, had expired (2026-11-11). `setup.sh` then falls back
  to the same file on Hugging Face (same md5 and sha256).
- The development server's exact Python package versions were not recorded.
  `servers/iopaint/constraints.txt` pins a set resolved later from the same
  requirements.
