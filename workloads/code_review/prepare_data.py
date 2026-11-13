# -*- coding: utf-8 -*-
"""Fetch the CodeReview inputs into data/code_review/ and check their sha256.

    python workloads/code_review/prepare_data.py [--split test] [--tarball PATH]

Every manifest row names a ``source_url`` and a ``source_relpath``:

* rows from the CPython 3.9.6 source tarball (python.org, sha256 pinned below):
  the tarball is downloaded once into data/code_review/_downloads/ (or taken
  from --tarball) and ``Python-3.9.6/<source_relpath>`` is extracted;
* the one row from a CPython git commit (profiling ``mailcap.py``): the raw
  file is downloaded from that commit.

Each file is written to data/code_review/<file> and must match the row's
sha256. Re-running skips files that are already present and correct.
Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from wbench import manifest  # noqa: E402

WORKLOAD = "code_review"
SPLITS = ("profiling", "test", "test2")
TARBALL_URL = "https://www.python.org/ftp/python/3.9.6/Python-3.9.6.tgz"
TARBALL_SHA256 = "d0a35182e19e416fc8eae25a3dcd4d02d4997333e4ad1f2eee6010aadc3fe866"
TARBALL_PREFIX = "Python-3.9.6/"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print(f"downloading {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    os.replace(tmp, dest)


def get_tarball(data: str, given: str | None) -> str:
    path = given or os.path.join(data, "_downloads", "Python-3.9.6.tgz")
    if not os.path.exists(path):
        if given:
            raise SystemExit(f"--tarball {given}: not found")
        download(TARBALL_URL, path)
    got = manifest.sha256_file(path)
    if got != TARBALL_SHA256:
        raise SystemExit(f"{path}: sha256 {got} != {TARBALL_SHA256}")
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", action="append", choices=SPLITS, help="only these splits (default: all)")
    p.add_argument("--tarball", default=None, help="use a local copy of Python-3.9.6.tgz instead of downloading")
    a = p.parse_args()
    data = manifest.data_dir(WORKLOAD)
    rows = [r for s in (a.split or SPLITS) for r in manifest.load(WORKLOAD, s)]

    todo = []
    for r in rows:
        dst = os.path.join(data, r["file"])
        if os.path.exists(dst) and manifest.sha256_file(dst) == r["sha256"]:
            continue
        todo.append(r)
    print(f"{len(rows) - len(todo)} of {len(rows)} files already present", file=sys.stderr)

    tar = None
    bad = []
    try:
        for r in todo:
            if r["source_url"] == TARBALL_URL:
                if tar is None:
                    tar = tarfile.open(get_tarball(data, a.tarball))
                f = tar.extractfile(TARBALL_PREFIX + r["source_relpath"])
                if f is None:
                    raise SystemExit(f"{r['input_id']}: {r['source_relpath']} not in tarball")
                body = f.read()
            else:
                with urllib.request.urlopen(r["source_url"], timeout=120) as resp:
                    body = resp.read()
            if sha256_bytes(body) != r["sha256"]:
                bad.append(r["input_id"])
                continue
            dst = os.path.join(data, r["file"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as out:
                out.write(body)
    finally:
        if tar is not None:
            tar.close()
    if bad:
        raise SystemExit(f"sha256 mismatch for {len(bad)} input(s): {bad}")
    print(f"ok: {len(rows)} files in {data}", file=sys.stderr)


if __name__ == "__main__":
    main()
