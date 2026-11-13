"""Build the document index the questions are asked against (paid: OpenAI embeddings).

    python build_index.py [--out data/hybrid_search/index/raglite.sqlite]

Ingests the 10 QASPER PDFs listed in the manifests (all splits; the index is shared) through the
app's own process_document (main.py L58-77, which calls raglite.insert_document with the session
configuration), in QASPER row order. Writes the SQLite database and <out>.meta.json (sha256, per
document result and time). Run prepare_data.py first. Embedding responses are not bit-stable across
calls, so two builds can differ; compare runs only against the same index (run rows record its
sha256 in extra.index_sha256).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from wbench import manifest  # noqa: E402

import app_setup  # noqa: E402

ID = "hybrid_search"


def documents():
    docs = {}
    for split in ("profiling", "test"):
        for r in manifest.load(ID, split):
            docs.setdefault(r["arxiv_id"], r)
    return sorted(docs.values(), key=lambda r: r["dataset_row_idx"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=os.path.join(manifest.data_dir(ID), "index", "raglite.sqlite"))
    p.add_argument("--upstream-dir", default=None)
    a = p.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    docs = documents()
    for r in docs:
        path = os.path.join(manifest.data_dir(ID), r["file"])
        if not os.path.exists(path) or manifest.sha256_file(path) != r["sha256"]:
            raise SystemExit(f"{path} missing or hash differs; run prepare_data.py")
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(out + ext):
            os.remove(out + ext)
    app = app_setup.load_app(a.upstream_dir)
    config = app_setup.build_config(out)   # the reranker is not used during ingestion
    app_setup.install_config(config)
    report = {"documents": []}
    for r in docs:
        t = time.perf_counter()
        ok = app.process_document(os.path.join(manifest.data_dir(ID), r["file"]))
        report["documents"].append({"arxiv_id": r["arxiv_id"], "sha256": r["sha256"], "ok": ok,
                                    "seconds": round(time.perf_counter() - t, 1)})
        print(report["documents"][-1], file=sys.stderr, flush=True)
    if not all(d["ok"] for d in report["documents"]):
        raise SystemExit("some documents failed to ingest (see the app's log above)")
    # Close the app's connections and fold the WAL into the main file, so that the database is one
    # self-contained file that run.py can copy.
    import sqlite3

    from raglite._database import create_database_engine

    create_database_engine(config).dispose()
    con = sqlite3.connect(out)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    report.update(sha256=manifest.sha256_file(out), bytes=os.path.getsize(out),
                  built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(out + ".meta.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"index {out}: sha256 {report['sha256']}", file=sys.stderr)


if __name__ == "__main__":
    main()
