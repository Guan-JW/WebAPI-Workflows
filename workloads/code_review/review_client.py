# -*- coding: utf-8 -*-
"""The code review workflow for one Python source file.

Five sequential HTTP calls, as in the original client:

    1. POST parser/parse          {source}                       -> ast_json (+ symbols, loc, ast_id)
    2. POST linter/lint           {source, ast_json}             -> diagnostics, counts, full_report_text
    3. POST scanner/scan          {source, ast_json}             -> issues, severity_max, cwe_refs
    4. POST parser/parse          {source}  (second validation parse; response not used)
    5. POST summarizer/summarize  {source, lint_summary, sec_summary} -> review_text, action

Every request body also carries ``trace_id`` (one per unit) and ``node_id``
(the step name). ``full_report_text`` and ``cwe_refs`` are received and
dropped; the summarizer gets the lint counts, the first three diagnostics,
the highest security severity and all security issues.
"""

from __future__ import annotations

from typing import Any, Dict

import requests

DEFAULT_URLS = {
    "parser": "http://127.0.0.1:8101",
    "linter": "http://127.0.0.1:8102",
    "scanner": "http://127.0.0.1:8103",
    "summarizer": "http://127.0.0.1:8104",
}
LINT_FIELDS = "diagnostics,counts,full_report"
SCAN_FIELDS = "issues,severity_max,cwe_refs"
TIMEOUT_S = 60


def post_json(url: str, payload: Dict[str, Any], timeout: int = TIMEOUT_S) -> Dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def review_file(source: str, urls: Dict[str, str], *, trace_id: str) -> Dict[str, Any]:
    """Run the five calls for one file and return the intermediate and final results."""
    parse_resp = post_json(
        f"{urls['parser']}/parse",
        {"source": source, "trace_id": trace_id, "node_id": "parse_1"},
    )
    ast_json = parse_resp["ast_json"]

    lint_resp = post_json(
        f"{urls['linter']}/lint?fields={LINT_FIELDS}",
        {"source": source, "ast_json": ast_json, "trace_id": trace_id, "node_id": "lint_1"},
    )
    lint_resp.pop("full_report_text", None)

    scan_resp = post_json(
        f"{urls['scanner']}/scan?fields={SCAN_FIELDS}",
        {"source": source, "ast_json": ast_json, "trace_id": trace_id, "node_id": "scan_1"},
    )
    scan_resp.pop("cwe_refs", None)

    post_json(
        f"{urls['parser']}/parse",
        {"source": source, "trace_id": trace_id, "node_id": "parse_2"},
    )

    lint_summary = {
        "counts": lint_resp.get("counts", {}),
        "top3": lint_resp.get("diagnostics", [])[:3],
    }
    sec_summary = {
        "severity_max": scan_resp.get("severity_max", "NONE"),
        "issues": scan_resp.get("issues", []),
    }
    sum_resp = post_json(
        f"{urls['summarizer']}/summarize",
        {"source": source, "lint_summary": lint_summary, "sec_summary": sec_summary,
         "trace_id": trace_id, "node_id": "summarize_1"},
    )
    return {"review": sum_resp, "lint_summary": lint_summary, "sec_summary": sec_summary}
