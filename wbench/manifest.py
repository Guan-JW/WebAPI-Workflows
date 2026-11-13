"""Input manifests and the local data directory.

Manifests live in ``manifests/<workload>/<split>.jsonl``. Every row has an
``input_id`` and the fields needed to fetch and verify the input (source URL,
sha256, license). Raw inputs are not stored in the repository; each workload's
``prepare_data.py`` downloads them into ``$WBENCH_DATA/<workload>/`` (default
``<repo>/data/<workload>/``) and checks the hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir(workload: str) -> str:
    root = os.environ.get("WBENCH_DATA", os.path.join(REPO_ROOT, "data"))
    return os.path.join(root, workload)


def manifest_path(workload: str, split: str) -> str:
    return os.path.join(REPO_ROOT, "manifests", workload, f"{split}.jsonl")


def load(workload: str, split: str) -> List[Dict[str, Any]]:
    path = manifest_path(workload, split)
    if not os.path.exists(path):
        avail = sorted(f[:-6] for f in os.listdir(os.path.dirname(path)) if f.endswith(".jsonl"))
        raise SystemExit(f"no split {split!r} for {workload}; available: {avail}")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
