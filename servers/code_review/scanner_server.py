# -*- coding: utf-8 -*-
"""scanner_server.py -- run the Bandit security scanner over Python source (port 8103).

    POST /scan
        Input : {"source": "<py src>", "ast_json": <str, optional>,
                 "trace_id": <str>, "node_id": <str>}
        Output: {"issues": [{"test_id", "test_name", "severity", "confidence",
                             "issue_text", "line_number", "cwe_id"}, ...],
                 "cwe_refs": [<str>, ...],
                 "severity_max": "NONE" | "UNDEFINED" | "LOW" | "MEDIUM" | "HIGH"}

Every request writes the source to a temporary file and starts a new
``bandit -f json -q <file>`` process (Bandit's stdin support is unreliable);
the file is removed when the process exits. If the request carries no
``ast_json``, the service first parses the source with ``ast.parse`` (kept
from the original service; the workflow client always sends ``ast_json``).
``cwe_refs`` is a human-readable list of the CWE ids of the issues. The client
sends a ``fields`` query parameter that lists all three fields; this service
always returns all three and ignores the parameter.

    python scanner_server.py --port 8103
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import BaseReq, find_tool, run_subprocess  # noqa: E402

app = FastAPI(title="code_review scanner")

_SEVERITY_ORDER = {"UNDEFINED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
_BANDIT_BIN = find_tool("bandit")


class ScanReq(BaseReq):
    source: str
    ast_json: Optional[str] = None


class ScanResp(BaseModel):
    issues: List[Dict[str, Any]]
    cwe_refs: Optional[List[str]] = None
    severity_max: str


def _run_bandit(source: str) -> List[Dict[str, Any]]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(source)
        tmp_path = tmp.name
    try:
        stdout, _stderr, _rc = run_subprocess([_BANDIT_BIN, "-f", "json", "-q", tmp_path], timeout=30)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {}
    raw = parsed.get("results", []) if isinstance(parsed, dict) else []
    issues: List[Dict[str, Any]] = []
    for r in raw:
        issues.append({
            "test_id": r.get("test_id", "?"),
            "test_name": r.get("test_name", ""),
            "severity": (r.get("issue_severity") or "UNDEFINED").upper(),
            "confidence": (r.get("issue_confidence") or "UNDEFINED").upper(),
            "issue_text": r.get("issue_text", ""),
            "line_number": r.get("line_number"),
            "cwe_id": (r.get("issue_cwe") or {}).get("id"),
        })
    return issues


def _severity_max(issues: List[Dict[str, Any]]) -> str:
    if not issues:
        return "NONE"
    top = "UNDEFINED"
    for iss in issues:
        sev = (iss.get("severity") or "UNDEFINED").upper()
        if _SEVERITY_ORDER.get(sev, 0) > _SEVERITY_ORDER.get(top, 0):
            top = sev
    return top


def _cwe_refs(issues: List[Dict[str, Any]]) -> List[str]:
    refs = []
    for iss in issues:
        cwe = iss.get("cwe_id")
        if cwe:
            refs.append(
                f"CWE-{cwe}: {iss.get('test_name','?')} "
                f"(severity={iss.get('severity')}, "
                f"confidence={iss.get('confidence')})"
            )
    if not refs:
        refs.append("No CWE references for this file.")
    refs.append("-- end of cwe_refs --")
    return refs


@app.post("/scan", response_model=ScanResp)
def scan(req: ScanReq) -> ScanResp:
    try:
        if req.ast_json is None:
            try:
                ast.parse(req.source)
            except SyntaxError:
                pass
        issues = _run_bandit(req.source)
        return ScanResp(issues=issues, cwe_refs=_cwe_refs(issues), severity_max=_severity_max(issues))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=repr(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="code_review scanner service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    print(f"Starting scanner at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
