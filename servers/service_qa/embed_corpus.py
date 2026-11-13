# -*- coding: utf-8 -*-
"""Embed the 100k-passage corpus: passages.jsonl -> passages.npy (+ embed_meta.json).

    python servers/service_qa/embed_corpus.py [--corpus-dir DIR] [--batch-size 64]

Run after workloads/service_qa/prepare_data.py has written passages.jsonl.
Same model and settings as the embedder service: all-MiniLM-L6-v2 at the
pinned revision, normalize_embeddings=True, float32, batch size 64. Checks the
sha256 of passages.jsonl first. The reference corpus embedding (CUDA, torch
2.14.1, sentence-transformers 6.2.0) had the sha256 below; other hardware or
library versions can change low-order float bits, and therefore the
vector-search neighbours of some queries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import corpus_dir  # noqa: E402
from embedder_server import MODEL_ID, MODEL_REVISION  # noqa: E402

PASSAGES_JSONL_SHA256 = "f3dd62a7b8437aaec1044067a05634d8961c9d6acdb47cb2b623687787be148f"
REFERENCE_NPY_SHA256 = "600d880325138bd5a3bc8cdf214c5b76220abe9e8f1237a4623223fae9bf6bca"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", default=None, help="default: see _shared.corpus_dir()")
    ap.add_argument("--batch-size", type=int, default=64)
    a = ap.parse_args()
    cdir = a.corpus_dir or corpus_dir()
    jl = os.path.join(cdir, "passages.jsonl")
    got = sha256_file(jl)
    if got != PASSAGES_JSONL_SHA256:
        print(f"{jl}: sha256 {got} != {PASSAGES_JSONL_SHA256}", file=sys.stderr)
        return 2

    import numpy as np
    import sentence_transformers
    import torch
    from sentence_transformers import SentenceTransformer

    texts = [json.loads(line)["passage_text"] for line in open(jl, encoding="utf-8")]
    model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION or None)
    vecs = model.encode(texts, batch_size=a.batch_size, normalize_embeddings=True, convert_to_numpy=True,
                        show_progress_bar=True).astype("float32")
    out = os.path.join(cdir, "passages.npy")
    np.save(out, vecs)
    npy_sha = sha256_file(out)
    meta = {"passages_jsonl_sha256": got, "n": len(texts), "dim": int(vecs.shape[1]),
            "embed_model": MODEL_ID, "embed_revision": MODEL_REVISION, "passages_npy_sha256": npy_sha,
            "matches_reference_npy": npy_sha == REFERENCE_NPY_SHA256,
            "device": "cuda" if torch.cuda.is_available() else "cpu", "python": platform.python_version(),
            "torch": torch.__version__, "sentence_transformers": sentence_transformers.__version__}
    with open(os.path.join(cdir, "embed_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
