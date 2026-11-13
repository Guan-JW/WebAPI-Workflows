# HeadFashion

A headwear and hairstyle preview. A user uploads a photo of themselves and restyles the hat,
then the hair: the application segments the hat with a text prompt and inpaints a new one, then
segments the hair on the edited photo and inpaints a new hairstyle. One unit is one photo taken
through both edits (two dependent text-guided local edits on the same image).

| | |
|---|---|
| Domain | Image editing (text-guided segmentation + inpainting) |
| Source | Derived from image editing (headwear and hairstyle preview); built on AUTOMATIC1111 WebUI v1.10.1, sd-webui-segment-anything and Stable Diffusion v1.5 |
| Services | AUTOMATIC1111 WebUI v1.10.1 with sd-webui-segment-anything, self-hosted (`servers/a1111`) |
| Calls per unit | 4 |
| Inputs | Open Images V7 photos, 9 profiling / 20 test / 20 test2 |
| Unit | one photo (two edits) |

## Source

The workload is derived from image editing (headwear and hairstyle preview). The client, with its
prompts and parameters, is part of this suite; the services are upstream.

The same call pattern appears in public code, for example in [Auto-Photoshop-StableDiffusion-Plugin](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin/blob/6f6d4907adf0b6a6e562d084238f02ed6b7503c1/typescripts/sam/sam.tsx#L31-L45) and [Fashion-Model-Generation-with-Stable-Diffusion](https://github.com/ybai789/Fashion-Model-Generation-with-Stable-Diffusion/blob/e5059c9d334a0326a7cc2850f3f463f5cf495a35/service.py#L342); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

* Server: AUTOMATIC1111 stable-diffusion-webui, tag v1.10.1
  (`82a973c04367123ae98bd9abdf80d9eda9b910e2`, AGPL-3.0), unmodified; sd-webui-segment-anything
  at `982138cfb505de61a3cbb257b2fa9d461d9b5493` (no license file upstream) with
  `servers/a1111/patches/sd-webui-segment-anything/0002-dino-unload-after-call.patch`.
  Details and model files: `servers/a1111/README.md`, `source.json`.
* Models: Stable Diffusion v1.5 (`v1-5-pruned-emaonly`), SAM ViT-H, GroundingDINO SwinT-OGC.
* Client: `workflow.py`, a cleaned copy of the original client. The request
  sequence, request bodies and parameters are unchanged; this was checked against the original
  on a deterministic mock server (same method, path and body sha256 for every request, same
  output hashes).

Adaptations:

* The img2img seed is 1234 for both edits (`--inpaint-seed`), the value used in every
  development run. The original client, run on its own, sent -1 (a random seed per call).
* The photo comes from a manifest row instead of a fixed file path.
* Request-ID headers and the client's request logging were removed. They did not change request
  bodies.

## Workflow

| # | call | sends | returns | used by |
|---|---|---|---|---|
| 1 | `POST /sam/sam-predict` | photo (base64 of the file bytes), `dino_text_prompt` "hat", box threshold 0.3, GroundingDINO SwinT-OGC | `msg`, 3 masks, 3 mask previews, 3 masked images (PNG, base64) | mask 0 -> call 2 |
| 2 | `POST /sdapi/v1/img2img` | photo, hat mask, prompt "light, summery style, straw sunhat with a yellow ribbon"; 30 steps, CFG 7, denoising 0.75, 512 x 512, `inpainting_fill` 1, `inpaint_full_res` true, padding 32, `mask_blur` 4, seed 1234 | edited photo (PNG) | calls 3 and 4 |
| 3 | `POST /sam/sam-predict` | edited photo, prompt "hair", same settings as call 1 | as call 1 | mask 0 -> call 4 |
| 4 | `POST /sdapi/v1/img2img` | edited photo, hair mask, prompt "loose, light, summery hairstyle", same settings as call 2 | final photo (PNG) | output |

Every image travels inside the JSON bodies; in development the request bodies were 0.1 to 2.7 MB,
the `/sam/sam-predict` responses 2.9 to 9.0 MB and the img2img responses 0.9 to 2.7 MB per call. A call fails the unit if no mask or no
image comes back. The client writes the input, the masks, the previews and both edited photos to
its work directory, as the original application does.

## Inputs

Open Images V7 photos (validation and test subsets, boxes from the V5 release) that contain a
hat and a person, ordered with seed 20261033; each split keeps the candidates on which the
workflow completed in development. Rules, source hashes and dropped candidates:
`manifests/head_fashion/SELECTION.md`. Splits: 9 `profiling`, 20 `test`, 20 `test2`.
Annotations CC BY 4.0 (Google LLC); images CC BY 2.0 as listed by Open Images, with author and
Flickr page in each row. `prepare_data.py` downloads the photos from the public Open Images mirror
and checks their sha256.

## Deployment

`servers/a1111` (`setup.sh`, `start.sh`). The workload's default `--a1111-url` is
`http://127.0.0.1:7861`, the instance started with `DINO_UNLOAD_AFTER_CALL=1`, which served every
development run of this workload.

Stable Diffusion v1.5 and SAM stay on the GPU between requests. There are no caches in the
client and no response caches in the server. Development hardware: one NVIDIA A40 shared with
the other services of the suite; the client ran on a laptop that reached the server through an
SSH tunnel (90 to 120 ms for a trivial request). See `servers/a1111/README.md`.

## Measurement

The timed window runs from the first request to the final photo saved; reading and encoding the
input photo is outside it. Outputs, as returned by the server (base64-decoded PNG): `final_image`
(the result), `mask_hat`, `mask_hair` and `inpaint_hat` (the photo after the hat edit). No
`extra` fields.

Equivalence rule (`check.py`): `mask_hat` and `mask_hair` match with IoU >= 0.99 (binarised at
127); `final_image` matches inside the bounding box of the reference run's two masks, grown by
16 px: block SSIM (8 x 8, grayscale) >= 0.99 and at most 1 % of those pixels differ by more than
16 grey levels. Identical hashes always match. Exact hashes are not the right rule here: with
the seed fixed, SD inpainting on the GPU still gave a different `inpaint_hat` and `final_image`
in some rounds for 2 of the 20 `test` inputs in development.

The development runs used the runner's defaults: one warm-up round and three timed rounds, with the unit order reshuffled every round.

## Running

```bash
bash servers/a1111/setup.sh a1111 && bash servers/a1111/start.sh a1111 unload
pip install -r workloads/head_fashion/requirements.txt
python -I workloads/head_fashion/prepare_data.py
python workloads/head_fashion/run.py --split test --save-outputs runs/head_fashion/out \
    --out runs/head_fashion/test.jsonl
python -m wbench.summarize runs/head_fashion/test.jsonl
python workloads/head_fashion/check.py REF.jsonl runs/head_fashion/test.jsonl \
    --ref-outputs REF_OUT --cand-outputs runs/head_fashion/out
```

## Known limitations

* `profiling` has 9 inputs (only 9 of 15 candidates completed).
* Inputs were kept only if the workflow completed on the development server; the hair mask
  depends on the hat edit, so on other GPUs or versions some inputs may fail with
  "SAM hair failed".
* The upstream extension has no license file; the patch contains a few lines of its code as
  context.
* Server package versions (for example Pillow, which encodes the response PNGs) change output
  bytes; `servers/a1111/README.md` lists the development versions.
