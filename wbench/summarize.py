"""Summarize result files.

    python -m wbench.summarize runs/head_fashion/*.jsonl

Prints, per (workload, split, label): timed units, errors, p50 / p95 / mean
latency, median HTTP calls and bytes. When the rows come from a closed-loop
run (several client ids), it also prints completed throughput: successful
units divided by the time between the first start and the last end of the
timed window.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from typing import Any, Dict, List


def pct(xs: List[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def load(paths: List[str]) -> List[Dict[str, Any]]:
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows


def summarize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by = defaultdict(list)
    for r in rows:
        if not r.get("warmup"):
            by[(r["workload"], r["split"], r.get("label", ""))].append(r)
    out = []
    for (w, s, lab), rs in sorted(by.items()):
        ok = [r for r in rs if r["status"] == "ok"]
        lat = [r["latency_ms"] for r in ok]
        rec = {
            "workload": w, "split": s, "label": lab, "units": len(rs), "errors": len(rs) - len(ok),
            "p50_ms": round(pct(lat, 0.5), 1), "p95_ms": round(pct(lat, 0.95), 1),
            "mean_ms": round(statistics.fmean(lat), 1) if lat else None,
            "median_calls": statistics.median([r["http_calls"] for r in ok]) if ok else None,
            "median_bytes_out": statistics.median([r["bytes_out"] for r in ok]) if ok else None,
            "median_bytes_in": statistics.median([r["bytes_in"] for r in ok]) if ok else None,
        }
        clients = {r["client_id"] for r in rs}
        if len(clients) > 1 and ok:
            span_s = (max(r["t_end_ms"] for r in ok) - min(r["t_start_ms"] for r in ok)) / 1000.0
            rec["clients"] = len(clients)
            rec["throughput_per_s"] = round(len(ok) / span_s, 4) if span_s > 0 else None
        out.append(rec)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = p.parse_args()
    res = summarize(load(a.files))
    if a.json:
        print(json.dumps(res, indent=1))
        return
    cols = ["workload", "split", "label", "units", "errors", "p50_ms", "p95_ms", "mean_ms", "median_calls",
            "median_bytes_out", "median_bytes_in", "clients", "throughput_per_s"]
    cols = [c for c in cols if any(c in r for r in res)]
    print("\t".join(cols))
    for r in res:
        print("\t".join(str(r.get(c, "")) for c in cols))


if __name__ == "__main__":
    main()
