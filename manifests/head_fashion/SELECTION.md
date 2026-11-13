# HeadFashion: input selection

## Source

Open Images V7 photos from the `validation` and `test` subsets, selected with the bounding-box
annotations of the V5 release (the Open Images site lists no box changes for these subsets after
V5). Images are fetched from the public mirror
`https://open-images-dataset.s3.amazonaws.com/<subset>/<ImageID>.jpg` (`source_url` in each row).

| file | sha256 |
|---|---|
| https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv | `d8bbd59410af14835d7733165a7bb8a3f0213981b22dd5077b0b9f7878991ff2` |
| https://storage.googleapis.com/openimages/v5/test-annotations-bbox.csv | `fe22e579b9453875601576859d14ef3304058165de139c66b725e599202bd7b1` |
| https://storage.googleapis.com/openimages/2018_04/class-descriptions-boxable.csv | `f101dfd97c6c2e080d2f7f65b1f7f3b098e25edb975568dfc608332ce90c9f52` |
| https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv | `ed93a0e121fe345effdfc7359b848dbc64a1ff6778c8c73563157cb500b33a17` |
| https://storage.googleapis.com/openimages/2018_04/test/test-images-with-rotation.csv | `de55c6b8cbda32a79f4a20f28572d54e9c49d527a4006725675764074a51a36d` |

## Rule

1. **Eligible**: at least one box of class Hat, Sun hat or Cowboy hat, and at least one box of
   class Person, Man, Woman, Boy, Girl, Human head or Human face. Pool: 187 of 37,306 validation
   images and 617 of 112,194 test images with boxes (804 in total).
2. **Order**: sort the eligible ImageIDs, shuffle once with Python `random.Random(20261033)`, and
   cut consecutive candidate lists: 15 for `profiling`, 30 for `test`, 30 for `test2`
   (1.5 x the target of 10 / 20 / 20, rounded up). No download failed.
3. **Applicability**: every candidate was run once through this workload (img2img seed 1234)
   against the development server, the instance with `DINO_UNLOAD_AFTER_CALL=1`. A candidate is
   applicable when both `/sam/sam-predict` calls return at least one mask and both
   `/sdapi/v1/img2img` calls return an image.
4. **Selection**: each split keeps the first applicable candidates, in candidate order, up to its
   target.

Row fields `group` (name of the candidate list: `profiling`; `test1` = split `test`; `test2`) and
`order_idx` (position in that list) record where a row came from. No input appears in two splits.

| split | candidate list | candidates | applicable | selected | target |
|---|---|---|---|---|---|
| `profiling` | `profiling` | 15 | 9 | 9 | 10 |
| `test` | `test1` | 30 | 26 | 20 | 20 |
| `test2` | `test2` | 30 | 24 | 20 | 20 |

`profiling` has 9 inputs, one short of its target: only 9 of its 15 candidates were applicable,
and the list was not extended.

Candidates dropped as not applicable. In every case the second `/sam/sam-predict` call (prompt
"hair", on the image after the hat edit) found no box and returned no mask
(`{'msg': 'You neither added point prompts nor enabled GroundingDINO. Segmentation cannot be generated.'}`):

- `profiling`: `oi_001a695ad732152b`, `oi_0be6fd5c4b8b2f0c`, `oi_4426fa0e3b515179`, `oi_52db0342612d8e96`,
  `oi_8a41076e29f8c2af`, `oi_f7599194b68aa78f`
- `test`: `oi_1c1c8c4995e1befc`, `oi_1e249e83a659834e`, `oi_6b40481f5bf5f360`, `oi_7910decdd5e92a8c`
- `test2`: `oi_10228b3f740a2390`, `oi_24a2af0160296521`, `oi_bbbf94358f2d4bf7`, `oi_e3e0a6f367ae14cc`,
  `oi_eb9b7934ce1a74d2`, `oi_fed7008307a9d9ff`

Because the hair edit depends on the hat edit, which depends on the inpainting seed and the GPU,
a candidate's applicability can differ on other hardware or software versions.

## Row fields

`input_id` (`oi_<ImageID>`), `file` (relative to `data/head_fashion/`), `sha256` (of the mirror
file), `source`, `subset`, `source_url`, `original_url` (Flickr original), `landing_url` (Flickr
page), `author`, `title`, `license_url`, `hat_labels` and `person_labels` (box classes present),
`max_hat_box_frac` (area of the largest hat box over the image area), `group`, `order_idx`.

## Licenses

Annotations: CC BY 4.0 (Google LLC). Images: CC BY 2.0 as listed by Open Images (every selected
row has `license_url` https://creativecommons.org/licenses/by/2.0/); Google states that it does not
verify the license of each image. Attribution data (`author`, `title`, `landing_url`) is in each
row. The images are not redistributed here; `prepare_data.py` fetches them.
