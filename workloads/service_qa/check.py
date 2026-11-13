# -*- coding: utf-8 -*-
"""Equivalence check for ServiceQA result files.

    python workloads/service_qa/check.py reference.jsonl candidate.jsonl [--score-tol 1e-4]

Per input id (timed, successful rows; the most frequent value over rounds):

* main, must match exactly: ``rerank_doc_ids`` (the ordered passages the
  answer is grounded on) and ``prompt`` (what the generator received);
* ``rerank_scores``: every score within --score-tol of the reference;
* reported, not required: ``answer`` and ``merged_doc_ids`` (exact).

Exit status 1 if any input fails a main or score check, or is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wbench.summarize import load  # noqa: E402

MAIN = ("rerank_doc_ids", "prompt")
REPORTED = ("answer", "merged_doc_ids")


def modal(rows):
    hashes = defaultdict(lambda: defaultdict(Counter))
    scores = defaultdict(Counter)
    for r in rows:
        if r.get("warmup") or r["status"] != "ok":
            continue
        for k, h in r["outputs"].items():
            hashes[r["input_id"]][k][h] += 1
        scores[r["input_id"]][json.dumps(r["extra"].get("rerank_scores"))] += 1
    return ({i: {k: c.most_common(1)[0][0] for k, c in d.items()} for i, d in hashes.items()},
            {i: json.loads(c.most_common(1)[0][0]) for i, c in scores.items()})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference")
    p.add_argument("candidate")
    p.add_argument("--score-tol", type=float, default=1e-4)
    a = p.parse_args()
    ref_h, ref_s = modal(load([a.reference]))
    cand_h, cand_s = modal(load([a.candidate]))
    failed = 0
    reported = Counter()
    for i in sorted(ref_h):
        if i not in cand_h:
            failed += 1
            print(f"MISSING  {i}")
            continue
        bad = [k for k in MAIN if cand_h[i].get(k) != ref_h[i].get(k)]
        rs, cs = ref_s.get(i) or [], cand_s.get(i) or []
        if len(rs) != len(cs) or any(abs(x - y) > a.score_tol for x, y in zip(rs, cs)):
            bad.append("rerank_scores")
        for k in REPORTED:
            if cand_h[i].get(k) != ref_h[i].get(k):
                reported[k] += 1
        if bad:
            failed += 1
            print(f"DIFFERS  {i}: {', '.join(bad)}")
    n = len(ref_h)
    print(f"equivalent {n - failed} of {n} reference inputs; "
          f"answer differs on {reported['answer']}, merged_doc_ids on {reported['merged_doc_ids']}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
