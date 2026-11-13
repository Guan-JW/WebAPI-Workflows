"""Build the inputs of this workload in data/segment_ocr/ and check their sha256.

    python -I prepare_data.py [--split profiling,test,test2] [--limit N] [--keep-source]

The inputs are derived, not downloaded as-is. For each manifest row:

  1. download the OpenALPR benchmark JPEG from `source_url` (raw.githubusercontent.com,
     repository openalpr/benchmarks at the pinned commit `source_commit`) and check
     `source_sha256`;
  2. decode it, convert to RGB and apply PIL.ImageFilter.GaussianBlur(radius=row["blur"]["radius"])
     (1.0 for every row);
  3. save the result as PNG to data/segment_ocr/<file> and check `sha256`.

The PNG bytes depend on the Pillow version (and the zlib it is built with). The
manifest hashes were produced with Pillow 12.1.0 (`blur.pillow` in every row);
install the version pinned in requirements.txt. With another version the
script reports BADHASH; `--accept-other-pillow` keeps those files anyway (the
pixels are expected to match, but the inputs are then not byte-identical to
the manifest, and the harness records the manifest hash, not the file's).

Needs Pillow; everything else is the standard library. Set WBENCH_DATA to put
data/ elsewhere. --keep-source also stores the original JPEGs under
data/segment_ocr/source/.
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time
import urllib.request

WORKLOAD = "segment_ocr"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPLITS = ("profiling", "test", "test2")
UA = "WebAPI-Workflows prepare_data"


def data_dir():
    return os.path.join(os.environ.get("WBENCH_DATA", os.path.join(REPO, "data")), WORKLOAD)


def manifest(split):
    with open(os.path.join(REPO, "manifests", WORKLOAD, f"{split}.jsonl"), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"retry   {url}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))


def blur_png(jpeg_bytes, radius):
    from PIL import Image, ImageFilter

    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.filter(ImageFilter.GaussianBlur(radius=radius)).save(buf, format="PNG")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=",".join(SPLITS), help="comma-separated splits (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N rows of each split")
    ap.add_argument("--keep-source", action="store_true", help="also keep the downloaded JPEGs in data/segment_ocr/source/")
    ap.add_argument("--accept-other-pillow", action="store_true",
                    help="write blurred PNGs even when their sha256 differs from the manifest (other Pillow version)")
    a = ap.parse_args()
    import PIL

    os.makedirs(data_dir(), exist_ok=True)
    bad = []
    for split in a.split.split(","):
        for r in manifest(split)[: a.limit]:
            path = os.path.join(data_dir(), r["file"])
            if os.path.exists(path) and sha256(open(path, "rb").read()) == r["sha256"]:
                print(f"ok      {split} {r['file']} (present)")
                continue
            try:
                src = get(r["source_url"])
            except Exception as e:  # noqa: BLE001
                print(f"FAILED  {split} {r['input_id']}: {e}")
                bad.append(r["input_id"])
                continue
            if sha256(src) != r["source_sha256"]:
                print(f"BADSRC  {split} {r['input_id']}: source sha256 {sha256(src)[:16]} != {r['source_sha256'][:16]}")
                bad.append(r["input_id"])
                continue
            if a.keep_source:
                os.makedirs(os.path.join(data_dir(), "source"), exist_ok=True)
                with open(os.path.join(data_dir(), "source", os.path.basename(r["source_url"])), "wb") as f:
                    f.write(src)
            png = blur_png(src, float(r["blur"]["radius"]))
            if sha256(png) != r["sha256"]:
                print(f"BADHASH {split} {r['file']}: got {sha256(png)[:16]}, manifest {r['sha256'][:16]} "
                      f"(Pillow {PIL.__version__} here, {r['blur'].get('pillow')} for the manifest)")
                if not a.accept_other_pillow:
                    bad.append(r["input_id"])
                    continue
            with open(path, "wb") as f:
                f.write(png)
            print(f"ok      {split} {r['file']}")
    if bad:
        raise SystemExit(f"{len(bad)} input(s) missing or mismatched: {bad}")
    print(f"all inputs present in {data_dir()}")


if __name__ == "__main__":
    main()
