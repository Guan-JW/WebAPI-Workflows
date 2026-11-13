"""Equivalence check for ChatWithPDF (README "Measurement").

    python check.py reference.jsonl [more reference files] --candidate candidate.jsonl [...]

The request the app sends to the chat model for question k of a session contains the answers to
questions 0..k-1 of that session (embedchain's chat history). A hosted LLM need not repeat those
answers, so each candidate question run is paired with the reference run at the same position
(round, client, question, n-th visit) and judged:

  identical        the chat `messages` (output `chat_request`) are byte-identical;
  history differs  they differ, and so do the session's earlier answers (extra.history_sha256):
                   not counted either way;
  DIFFERS          they differ although the earlier answers are identical.

Exit status 1 if any pair DIFFERS, a candidate run failed, or a reference run has no candidate.
Run the reference against itself on a second baseline run (A/A) to see the noise floor.
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wbench.summarize import load  # noqa: E402


def keyed(rows):
    rows = sorted((r for r in rows if not r.get("warmup")), key=lambda r: (r["client_id"], r["t_start_ms"]))
    seen, out = Counter(), {}
    for r in rows:
        k = (r["round"], r["client_id"], r["input_id"])
        out[k + (seen[k],)] = r
        seen[k] += 1
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference", nargs="+")
    p.add_argument("--candidate", nargs="+", required=True)
    a = p.parse_args()
    ref, cand = keyed(load(a.reference)), keyed(load(a.candidate))
    n = Counter()
    per_q = defaultdict(Counter)
    for k, r in sorted(ref.items()):
        c = cand.get(k)
        if c is None:
            n["missing"] += 1
            continue
        if c["status"] != "ok":
            n["candidate_failed"] += 1
            print(f"FAILED   {k}: {c['error']}")
            continue
        if r["status"] != "ok":
            n["reference_failed"] += 1
            continue
        if c["outputs"].get("chat_request") == r["outputs"].get("chat_request"):
            v = "identical"
        elif c["extra"].get("history_sha256") != r["extra"].get("history_sha256"):
            v = "history_differs"
        else:
            v = "DIFFERS"
            print(f"DIFFERS  round {k[0]} client {k[1]} {k[2]} (q{c['extra'].get('q_index')}, "
                  f"{c['extra'].get('arxiv_id')})")
        n[v] += 1
        per_q[c["extra"].get("q_index")][v] += 1
    print(", ".join(f"{k} {v}" for k, v in sorted(n.items())))
    for q in sorted(per_q):
        print(f"  q{q}: " + ", ".join(f"{k} {v}" for k, v in sorted(per_q[q].items())))
    sys.exit(1 if n["DIFFERS"] or n["candidate_failed"] or n["missing"] else 0)


if __name__ == "__main__":
    main()
