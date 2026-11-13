"""Equivalence check for HybridSearch (README "Measurement").

    python check.py reference.jsonl [more reference files] --candidate candidate.jsonl [...]

Rule: a candidate request is equivalent when the `messages` it sent to the answering LLM (output
`chat_request`) equal one of the reference's requests for the same question, over all timed ok
reference rows. The answer text is not compared: the hosted LLM need not repeat itself. Both runs
must use the same index (extra.index_sha256). Exit status 1 if any candidate request differs or a
reference question has no candidate row.
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wbench.summarize import load  # noqa: E402


def timed_ok(rows):
    return [r for r in rows if not r.get("warmup") and r["status"] == "ok"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference", nargs="+")
    p.add_argument("--candidate", nargs="+", required=True)
    a = p.parse_args()
    ref, cand = timed_ok(load(a.reference)), timed_ok(load(a.candidate))
    idx = {r["extra"].get("index_sha256") for r in ref} | {r["extra"].get("index_sha256") for r in cand}
    if len(idx) != 1:
        print(f"WARNING: runs used different indexes: {sorted(i or 'none' for i in idx)}")
    allowed = defaultdict(set)
    for r in ref:
        allowed[r["input_id"]].add(r["outputs"].get("chat_request"))
    by_input = defaultdict(list)
    for r in cand:
        by_input[r["input_id"]].append(r["outputs"].get("chat_request"))
    equal = differ = 0
    for i in sorted(allowed):
        hs = by_input.get(i)
        if not hs:
            print(f"MISSING  {i}")
            continue
        bad = [h for h in hs if h not in allowed[i]]
        equal += len(hs) - len(bad)
        differ += len(bad)
        if bad:
            print(f"DIFFERS  {i}: {len(bad)}/{len(hs)} requests not among the reference's {len(allowed[i])}")
    missing = sum(1 for i in allowed if i not in by_input)
    extra = sorted(set(by_input) - set(allowed))
    print(f"chat requests equal to a reference request: {equal}/{equal + differ}; "
          f"questions missing: {missing}/{len(allowed)}; candidate-only questions: {len(extra)}")
    sys.exit(1 if differ or missing else 0)


if __name__ == "__main__":
    main()
