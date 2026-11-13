"""Compare the outputs of two result files input by input.

    python -m wbench.compare reference.jsonl candidate.jsonl [--outputs final_image]

For every input id, the most frequent output hash over the timed rounds of
each file is compared, per output name. This is the exact-match check; some
workloads also need a tolerance-based check (stochastic generation, hosted
LLMs). Each workload's README states which rule applies and ships its own
checker when exact match is not the right rule.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from .summarize import load


def modal_outputs(rows: List[Dict[str, Any]], names: Optional[List[str]]) -> Dict[str, Dict[str, str]]:
    seen: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        if r.get("warmup") or r["status"] != "ok":
            continue
        for k, h in r["outputs"].items():
            if names is None or k in names:
                seen[r["input_id"]][k][h] += 1
    return {i: {k: c.most_common(1)[0][0] for k, c in d.items()} for i, d in seen.items()}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference")
    p.add_argument("candidate")
    p.add_argument("--outputs", default=None, help="comma-separated output names to compare (default: all)")
    a = p.parse_args()
    names = a.outputs.split(",") if a.outputs else None
    ref = modal_outputs(load([a.reference]), names)
    cand = modal_outputs(load([a.candidate]), names)
    same = differ = missing = 0
    for i in sorted(ref):
        if i not in cand:
            missing += 1
            print(f"MISSING  {i}")
            continue
        diff = sorted(k for k in ref[i] if cand[i].get(k) != ref[i][k])
        if diff:
            differ += 1
            print(f"DIFFERS  {i}: {', '.join(diff)}")
        else:
            same += 1
    print(f"identical {same}, differ {differ}, missing {missing} (of {len(ref)} reference inputs)")


if __name__ == "__main__":
    main()
