# -*- coding: utf-8 -*-
"""linter_server.py -- run ruff over Python source (port 8102).

    POST /lint
        Input : {"source": "<py src>", "ast_json": <str, optional>,
                 "trace_id": <str>, "node_id": <str>}
        Output: {"diagnostics": [{"code", "message", "line", "column", "severity"}, ...],
                 "counts": {"error": int, "warning": int, "info": int},
                 "full_report_text": <str>}

Every request starts a new ``ruff check`` process that reads the source from
stdin. If the request carries no ``ast_json``, the service first parses the
source with ``ast.parse`` (a validation step kept from the original service;
the workflow client always sends ``ast_json``, so it does not run there).
``ast_json`` is otherwise not used. ``full_report_text`` is a human-readable
rendering of the diagnostics. The client sends a ``fields`` query parameter
that lists all three fields; this service always returns all three and ignores
the parameter.

    python linter_server.py --port 8102
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import BaseReq, find_tool, run_subprocess  # noqa: E402

app = FastAPI(title="code_review linter")


class LintReq(BaseReq):
    source: str
    ast_json: Optional[str] = None


class LintResp(BaseModel):
    diagnostics: List[Dict[str, Any]]
    counts: Dict[str, int]
    full_report_text: Optional[str] = None


def _classify_ruff_severity(code: str) -> str:
    """Coarse map of ruff rule codes to {error, warning, info}."""
    if not code:
        return "warning"
    head = code[0].upper()
    if head in ("E", "F"):
        return "error"
    if head in ("W",):
        return "warning"
    return "info"


_RUFF_BIN = find_tool("ruff")
# --isolated: ignore any pyproject.toml / ruff.toml found above the working
# directory, so the rule set is ruff's default in every deployment.
_RUFF_CMD = [_RUFF_BIN, "check", "-", "--output-format=json", "--no-fix", "--isolated",
             "--stdin-filename", "input.py"]


def _run_ruff(source: str) -> List[Dict[str, Any]]:
    stdout, _stderr, _rc = run_subprocess(_RUFF_CMD, input_text=source, timeout=30)
    # ruff exits non-zero when it finds issues; stdout is what matters.
    try:
        raw = json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError:
        raw = []
    diagnostics: List[Dict[str, Any]] = []
    for d in raw:
        code = d.get("code", "")
        loc = d.get("location", {}) or {}
        diagnostics.append({
            "code": code,
            "message": d.get("message", ""),
            "line": loc.get("row"),
            "column": loc.get("column"),
            "severity": _classify_ruff_severity(code),
        })
    return diagnostics


def _counts(diagnostics: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {"error": 0, "warning": 0, "info": 0}
    for d in diagnostics:
        out[d.get("severity", "info")] = out.get(d.get("severity", "info"), 0) + 1
    return out


def _full_report(diagnostics: List[Dict[str, Any]]) -> str:
    if not diagnostics:
        return "No lint findings."
    lines = [f"Lint report ({len(diagnostics)} finding(s)):"]
    for d in diagnostics:
        lines.append(
            f"  L{d.get('line', '?')}:{d.get('column', '?')}  "
            f"[{d.get('severity', '?').upper()}] "
            f"{d.get('code', '?')}  {d.get('message', '')}"
        )
    lines.append("")
    lines.append("Legend: E/F = error, W = warning, other = info.")
    lines.append("-" * 72)
    return "\n".join(lines)


@app.post("/lint", response_model=LintResp)
def lint(req: LintReq) -> LintResp:
    try:
        if req.ast_json is None:
            try:
                ast.parse(req.source)
            except SyntaxError:
                pass
        diagnostics = _run_ruff(req.source)
        return LintResp(diagnostics=diagnostics, counts=_counts(diagnostics),
                        full_report_text=_full_report(diagnostics))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=repr(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="code_review linter service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    print(f"Starting linter at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
