# iopaint inputs: selection

Photos from COCO 2017 val, each with three objects to remove and one click
per object. The rule was fixed before any session on these inputs was run.

## Source

- Images: `http://images.cocodataset.org/val2017/<file_name>` (COCO's `coco_url`).
- Annotations: `instances_val2017.json` from
  `http://images.cocodataset.org/annotations/annotations_trainval2017.zip`
  (sha256 `113a836d90195ee1f884e704da6304dfaaecff1f023f49b6ca93c4aaae470268`,
  252,907,541 bytes, as downloaded on 2026-11-12). Only needed to re-derive the
  selection; the workload itself reads the clicks from the manifest.

## Rule

1. Candidate instance: `iscrowd = 0`, polygon segmentation (RLE masks are
   skipped), and annotation `area` between 2 % and 15 % of `width x height`,
   both bounds inclusive.
2. For each image with at least 3 candidates: sort its candidates by `area`,
   largest first (ties: lower annotation id). Rasterize each polygon set at
   image resolution (Pillow `ImageDraw.polygon`, fill 255). Take an instance if
   its mask shares no pixel with the masks already taken; stop at 3. The image
   qualifies if 3 instances are taken.
3. Exclusions: the 30 images of an earlier single-object version of this
   workload, image ids 7977, 25603, 33759, 69795, 82765, 89697, 125778, 145020,
   163257, 163682, 182923, 200961, 201676, 206838, 226147, 235241, 262895,
   281759, 320642, 410612, 424349, 439180, 482800, 491366, 500257, 502229,
   534394, 545129, 560256, 575500.
4. Order and split: the qualifying image ids (693) are sorted ascending and
   shuffled with Python's `random.Random(20261103).shuffle`. Positions 0-4 are
   `profiling`, positions 5-29 are `test`. The rest are unused.
5. Click per instance: `cv2.distanceTransform(mask, cv2.DIST_L2, 5)`, then the
   first maximum in row-major order (`numpy.argmax`), as integer pixel
   coordinates `[x, y]`: the interior point farthest from the instance
   boundary. Clicks are listed in the order the instances were taken (largest
   first), which is the order the session removes them in.

Re-running this rule on the annotation file above reproduces every row of
`profiling.jsonl` and `test.jsonl` (checked on 2026-11-12: 1,174 images with at
least 3 candidates after the exclusions, 693 qualifying, all 30 rows equal).

## Splits

| Split | Rows | Use |
|---|---|---|
| `profiling` | 5 | inputs a tool may observe; in development, validation runs also used these |
| `test` | 25 | held out; report results here |

There is no separate validation split.

## Row fields

| Field | Meaning |
|---|---|
| `input_id` | `coco-<12-digit image id>` |
| `file` | path under `data/iopaint/` written by `workloads/iopaint/prepare_data.py` |
| `url`, `sha256` | download URL and sha256 of the original JPEG |
| `dataset` | `COCO 2017 val` |
| `license`, `license_name`, `license_url` | the image's COCO license id and its entry in COCO's license table |
| `image_id`, `file_name`, `width`, `height` | from COCO |
| `split`, `idx` | split, and position in the seeded shuffle (step 4) |
| `clicks` | one `[x, y]` per object, in removal order; `click` repeats the first one |
| `objects` | per object: COCO annotation id, category, area fraction (rounded to 4 digits) |

## Licenses

COCO annotations are CC BY 4.0. Each image keeps its Flickr license (field
`license_name`): of the 30 images, 10 are Attribution-NonCommercial-ShareAlike,
2 Attribution-NonCommercial, 9 Attribution-NonCommercial-NoDerivs,
3 Attribution, 3 Attribution-ShareAlike, 3 Attribution-NoDerivs (all CC 2.0).
The repository lists the images and does not redistribute them. The workload
produces edited versions of the photos; for NoDerivs images, do not publish
those outputs.
