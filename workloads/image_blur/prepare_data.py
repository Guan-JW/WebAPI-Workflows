"""Download the inputs of this workload into data/image_blur/ and check their sha256.

    python -I prepare_data.py [--split profiling,test,test2] [--limit N]

Each manifest row names a COCO val2017 image by `source_url`
(images.cocodataset.org), its `sha256` and the Flickr license of the photo.
The file is saved as data/image_blur/<file>. Uses only the standard library. Set
WBENCH_DATA to put data/ elsewhere.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

WORKLOAD = "image_blur"
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=",".join(SPLITS), help="comma-separated splits (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N rows of each split")
    a = ap.parse_args()
    os.makedirs(data_dir(), exist_ok=True)
    bad = []
    for split in a.split.split(","):
        rows = manifest(split)[: a.limit]
        for r in rows:
            path = os.path.join(data_dir(), r["file"])
            if os.path.exists(path) and sha256(open(path, "rb").read()) == r["sha256"]:
                print(f"ok      {split} {r['file']} (present)")
                continue
            try:
                data = get(r["source_url"])
            except Exception as e:  # noqa: BLE001
                print(f"FAILED  {split} {r['file']}: {e}")
                bad.append(r["input_id"])
                continue
            if sha256(data) != r["sha256"]:
                print(f"BADHASH {split} {r['file']}: got {sha256(data)[:16]}, manifest {r['sha256'][:16]}")
                bad.append(r["input_id"])
                continue
            with open(path, "wb") as f:
                f.write(data)
            print(f"ok      {split} {r['file']}")
    if bad:
        raise SystemExit(f"{len(bad)} input(s) missing or mismatched: {bad}")
    print(f"all inputs present in {data_dir()}")


if __name__ == "__main__":
    main()
