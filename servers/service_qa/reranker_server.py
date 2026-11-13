# -*- coding: utf-8 -*-
"""reranker_server.py -- cross-encoder reranking (port 8204).

    POST /rerank
      {query: str, candidates: [{doc_id, passage_text, ...}, ...], top_k: int,
       trace_id?, node_id?}
      -> {hits: [{...candidate fields, score}, ...]}   (top_k by reranker score)
    GET /health

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 at the revision pinned below
(Hugging Face now redirects this name to cross-encoder/ms-marco-MiniLM-L6-v2).
Every (query, passage_text) pair is scored in one predict() call; each
returned hit is the candidate with its ``score`` replaced by the reranker
score. The model loads on the first /rerank call and stays loaded.

    RAG_RERANK_PORT=8204 python reranker_server.py
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

from _shared import BaseReq

MODEL_ID = os.environ.get("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
MODEL_REVISION = os.environ.get("RAG_RERANK_REVISION", "233902d25c440f23af6f7d6e94d2946bac0bee0a")

_MODEL = None
_LOCK = threading.Lock()


def _ensure_loaded() -> Any:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        from sentence_transformers import CrossEncoder  # noqa: WPS433

        _MODEL = CrossEncoder(MODEL_ID, revision=MODEL_REVISION or None)
    return _MODEL


app = FastAPI(title="service_qa.reranker", version="0.1")


class RerankReq(BaseReq):
    query: str
    candidates: List[Dict[str, Any]]
    top_k: int = 5


class RerankResp(BaseModel):
    hits: List[Dict[str, Any]]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "model": MODEL_ID}


@app.post("/rerank", response_model=RerankResp)
def rerank(req: RerankReq) -> RerankResp:
    model = _ensure_loaded()
    enriched = [{**c, "passage_text": c.get("passage_text") or ""} for c in req.candidates]
    pairs = [[req.query, c["passage_text"]] for c in enriched]
    scores = model.predict(pairs).tolist() if pairs else []
    scored = list(zip(enriched, scores))
    scored.sort(key=lambda x: -x[1])
    top = scored[: req.top_k]
    return RerankResp(hits=[{**c, "score": float(s)} for c, s in top])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("RAG_HOST", "127.0.0.1"), port=int(os.environ.get("RAG_RERANK_PORT", "8204")))
