# CaptionCompare: input selection

## Source

COCO 2017 validation images (val2017, 5,000 images), fetched from
`http://images.cocodataset.org/val2017/<id>.jpg` (`source_url` in each row). Image metadata,
licenses and the object counts in each row come from `instances_val2017.json` in
http://images.cocodataset.org/annotations/annotations_trainval2017.zip
(sha256 `113a836d90195ee1f884e704da6304dfaaecff1f023f49b6ca93c4aaae470268`).

## Rule

1. **Eligible**: every val2017 image (pool 5,000).
2. **Order**: sort the image ids, shuffle once with Python `random.Random(20261031)`, and cut
   consecutive candidate lists: 15 for `profiling`, 30 for `test`, 30 for `test2` (1.5 x the
   target of 10 / 20 / 20, rounded up). No download failed.
3. **Applicability**: every candidate was run once through this workload (3 requests, model
   `clip`) against the development server (the instance without `DINO_UNLOAD_AFTER_CALL`). A
   candidate is applicable when all three `/sdapi/v1/interrogate` calls return a non-empty caption.
4. **Selection**: each split keeps the first applicable candidates, in candidate order, up to its
   target.

Row fields `group` (name of the candidate list: `profiling`; `test1` = split `test`; `test2`) and
`order_idx` (position in that list) record where a row came from. No input appears in two splits.

| split | candidate list | candidates | applicable | selected | target |
|---|---|---|---|---|---|
| `profiling` | `profiling` | 15 | 15 | 10 | 10 |
| `test` | `test1` | 30 | 30 | 20 | 20 |
| `test2` | `test2` | 30 | 30 | 20 | 20 |

No candidate was dropped as not applicable.

## Row fields

`input_id` (`coco_<image id>`), `file` (relative to `data/caption_compare/`), `sha256`, `source`,
`source_url`, `flickr_url`, `width`, `height`, `license_id`, `license_name`, `license_url` (from
the COCO annotation file), `n_person`, `n_car` (non-crowd instances), `max_person_frac` (largest
person box over the image area; these three fields are informational here), `group`, `order_idx`.

## Licenses

COCO annotations: CC BY 4.0 (COCO Consortium). Images: Flickr photos under the per-image Creative
Commons license recorded in each row (several are NonCommercial and/or NoDerivs), and the Flickr
Terms of Use. The images are not redistributed here; `prepare_data.py` fetches them.
