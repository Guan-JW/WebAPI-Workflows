# -*- coding: utf-8 -*-
"""summarizer_server.py -- turn lint and security findings into a review (port 8104).

    POST /summarize
        Input : {"source": "<py src>",
                 "lint_summary": {"counts": {...}, "top3": [...]},
                 "sec_summary":  {"severity_max": "...", "issues": [...]},
                 "trace_id": <str>, "node_id": <str>}
        Output: {"review_text": <str>, "action": "approve" | "request_changes",
                 "tokens_in": int, "tokens_out": int}

The review is produced by a deterministic template: ``action`` is
``approve`` when the lint summary has no errors and the highest security
severity is NONE, LOW, UNDEFINED or empty, and ``request_changes`` otherwise.
``tokens_in`` / ``tokens_out`` are whitespace token counts.

    python summarizer_server.py --port 8104
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import BaseReq  # noqa: E402

app = FastAPI(title="code_review summarizer")

_SEVERITY_OK = {"LOW", "NONE", "UNDEFINED", ""}


class SumReq(BaseReq):
    source: str
    lint_summary: Dict[str, Any]
    sec_summary: Dict[str, Any]


class SumResp(BaseModel):
    review_text: str
    action: str
    tokens_in: int
    tokens_out: int


def _decide_action(lint_summary: Dict[str, Any], sec_summary: Dict[str, Any]) -> str:
    counts = (lint_summary or {}).get("counts", {}) or {}
    errors = int(counts.get("error", 0) or 0)
    sev_max = str((sec_summary or {}).get("severity_max", "") or "").upper()
    if errors == 0 and sev_max in _SEVERITY_OK:
        return "approve"
    return "request_changes"


def generate_review(source: str, lint_summary: Dict[str, Any], sec_summary: Dict[str, Any]) -> Dict[str, Any]:
    action = _decide_action(lint_summary, sec_summary)
    counts = (lint_summary or {}).get("counts", {}) or {}
    top = (lint_summary or {}).get("top3", []) or (
        lint_summary.get("diagnostics", []) if lint_summary else []
    )
    top = top[:3] if top else []
    issues = (sec_summary or {}).get("issues", []) or []
    sev_max = (sec_summary or {}).get("severity_max", "NONE")

    lines = [
        f"### Review ({action})",
        f"- Lint: {counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), {counts.get('info', 0)} info",
        f"- Security severity_max: {sev_max} ({len(issues)} issue(s))",
    ]
    if top:
        lines.append("- Top lint findings:")
        for d in top:
            code = d.get("code") or d.get("rule") or "?"
            msg = d.get("message", "")
            line_no = d.get("line") or d.get("location", {}).get("row", "?")
            lines.append(f"    * L{line_no} [{code}] {msg}")
    if issues:
        lines.append("- Security findings:")
        for sec in issues[:3]:
            test = sec.get("test_id") or sec.get("code") or "?"
            msg = sec.get("issue_text") or sec.get("message", "")
            line_no = sec.get("line_number") or sec.get("line", "?")
            lines.append(f"    * L{line_no} [{test}] {msg}")

    review_text = "\n".join(lines)
    return {
        "review_text": review_text,
        "action": action,
        "tokens_in": len(source.split()) + len(str(lint_summary).split()),
        "tokens_out": len(review_text.split()),
    }


@app.post("/summarize", response_model=SumResp)
def summarize(req: SumReq) -> SumResp:
    try:
        result = generate_review(req.source, req.lint_summary, req.sec_summary)
        return SumResp(
            review_text=str(result.get("review_text", "")),
            action=str(result.get("action", "request_changes")),
            tokens_in=int(result.get("tokens_in", 0)),
            tokens_out=int(result.get("tokens_out", 0)),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=repr(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="code_review summarizer service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8104)
    args = parser.parse_args()
    print(f"Starting summarizer at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
