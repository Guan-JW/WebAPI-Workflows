# -*- coding: utf-8 -*-
"""embedder_server.py -- sentence-transformers query embedder (port 8201).

    POST /embed
      {texts: [str, ...], trace_id?: str, node_id?: str}
      -> {vectors: [[float, ...], ...], dim: int, model: str}
    GET /health

Model: sentence-transformers/all-MiniLM-L6-v2 (384-d), at the revision pinned
below; vectors are L2-normalized. The model loads on the first /embed call
and stays loaded.

    RAG_EMBED_PORT=8201 python embedder_server.py
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel

from _shared import BaseReq

MODEL_ID = os.environ.get("RAG_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MODEL_REVISION = os.environ.get("RAG_EMBED_REVISION", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41")

_MODEL = None
_LOCK = threading.Lock()


def _ensure_loaded() -> Any:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        from sentence_transformers import SentenceTransformer  # noqa: WPS433

        _MODEL = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION or None)
    return _MODEL


app = FastAPI(title="service_qa.embedder", version="0.1")


class EmbedReq(BaseReq):
    texts: List[str]


class EmbedResp(BaseModel):
    vectors: List[List[float]]
    dim: int
    model: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "model": MODEL_ID}


@app.post("/embed", response_model=EmbedResp)
def embed(req: EmbedReq) -> EmbedResp:
    model = _ensure_loaded()
    vecs = model.encode(
        req.texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).tolist()
    return EmbedResp(vectors=vecs, dim=len(vecs[0]) if vecs else 0, model=MODEL_ID)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("RAG_HOST", "127.0.0.1"), port=int(os.environ.get("RAG_EMBED_PORT", "8201")))
