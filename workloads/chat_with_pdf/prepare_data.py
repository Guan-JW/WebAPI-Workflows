"""Download the inputs of this workload into data/<workload>/ and check their sha256.

    python -I prepare_data.py [--split profiling,test] [--verify-questions]

Inputs are arXiv PDFs of QASPER documents, listed in manifests/<workload>/<split>.jsonl
(field `file` relative to data/<workload>/, `pdf_url`, `sha256`). Questions are carried in the
manifest rows. --verify-questions also fetches each row's QASPER record from the Hugging Face
datasets-server and checks the question id and text (no files are written for that).

Uses only the standard library. Downloads are spaced 3 s apart (arXiv's request-rate guidance).
Set WBENCH_DATA to put data/ elsewhere.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

WORKLOAD = "chat_with_pdf"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UA = "WebAPI-Workflows prepare_data (QASPER inputs)"
ROWS_API = "https://datasets-server.huggingface.co/rows"
HF_API = "https://huggingface.co/api/datasets/allenai/qasper"


def data_dir():
    return os.path.join(os.environ.get("WBENCH_DATA", os.path.join(REPO, "data")), WORKLOAD)


def manifest(split):
    with open(os.path.join(REPO, "manifests", WORKLOAD, f"{split}.jsonl"), encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def get(url, timeout=120, tries=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503) or k == tries - 1:
                raise
            time.sleep(5 * 2 ** k)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def fetch_files(rows):
    files = {}
    for r in rows:
        files.setdefault(r["file"], r)
    bad, last = [], 0.0
    for rel, r in sorted(files.items()):
        path = os.path.join(data_dir(), rel)
        if os.path.exists(path) and sha256(open(path, "rb").read()) == r["sha256"]:
            print(f"ok      {rel} (present)")
            continue
        time.sleep(max(0.0, 3.0 - (time.time() - last)))
        last = time.time()
        try:
            b = get(r["pdf_url"])
        except Exception as e:  # noqa: BLE001
            print(f"FAILED  {rel}: {r['pdf_url']}: {e}")
            bad.append(rel)
            continue
        if sha256(b) != r["sha256"]:
            print(f"MISMATCH {rel}: {r['pdf_url']} gave sha256 {sha256(b)} ({len(b)} bytes), "
                  f"manifest has {r['sha256']} ({r.get('pdf_bytes')} bytes); file not written")
            bad.append(rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b)
        print(f"ok      {rel} (downloaded, {len(b)} bytes)")
    return len(files), bad


def verify_questions(rows):
    try:
        cur = json.loads(get(HF_API, 60)).get("sha")
    except Exception as e:  # noqa: BLE001
        cur = f"unavailable ({e})"
    revs = sorted({r["dataset_revision"] for r in rows})
    print(f"dataset revision in manifest: {revs}; current allenai/qasper revision: {cur}")
    bad, records = 0, {}
    for r in rows:
        key = (r["dataset_split"], r["dataset_row_idx"])
        if key not in records:
            q = urllib.parse.urlencode({"dataset": "allenai/qasper", "config": "qasper", "split": key[0],
                                        "offset": key[1], "length": 1})
            records[key] = json.loads(get(f"{ROWS_API}?{q}"))["rows"][0]["row"]
            time.sleep(1.0)
        rec = records[key]
        qas = dict(zip(rec["qas"]["question_id"], rec["qas"]["question"]))
        ok = rec["id"] == r["arxiv_id"] and qas.get(r["input_id"]) == r["question"] \
            and sha256(r["question"].encode()) == r["question_sha256"]
        bad += not ok
        print(f"{'ok' if ok else 'DIFFERS':8s}{r['input_id']} ({r['arxiv_id']}, row {r['dataset_row_idx']})")
    return bad


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="profiling,test", help="comma-separated splits (default: profiling,test)")
    p.add_argument("--verify-questions", action="store_true")
    a = p.parse_args()
    rows = [r for s in a.split.split(",") for r in manifest(s)]
    n, bad = fetch_files(rows)
    print(f"{n - len(bad)}/{n} files ok under {data_dir()}")
    nq = verify_questions(rows) if a.verify_questions else 0
    if a.verify_questions:
        print(f"{len(rows) - nq}/{len(rows)} questions match QASPER")
    sys.exit(1 if bad or nq else 0)


if __name__ == "__main__":
    main()
