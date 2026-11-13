# SegmentOCR: input selection

## Source

The `endtoend/us` set of the OpenALPR benchmarks repository, https://github.com/openalpr/benchmarks
at commit `9790ed20d475be1e940a7e2a3f492a97c2ebed9b`: 222 JPEG photos of US cars, each with a
ground-truth file `<file>\t<x>\t<y>\t<w>\t<h>\t<plate text>`. Each row's `source_url` points to
the JPEG at that commit and `source_sha256` is the JPEG's hash.

The inputs are **derived** from these photos: each JPEG is decoded, converted to RGB and blurred
with `PIL.ImageFilter.GaussianBlur(radius=1.0)`, then saved as PNG. `sha256` is the hash of that
PNG, made with Pillow 12.1.0 (field `blur` in every row). PNG bytes depend on the Pillow version;
`prepare_data.py` rebuilds the files and checks the hashes.

## Rule

1. **Eligible**: every `endtoend/us` JPEG whose ground-truth plate text is non-empty (pool 222).
2. **Order**: sort the file stems, shuffle once with Python `random.Random(20261034)`, and cut
   consecutive candidate lists: 15 for `profiling`, 30 for `test`, 30 for `test2` (1.5 x the
   target of 10 / 20 / 20, rounded up).
3. **Applicability**: every candidate was run once through this workload against the
   development server, the instance with `DINO_UNLOAD_AFTER_CALL=1`. A candidate is applicable
   when the upscale returns an image, `/sam/sam-predict` returns a mask for "car" and for
   "license plate" (or the retry "plate"), and the OCR text is non-empty.
4. **Selection**: each split keeps the first applicable candidates, in candidate order, up to its
   target.

Row fields `group` (name of the candidate list: `profiling`; `test1` = split `test`; `test2`) and
`order_idx` (position in that list) record where a row came from. No input appears in two splits.

| split | candidate list | candidates | applicable | selected | target |
|---|---|---|---|---|---|
| `profiling` | `profiling` | 15 | 15 | 10 | 10 |
| `test` | `test1` | 30 | 29 | 20 | 20 |
| `test2` | `test2` | 30 | 30 | 20 | 20 |

Dropped as not applicable: `test`: `alpr_us_wts-lg-000133` (OCR text empty).

**Blur radius.** The selection was first run with radius 2.0. At that radius only 9 of 15
`profiling` and 18 of 30 `test` candidates gave a non-empty OCR text (every failure was an empty
OCR result). The radius was then lowered to 1.0, with the same photos, ids, seed and order, and
the applicability step was repeated; the table above is the radius-1.0 result. All 50 manifest
rows were checked: re-blurring the source JPEG with radius 1.0 under Pillow 12.1.0 reproduces
the recorded `sha256` for every row, and radius 2.0 reproduces none.

## Row fields

`input_id` (`alpr_us_<stem>`), `file` (blurred PNG, relative to `data/segment_ocr/`), `sha256`
(of the PNG), `source`, `source_url`, `source_commit`, `source_sha256` (of the JPEG), `blur`
(method, radius, format, Pillow version), `width`, `height`, `gt_plate_text`, `gt_bbox_xywh` (the
repository's ground truth, in pixels of the original photo; not used by the workflow), `license`,
`group`, `order_idx`.

## Licenses

The repository is licensed AGPL-3.0 (GitHub license detection). Its README does not state a
separate license or source for the photos. The photos are not redistributed here;
`prepare_data.py` downloads them from GitHub and builds the blurred PNGs locally.
