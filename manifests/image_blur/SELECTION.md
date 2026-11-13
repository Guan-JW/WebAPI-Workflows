# ImageBlur: input selection

## Source

COCO 2017 validation images (val2017), fetched from
`http://images.cocodataset.org/val2017/<id>.jpg` (`source_url` in each row). The eligibility rule
uses `instances_val2017.json` from
http://images.cocodataset.org/annotations/annotations_trainval2017.zip
(sha256 `113a836d90195ee1f884e704da6304dfaaecff1f023f49b6ca93c4aaae470268`).

## Rule

1. **Eligible**: at least one non-crowd `person` and at least one non-crowd `car` instance, and
   the largest person box covers at least 2 % of the image area. Pool: 219 of 5,000 images.
2. **Order**: sort the image ids, shuffle once with Python `random.Random(20261032)`, and cut
   consecutive candidate lists: 15 for `profiling`, 30 for `test`, 30 for `test2` (1.5 x the
   target of 10 / 20 / 20, rounded up). No download failed.
3. **Applicability**: every candidate was run once through this workload (blur kernel 41)
   against the development server, the instance with `DINO_UNLOAD_AFTER_CALL=1`. A candidate is
   applicable when both `/sam/sam-predict` calls ("human face", "car") return a mask and
   `/blur/generate` and `/compose` return an image.
4. **Selection**: each split keeps the first applicable candidates, in candidate order, up to its
   target.

Row fields `group` (name of the candidate list: `profiling`; `test1` = split `test`; `test2`) and
`order_idx` (position in that list) record where a row came from. No input appears in two splits.

| split | candidate list | candidates | applicable | selected | target |
|---|---|---|---|---|---|
| `profiling` | `profiling` | 15 | 13 | 10 | 10 |
| `test` | `test1` | 30 | 24 | 20 | 20 |
| `test2` | `test2` | 30 | 26 | 20 | 20 |

Candidates dropped as not applicable. In every case one `/sam/sam-predict` call segmented nothing
and returned an empty response (prompt in brackets):

- `profiling`: `coco_160012` (human face), `coco_579902` (human face)
- `test`: `coco_273198` (human face), `coco_314251` (human face), `coco_342128` (car),
  `coco_464824` (human face), `coco_537506` (human face), `coco_570688` (car)
- `test2`: `coco_421455` (human face), `coco_432898` (human face), `coco_569030` (human face),
  `coco_577932` (human face)

## Row fields

`input_id` (`coco_<image id>`), `file` (relative to `data/image_blur/`), `sha256`, `source`,
`source_url`, `flickr_url`, `width`, `height`, `license_id`, `license_name`, `license_url` (from
the COCO annotation file), `n_person`, `n_car` (non-crowd instances), `max_person_frac` (largest
person box over the image area), `group`, `order_idx`.

## Licenses

COCO annotations: CC BY 4.0 (COCO Consortium). Images: Flickr photos under the per-image Creative
Commons license recorded in each row (several are NonCommercial and/or NoDerivs), and the Flickr
Terms of Use. The images are not redistributed here; `prepare_data.py` fetches them.
