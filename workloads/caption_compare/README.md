# CaptionCompare

Image captioning with repeated requests: one unit sends the same captioning request for the same
image three times. Despite the name, the workload does not compare different captions; all three
requests are identical.

| | |
|---|---|
| Domain | Image captioning |
| Source | Derived from image captioning; built on the interrogate endpoint of AUTOMATIC1111 WebUI v1.10.1 (BLIP, CLIP) |
| Services | AUTOMATIC1111 WebUI v1.10.1, self-hosted (`servers/a1111`) |
| Calls per unit | 3 |
| Inputs | COCO val2017 images, 10 profiling / 20 test / 20 test2 |
| Unit | one image (three requests) |

## Source

The workload is derived from image captioning. Its client is part of this suite; the service is the
`/sdapi/v1/interrogate` endpoint of AUTOMATIC1111 stable-diffusion-webui, tag v1.10.1
(`82a973c04367123ae98bd9abdf80d9eda9b910e2`, AGPL-3.0), unmodified. With model `clip` the WebUI
captions the image with BLIP and appends CLIP ViT-L/14 matches from four category lists (the
"CLIP interrogator"). Model files: `servers/a1111/README.md`, `source.json`.

The same call pattern appears in public code, for example in [Open WebUI](https://github.com/open-webui/open-webui/blob/f7ac7ee10962ddec0017f5c29b6740d9b9c5faca/backend/open_webui/utils/middleware.py#L3609); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

The client (`workflow.py`) is a cleaned copy of the original client. The request
sequence and bodies are unchanged; this was checked against the original on a deterministic mock
server (same method, path and body sha256 for every request, same output hash).

Adaptations: the image comes from a manifest row instead of a fixed file path; request-ID headers
and the client's request logging were removed (they did not change request bodies).

## Workflow

| # | call | sends | returns | used by |
|---|---|---|---|---|
| 1 | `POST /sdapi/v1/interrogate` | `{"image": <base64 of the file bytes>, "model": "clip"}` | `{"caption": ...}` | output |
| 2 | same as 1 | same body | caption | output |
| 3 | same as 1 | same body | caption | output |

The client reads and encodes the image once; each request carries the full image (0.08 to
0.39 MB in development). The calls run one after another, each on a new connection. The three
captions are written to `captions.txt` in the work directory. In every development run the
server returned the same caption to all three requests of a unit.

## Inputs

COCO 2017 validation images, ordered with seed 20261031; every candidate completed in
development. Rules and source hashes: `manifests/caption_compare/SELECTION.md`. Splits: 10
`profiling`, 20 `test`, 20 `test2`. COCO annotations CC BY 4.0; images under the per-image Flickr
license recorded in each row (some NonCommercial or NoDerivs) and the Flickr Terms of Use.
`prepare_data.py` downloads the images from images.cocodataset.org and checks their sha256.

## Deployment

`servers/a1111` (`setup.sh`, `start.sh`). The workload's default `--a1111-url` is
`http://127.0.0.1:7860`, the instance without `DINO_UNLOAD_AFTER_CALL`, which served every
development run of this workload (the switch does not affect this endpoint). Models: BLIP base
caption (capfilt large), CLIP ViT-L/14, clip-interrogator category lists. With the WebUI defaults,
BLIP and CLIP are moved to the GPU for every request and back to CPU memory afterwards; no
response caches in the server or the client. Development hardware: one NVIDIA A40 shared with the
other services of the suite; the client ran on a laptop that reached the server through an SSH
tunnel (90 to 120 ms for a trivial request). See `servers/a1111/README.md`.

## Measurement

The timed window runs from the first request to `captions.txt` written; reading and encoding the
image is outside it. Output: `captions` (the three captions joined with `\n`, UTF-8). `extra`:
`n_captions`. Equivalence rule: exact sha256 of `captions` (`python -m wbench.compare`); in
development every input gave the same hash in every round.

The development runs used the runner's defaults: one warm-up round and three timed rounds, with the unit order reshuffled every round.

## Running

```bash
bash servers/a1111/setup.sh a1111 && bash servers/a1111/start.sh a1111 default
pip install -r workloads/caption_compare/requirements.txt
python -I workloads/caption_compare/prepare_data.py
python workloads/caption_compare/run.py --split test --out runs/caption_compare/test.jsonl
python -m wbench.summarize runs/caption_compare/test.jsonl
python -m wbench.compare REF.jsonl runs/caption_compare/test.jsonl
```

`--repeat` and `--model` exist for experiments; the workload is defined with 3 and `clip`.

## Known limitations

* Captions can change with the GPU, the torch version or the WebUI interrogate settings (all
  defaults here).
