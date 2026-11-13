"""Download the COCO val2017 photos listed in manifests/iopaint/ and check their sha256.

    python workloads/iopaint/prepare_data.py [--split profiling,test]

Files go to $WBENCH_DATA/iopaint/val2017/ (default <repo>/data/iopaint/val2017/).
Only the photos are fetched: the click points and object annotations used by
the workload are already in the manifest rows (see manifests/iopaint/SELECTION.md).
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

import requests  # noqa: E402

from wbench import manifest  # noqa: E402

WORKLOAD_ID = "iopaint"
SPLITS = ("profiling", "test")


def fetch(url, dest, sha256, tries=3):
    tmp = dest + ".part"
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            if manifest.sha256_bytes(r.content) != sha256:
                raise ValueError(f"sha256 mismatch for {url}")
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, dest)
            return
        except Exception as e:  # noqa: BLE001
            if attempt == tries:
                raise
            print(f"retry {attempt}/{tries - 1} for {url}: {e}", file=sys.stderr)
            time.sleep(2 * attempt)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default=",".join(SPLITS), help="comma-separated splits (default: all)")
    a = p.parse_args()
    root = manifest.data_dir(WORKLOAD_ID)
    got = have = 0
    for split in a.split.split(","):
        for r in manifest.load(WORKLOAD_ID, split):
            dest = os.path.join(root, r["file"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest) and manifest.sha256_file(dest) == r["sha256"]:
                have += 1
                continue
            fetch(r["url"], dest, r["sha256"])
            got += 1
    print(f"{WORKLOAD_ID}: {got} downloaded, {have} already present and verified, in {root}")


if __name__ == "__main__":
    main()
