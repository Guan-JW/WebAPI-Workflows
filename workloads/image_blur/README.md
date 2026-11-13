# ImageBlur

Privacy-preserving photo sharing. Before a user publishes a photo, the application finds faces
and cars with text-prompted segmentation and blurs those regions. One unit is one photo: two
segmentation calls, a blur, and a composite of the blurred regions into the original.

| | |
|---|---|
| Domain | Image privacy filtering |
| Source | Derived from privacy-preserving photo sharing; built on AUTOMATIC1111 WebUI v1.10.1, sd-webui-segment-anything and the sd-webui-blur extension in this suite |
| Services | AUTOMATIC1111 WebUI v1.10.1 with sd-webui-segment-anything and sd-webui-blur, self-hosted (`servers/a1111`) |
| Calls per unit | 4 |
| Inputs | COCO val2017 images with people and cars, 10 profiling / 20 test / 20 test2 |
| Unit | one photo |

## Source

The workload is derived from privacy-preserving photo sharing. The client and the sd-webui-blur
extension are part of this suite; segmentation is upstream.

The same call pattern appears in public code, for example in [Auto-Photoshop-StableDiffusion-Plugin](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin/blob/6f6d4907adf0b6a6e562d084238f02ed6b7503c1/typescripts/sam/sam.tsx#L31-L45) and [celantur-arcgis-tools](https://github.com/celantur/celantur-arcgis-tools/blob/8a956486d3beaf40b491c535eb40147694e3a380/geoprocessing-toolbox/CelanturBlurringToolbox.pyt#L103-L158); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

* Server: AUTOMATIC1111 stable-diffusion-webui, tag v1.10.1
  (`82a973c04367123ae98bd9abdf80d9eda9b910e2`, AGPL-3.0), unmodified; sd-webui-segment-anything
  at `982138cfb505de61a3cbb257b2fa9d461d9b5493` (no license file upstream) with patches
  `0001-sam-predict-output-mode` and `0002-dino-unload-after-call`; sd-webui-blur from
  `servers/a1111/extensions/` (part of this suite; Apache-2.0). Details:
  `servers/a1111/README.md`, `source.json`.
* Models: SAM ViT-H, GroundingDINO SwinT-OGC. Blur and composite use OpenCV on the CPU.
* Client: `workflow.py`, a cleaned copy of the original client. The request
  sequence and bodies are unchanged; this was checked against the original on a deterministic
  mock server (same method, path and body sha256 for every request, same output hashes).

Adaptations:

* The original command-line application could ask the user to confirm before blurring
  (`--confirm`). That prompt is not part of the benchmark (it was not part of the measured runs
  either).
* The photo comes from a manifest row instead of a fixed file path.
* Request-ID headers and the client's request logging were removed (they did not change request
  bodies).
* The client asks `/sam/sam-predict` for the selected mask only (`output_mode="mask_top1"`,
  `mask_index=0`), as the original client did; patch 0001 adds these fields to the upstream
  extension, which would otherwise ignore them and return all nine images.

## Workflow

All calls go over one keep-alive session.

| # | call | sends | returns | used by |
|---|---|---|---|---|
| 1 | `POST /sam/sam-predict` | photo (decoded and re-encoded by the client: JPEG quality 95 for `.jpg`), prompt "human face", box threshold 0.3, SAM ViT-H, `mask_top1` | `{"masks": [face mask PNG]}` | union |
| 2 | `POST /sam/sam-predict` | same photo, prompt "car" | `{"masks": [car mask PNG]}` | union |
| - | client | union of the two masks (threshold 127), PNG | | call 4 |
| 3 | `POST /blur/generate` | same photo, `blur_ksize` 41, PNG | blurred photo (PNG) | call 4 |
| 4 | `POST /compose` | photo, blurred photo, union mask, PNG (default feather 7) | final photo (PNG) | output |

Calls 1 to 3 carry the same photo (0.12 to 0.23 MB in development); call 4 carries three images
(0.24 to 0.55 MB). A call fails the unit if the segmentation is empty or an image is missing. The
client writes the masks, the blurred photo and the final photo to its work directory, as the
original application does.

## Inputs

COCO 2017 validation images with at least one person and one car (largest person box at least
2 % of the image), ordered with seed 20261032; each split keeps the candidates on which the
workflow completed in development. Rules, source hashes and dropped candidates:
`manifests/image_blur/SELECTION.md`. Splits: 10 `profiling`, 20 `test`, 20 `test2`. COCO
annotations CC BY 4.0; images under the per-image Flickr license recorded in each row (some
NonCommercial or NoDerivs) and the Flickr Terms of Use. `prepare_data.py` downloads the images
from images.cocodataset.org and checks their sha256.

## Deployment

`servers/a1111` (`setup.sh`, `start.sh`). The workload's default `--a1111-url` is
`http://127.0.0.1:7861`, the instance started with `DINO_UNLOAD_AFTER_CALL=1`, which served every
development run of this workload.

SAM stays on the GPU between requests. No caches in the client and no response caches in the
server. The blur output depends on OpenCV being installed in the server venv (4.11.0.86 in
development; without it the extension falls back to a PIL blur with different pixels).
Development hardware: one NVIDIA A40 shared with the other services of the suite; the client ran
on a laptop that reached the server through an SSH tunnel (90 to 120 ms for a trivial request).
See `servers/a1111/README.md`.

## Measurement

The timed window runs from the first request to the final photo saved; reading and re-encoding
the input photo is outside it. Outputs (PNG bytes): `mask_face`, `mask_car`, `final_image`
(main), `mask_union`, `blurred`. No `extra` fields.

Equivalence rule (`check.py`): `mask_face` and `mask_car` match with IoU >= 0.99 (binarised at
127); `final_image` matches inside the bounding box of the reference run's two masks, grown by
16 px: block SSIM (8 x 8, grayscale) >= 0.99 and at most 1 % of those pixels differ by more than
16 grey levels. Identical hashes always match. In development every output was bit-identical
across rounds; the tolerance is for comparisons across hardware and versions.

The development runs used the runner's defaults: one warm-up round and three timed rounds, with the unit order reshuffled every round.

## Running

```bash
bash servers/a1111/setup.sh a1111 && bash servers/a1111/start.sh a1111 unload
pip install -r workloads/image_blur/requirements.txt
python -I workloads/image_blur/prepare_data.py
python workloads/image_blur/run.py --split test --save-outputs runs/image_blur/out \
    --out runs/image_blur/test.jsonl
python -m wbench.summarize runs/image_blur/test.jsonl
python workloads/image_blur/check.py REF.jsonl runs/image_blur/test.jsonl \
    --ref-outputs REF_OUT --cand-outputs runs/image_blur/out
```

## Known limitations

* The client re-encodes the photo with Pillow before sending it; another Pillow version changes
  the request bytes and can change the masks (`requirements.txt` pins the development version).
* Inputs were kept only if both segmentations returned a mask on the development server; on other
  GPUs or versions some may fail.
* The upstream segmentation extension has no license file; the patches contain a few lines of its
  code as context. sd-webui-blur still needs a license.
