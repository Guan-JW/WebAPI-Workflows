# -*- coding: utf-8 -*-
"""Build the ServiceQA inputs and corpus from MS MARCO v2.1 and check their sha256.

    python workloads/service_qa/prepare_data.py [--parquet PATH] [--skip-corpus]

1. Downloads the MS MARCO v2.1 validation parquet from Hugging Face at a pinned
   revision (about 210 MB) into data/service_qa/_downloads/, or uses --parquet,
   and checks its sha256.
2. Writes data/service_qa/corpus/passages.jsonl: the first 100 000 distinct
   passage texts (whitespace-stripped, empty ones skipped) in file order, as
   {"doc_id": "p<5 digits>", "passage_text": ..., "metadata": {"source":
   "ms_marco_v2.1_dev"}}, one JSON object per line. The result must have the
   sha256 below. The services read this file; the vector index also needs
   passages.npy, made by servers/service_qa/embed_corpus.py.
3. Writes one file per manifest row, data/service_qa/queries/<input_id>.txt,
   holding the whitespace-stripped query text of parquet row
   ``parquet_row_idx`` (UTF-8, no newline), and checks it against the row's
   sha256.

Needs pyarrow (see requirements.txt).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from wbench import manifest  # noqa: E402

WORKLOAD = "service_qa"
SPLITS = ("profiling", "test", "test2")
PARQUET_URL = ("https://huggingface.co/datasets/microsoft/ms_marco/resolve/"
               "a47ee7aae8d7d466ba15f9f0bfac3b3681087b3a/v2.1/validation-00000-of-00001.parquet")
PARQUET_SHA256 = "a07a87f483e602f5812573bff45109e5cbd934773c1c364366f176dd791e44d7"
N_PASSAGES = 100_000
CORPUS_SHA256 = "f3dd62a7b8437aaec1044067a05634d8961c9d6acdb47cb2b623687787be148f"


def get_parquet(data: str, given: str | None) -> str:
    path = given or os.path.join(data, "_downloads", "validation-00000-of-00001.parquet")
    if not os.path.exists(path):
        if given:
            raise SystemExit(f"--parquet {given}: not found")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"downloading {PARQUET_URL}", file=sys.stderr)
        with urllib.request.urlopen(PARQUET_URL, timeout=300) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
        os.replace(path + ".part", path)
    got = manifest.sha256_file(path)
    if got != PARQUET_SHA256:
        raise SystemExit(f"{path}: sha256 {got} != {PARQUET_SHA256}")
    return path


def build_corpus(passages_col) -> bytes:
    seen = set()
    out = []
    for p in passages_col:
        for text in (p or {}).get("passage_text", []):
            text = (text or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(json.dumps({"doc_id": f"p{len(out):05d}", "passage_text": text,
                                   "metadata": {"source": "ms_marco_v2.1_dev"}}, ensure_ascii=False) + "\n")
            if len(out) >= N_PASSAGES:
                return "".join(out).encode("utf-8")
    raise SystemExit(f"parquet has only {len(out)} distinct passages")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet", default=None, help="local copy of the validation parquet (skips the download)")
    ap.add_argument("--skip-corpus", action="store_true", help="write only the query files")
    a = ap.parse_args()
    import pyarrow.parquet as pq

    data = manifest.data_dir(WORKLOAD)
    table = pq.read_table(get_parquet(data, a.parquet), columns=["query_id", "query", "passages"])

    if not a.skip_corpus:
        cpath = os.path.join(data, "corpus", "passages.jsonl")
        if os.path.exists(cpath) and manifest.sha256_file(cpath) == CORPUS_SHA256:
            print(f"corpus present: {cpath}", file=sys.stderr)
        else:
            body = build_corpus(table.column("passages").to_pylist())
            got = hashlib.sha256(body).hexdigest()
            if got != CORPUS_SHA256:
                raise SystemExit(f"rebuilt corpus sha256 {got} != {CORPUS_SHA256}")
            os.makedirs(os.path.dirname(cpath), exist_ok=True)
            with open(cpath, "wb") as f:
                f.write(body)
            print(f"wrote {cpath} ({N_PASSAGES} passages, sha256 ok)", file=sys.stderr)

    qids = table.column("query_id").to_pylist()
    queries = table.column("query").to_pylist()
    n = 0
    for split in SPLITS:
        for r in manifest.load(WORKLOAD, split):
            i = r["parquet_row_idx"]
            if int(qids[i]) != r["msmarco_query_id"]:
                raise SystemExit(f"{r['input_id']}: parquet row {i} has query_id {qids[i]}, "
                                 f"manifest says {r['msmarco_query_id']}")
            body = (queries[i] or "").strip().encode("utf-8")
            if hashlib.sha256(body).hexdigest() != r["sha256"]:
                raise SystemExit(f"{r['input_id']}: sha256 mismatch")
            dst = os.path.join(data, r["file"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(body)
            n += 1
    print(f"ok: {n} query files in {os.path.join(data, 'queries')}", file=sys.stderr)


if __name__ == "__main__":
    main()
