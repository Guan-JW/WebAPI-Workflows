# -*- coding: utf-8 -*-
"""parser_server.py -- parse Python source into an AST (port 8101).

    POST /parse
        Input : {"source": "<python source>", "trace_id": "...", "node_id": "..."}
        Output: {"ast_json": "<ast.dump>", "symbols": [...], "loc": int,
                 "ast_id": "obj:ast:<16 hex>"}

``ast_json`` is ``ast.dump(tree, include_attributes=False)``. ``symbols``
lists every function and class name in ``ast.walk`` order. ``loc`` is the
number of lines. ``ast_id`` is a content address of ``ast_json`` (first 16
hex digits of its sha256). CPU only (Python stdlib ``ast``).

    python parser_server.py --port 8101
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import sys

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import BaseReq  # noqa: E402

app = FastAPI(title="code_review parser")


class ParseReq(BaseReq):
    source: str


class ParseResp(BaseModel):
    ast_json: str
    symbols: list[str]
    loc: int
    ast_id: str


def _content_id(s: str, kind: str) -> str:
    return f"obj:{kind}:{hashlib.sha256((s or '').encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _collect_symbols(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


@app.post("/parse", response_model=ParseResp)
def parse_source(req: ParseReq) -> ParseResp:
    try:
        try:
            tree = ast.parse(req.source)
        except SyntaxError as exc:
            raise HTTPException(status_code=400, detail=f"SyntaxError: {exc}") from exc
        ast_json = ast.dump(tree, include_attributes=False)
        symbols = _collect_symbols(tree)
        loc = len(req.source.splitlines())
        ast_id = _content_id(ast_json, "ast")
        return ParseResp(ast_json=ast_json, symbols=symbols, loc=loc, ast_id=ast_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=repr(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description="code_review parser service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8101)
    args = parser.parse_args()
    print(f"Starting parser at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
