"""Closed-loop client concurrency for any workload.

    python -m wbench.closed_loop head_fashion --clients 4 --split test -- --a1111-url http://host:7860

Starts C client processes of ``workloads/<id>/run.py``. Each client takes its
own shard of the split (``--shard i/C``), runs one untimed warm-up unit, waits
for a common start time, then issues k = max(4, ceil(16 / C)) units back to
back (override with ``--requests``). Every client gets its own work
directory, so stateful workloads never share sessions, files or output paths.
Arguments after ``--`` are passed to every client. Summarize the result with
``python -m wbench.summarize <out>/client*.jsonl``.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time

from .manifest import REPO_ROOT


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("workload")
    p.add_argument("--clients", type=int, required=True)
    p.add_argument("--split", default="test")
    p.add_argument("--requests", type=int, default=None, help="timed units per client (default: max(4, ceil(16/C)))")
    p.add_argument("--warmup-budget-s", type=float, default=600.0,
                   help="seconds allowed for every client to finish set-up and warm-up before the common start")
    p.add_argument("--out", default=None, help="output directory (default: runs/<workload>/conc_c<C>_<utc>)")
    p.add_argument("--label", default="baseline")
    argv = sys.argv[1:]
    cut = argv.index("--") if "--" in argv else len(argv)
    a = p.parse_args(argv[:cut])
    rest = argv[cut + 1:]
    c = a.clients
    k = a.requests or max(4, math.ceil(16 / c))
    out = a.out or os.path.join("runs", a.workload, f"conc_c{c}_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}")
    os.makedirs(out, exist_ok=True)
    start_at = time.time() + a.warmup_budget_s
    script = os.path.join(REPO_ROOT, "workloads", a.workload, "run.py")
    procs = []
    for i in range(c):
        cmd = [sys.executable, script, "--split", a.split, "--shard", f"{i}/{c}", "--client-id", str(i),
               "--requests", str(k), "--start-at", f"{start_at:.3f}", "--label", a.label,
               "--out", os.path.join(out, f"client{i}.jsonl"), "--workdir", os.path.join(out, f"work_c{i}")] + rest
        procs.append(subprocess.Popen(cmd))
    codes = [pr.wait() for pr in procs]
    late = time.time() < start_at
    print(f"clients={c} k={k} exit codes={codes} -> {out}" + ("  (finished before start?)" if late else ""))
    if any(codes):
        sys.exit(1)


if __name__ == "__main__":
    main()
