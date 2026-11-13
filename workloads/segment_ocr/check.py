"""Compare the outputs of two runs of this workload, input by input, with the tolerance rule of README.md.

    python check.py REF.jsonl CAND.jsonl --ref-outputs DIR --cand-outputs DIR [--outputs a,b]

Both runs must have been made with `run.py ... --save-outputs DIR`. For every
input, the most frequent output hash over the timed rounds of each file is
taken (as in `python -m wbench.compare`), and the matching saved file is
compared:

* identical sha256 -> pass;
* `ocr_text`: equal after collapsing whitespace and upper-casing;
* `car_mask`, `plate_mask` (only if requested with --outputs): binarised at 127, IoU >= 0.99.
  Other outputs (`plate_bbox`, `plate_crop`) must be identical.

An input passes when every compared output passes. Exit status 1 if any input
differs or is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

WORKLOAD = "segment_ocr"
MAIN_OUTPUTS = ["ocr_text"]
ROI_MASKS = {}          # image output -> reference masks that define its region of interest
TEXT_OUTPUTS = {"ocr_text"}      # compared after whitespace/case normalisation
MASK_IOU_MIN = 0.99
ROI_SSIM_MIN = 0.99
ROI_FRAC16_MAX = 0.01
ROI_DILATE_PX = 16


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def modal(rows, outdir):
    """input_id -> {output: (sha256, saved file)} using the most frequent hash over timed ok rounds."""
    seen = defaultdict(lambda: defaultdict(Counter))
    where = {}
    for r in rows:
        if r.get("warmup") or r["status"] != "ok":
            continue
        for k, h in r["outputs"].items():
            seen[r["input_id"]][k][h] += 1
            where.setdefault((r["input_id"], k, h),
                             os.path.join(outdir, str(r["input_id"]), f"r{r['round']}_c{r['client_id']}", k))
    out = {}
    for i, d in seen.items():
        out[i] = {}
        for k, c in d.items():
            h = c.most_common(1)[0][0]
            out[i][k] = (h, where[(i, k, h)])
    return out


def gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype="float64")


def mask_iou(a_path, b_path):
    a, b = gray(a_path) > 127, gray(b_path) > 127
    if a.shape != b.shape:
        return None
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.0


def block_ssim(a, b, win=8):
    """Mean SSIM over non-overlapping win x win blocks (grayscale, K1=0.01, K2=0.03, L=255)."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    h, w = a.shape
    vals = []
    for y in range(0, h - win + 1, win):
        for x in range(0, w - win + 1, win):
            pa, pb = a[y:y + win, x:x + win], b[y:y + win, x:x + win]
            ma, mb = pa.mean(), pb.mean()
            cov = ((pa - ma) * (pb - mb)).mean()
            vals.append(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (pa.var() + pb.var() + c2)))
    return float(np.mean(vals)) if vals else None


def roi_check(a_path, b_path, mask_paths):
    a, b = gray(a_path), gray(b_path)
    if a.shape != b.shape:
        return None
    union = np.zeros(a.shape, dtype=bool)
    for mp in mask_paths:
        m = gray(mp) > 127
        if m.shape == a.shape:
            union |= m
    if not union.any():
        return None
    ys, xs = np.where(union)
    d = ROI_DILATE_PX
    y0, y1 = max(0, ys.min() - d), min(a.shape[0], ys.max() + 1 + d)
    x0, x1 = max(0, xs.min() - d), min(a.shape[1], xs.max() + 1 + d)
    ra, rb = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    ssim = block_ssim(ra, rb) if min(ra.shape) >= 8 else float(ra.tolist() == rb.tolist())
    frac16 = float((np.abs(ra - rb) > 16).mean())
    return ssim, frac16


def norm_text(s):
    return " ".join(s.split()).upper()


def check_output(k, ref, cand):
    (hr, fr), (hc, fc) = ref[k], cand[k]
    if hr == hc:
        return True, "exact"
    if not (os.path.exists(fr) and os.path.exists(fc)):
        return False, "hash differs and saved outputs are missing (run with --save-outputs)"
    if k in TEXT_OUTPUTS:
        tr, tc = open(fr, encoding="utf-8").read(), open(fc, encoding="utf-8").read()
        ok = norm_text(tr) == norm_text(tc)
        return ok, "text equal after normalisation" if ok else f"text {tr.strip()[:40]!r} vs {tc.strip()[:40]!r}"
    if "mask" in k:
        iou = mask_iou(fr, fc)
        ok = iou is not None and iou >= MASK_IOU_MIN
        return ok, f"IoU {iou}"
    if k in ROI_MASKS:
        masks = [ref[m][1] for m in ROI_MASKS[k] if m in ref and os.path.exists(ref[m][1])]
        res = roi_check(fr, fc, masks) if masks else None
        if res is None:
            return False, "no usable reference mask for the region of interest"
        ssim, frac16 = res
        ok = ssim >= ROI_SSIM_MIN and frac16 <= ROI_FRAC16_MAX
        return ok, f"ROI SSIM {ssim:.4f}, ROI pixels |d|>16 {frac16:.4f}"
    return False, "hash differs (no tolerance rule for this output)"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference")
    p.add_argument("candidate")
    p.add_argument("--ref-outputs", required=True, help="--save-outputs directory of the reference run")
    p.add_argument("--cand-outputs", required=True, help="--save-outputs directory of the candidate run")
    p.add_argument("--outputs", default=",".join(MAIN_OUTPUTS),
                   help=f"comma-separated outputs to compare (default: {','.join(MAIN_OUTPUTS)})")
    a = p.parse_args()
    names = [x for x in a.outputs.split(",") if x]
    ref = modal(load_rows(a.reference), a.ref_outputs)
    cand = modal(load_rows(a.candidate), a.cand_outputs)
    n_same = n_tol = n_diff = n_missing = 0
    for i in sorted(ref):
        if i not in cand:
            n_missing += 1
            print(f"MISSING  {i}")
            continue
        verdicts = []
        for k in names:
            if k not in ref[i] or k not in cand[i]:
                verdicts.append((k, False, "output missing"))
                continue
            ok, why = check_output(k, ref[i], cand[i])
            verdicts.append((k, ok, why))
        if all(ok for _, ok, _ in verdicts):
            if all(why == "exact" for _, _, why in verdicts):
                n_same += 1
            else:
                n_tol += 1
                print(f"TOLERATED {i}: " + "; ".join(f"{k}: {why}" for k, _, why in verdicts if why != "exact"))
        else:
            n_diff += 1
            print(f"DIFFERS  {i}: " + "; ".join(f"{k}: {why}" for k, ok, why in verdicts if not ok))
    print(f"{WORKLOAD}: identical {n_same}, within tolerance {n_tol}, differ {n_diff}, missing {n_missing} "
          f"(of {len(ref)} reference inputs; outputs {','.join(names)})")
    sys.exit(1 if (n_diff or n_missing) else 0)


if __name__ == "__main__":
    main()
