# -*- coding: utf-8 -*-
"""bm25_server.py -- BM25 sparse retrieval (port 8203).

    POST /bm25
      {query: str, top_k: int, trace_id?, node_id?}
      -> {hits: [{doc_id, score, passage_text, metadata}, ...]}
    GET /health  -> {status, n_docs, loaded}

At startup the service tokenizes every passage of passages.jsonl (lowercased
runs of [A-Za-z0-9']) and builds a rank_bm25 BM25Okapi index with default
parameters. A query is scored against all passages; the top_k are returned in
descending score order (ties keep corpus order).

    RAG_BM25_PORT=8203 python bm25_server.py
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from _shared import BaseReq, corpus_dir

_BM25 = None
_META: List[Dict[str, Any]] = []
_LOCK = threading.Lock()

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _load_corpus(cdir: str) -> None:
    global _BM25, _META
    from rank_bm25 import BM25Okapi  # noqa: WPS433

    meta: List[Dict[str, Any]] = []
    tokenized: List[List[str]] = []
    with open(os.path.join(cdir, "passages.jsonl"), "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            meta.append(rec)
            tokenized.append(_tokenize(rec.get("passage_text", "")))
    bm25 = BM25Okapi(tokenized)
    with _LOCK:
        _BM25 = bm25
        _META = meta


app = FastAPI(title="service_qa.bm25", version="0.1")


class BM25Req(BaseReq):
    query: str
    top_k: int = 10


class SearchResp(BaseModel):
    hits: List[Dict[str, Any]]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "n_docs": len(_META), "loaded": _BM25 is not None}


@app.on_event("startup")
def _on_startup() -> None:
    cdir = corpus_dir()
    if _BM25 is None and os.path.isdir(cdir):
        try:
            _load_corpus(cdir)
        except FileNotFoundError:
            pass


def _build_hit(idx: int, score: float) -> Dict[str, Any]:
    m = _META[idx]
    return {
        "doc_id": m.get("doc_id", f"doc_{idx}"),
        "score": float(score),
        "passage_text": m.get("passage_text", ""),
        "metadata": m.get("metadata", {}),
    }


@app.post("/bm25", response_model=SearchResp)
def bm25(req: BM25Req) -> SearchResp:
    if _BM25 is None:
        raise HTTPException(status_code=503, detail="corpus not loaded")
    tokens = _tokenize(req.query)
    scores = _BM25.get_scores(tokens)
    top = sorted(range(len(scores)), key=lambda i: -scores[i])[: req.top_k]
    return SearchResp(hits=[_build_hit(i, scores[i]) for i in top])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("RAG_HOST", "127.0.0.1"), port=int(os.environ.get("RAG_BM25_PORT", "8203")))
