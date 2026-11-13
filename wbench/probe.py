"""Measure the network path to a service before a run.

    python -m wbench.probe http://host:7860/sdapi/v1/options [--n 20] [--upload-mb 2]

Reports the median and maximum time of N small GET requests (round-trip time
plus server overhead of an idle endpoint), and, with ``--upload-mb``, the time
to POST that many bytes, as a rough upload bandwidth. Pick an idle, cheap
endpoint of the deployment being measured. Record the output with the results.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time

import requests


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--upload-mb", type=float, default=0.0)
    p.add_argument("--upload-url", default=None, help="URL that accepts a POST body (default: same URL)")
    a = p.parse_args()
    s = requests.Session()
    s.get(a.url, timeout=30)
    times = []
    for _ in range(a.n):
        t0 = time.perf_counter()
        s.get(a.url, timeout=30)
        times.append((time.perf_counter() - t0) * 1000.0)
    out = {"url": a.url, "n": a.n, "get_median_ms": round(statistics.median(times), 2),
           "get_max_ms": round(max(times), 2)}
    if a.upload_mb > 0:
        body = b"\0" * int(a.upload_mb * 1e6)
        t0 = time.perf_counter()
        s.post(a.upload_url or a.url, data=body, timeout=300)
        dt = time.perf_counter() - t0
        out["upload_mb_per_s"] = round(a.upload_mb / dt, 2)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
