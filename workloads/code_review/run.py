# -*- coding: utf-8 -*-
"""CodeReview: review one Python source file through four HTTP services.

    python workloads/code_review/run.py --split test
"""
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from wbench.harness import UnitResult, Workload, main  # noqa: E402

import review_client as client  # noqa: E402

# Fields of the /summarize response left out of the review_json output: token
# counts are bookkeeping, not part of the review.
VOLATILE_REVIEW_FIELDS = ("tokens_in", "tokens_out")


def add_args(p):
    for name, url in client.DEFAULT_URLS.items():
        p.add_argument(f"--{name}-url", default=url, help=f"{name} service (default: {url})")


def _enc(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def run_one(unit, ctx):
    path = os.path.join(ctx.data_dir, unit["file"])
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    urls = {name: getattr(ctx.args, f"{name}_url").rstrip("/") for name in client.DEFAULT_URLS}
    trace_id = f"tr_{uuid.uuid4().hex[:12]}"
    with ctx.timed():
        res = client.review_file(source, urls, trace_id=trace_id)
    review = {k: v for k, v in (res["review"] or {}).items() if k not in VOLATILE_REVIEW_FIELDS}
    return UnitResult(
        outputs={
            "review_json": _enc(review),
            "action": str(review.get("action")).encode("utf-8"),
            "lint_summary": _enc(res["lint_summary"]),
            "sec_summary": _enc(res["sec_summary"]),
        },
        extra={
            "action": review.get("action"),
            "lint_counts": res["lint_summary"].get("counts"),
            "severity_max": res["sec_summary"].get("severity_max"),
            "n_security_issues": len(res["sec_summary"].get("issues") or []),
        },
    )


WORKLOAD = Workload(id="code_review", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
