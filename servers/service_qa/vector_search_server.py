# -*- coding: utf-8 -*-
"""vector_search_server.py -- FAISS dense retrieval (port 8202).

    POST /search
      {query_vec: [float, ...], top_k: int, trace_id?, node_id?}
      -> {hits: [{doc_id, score, passage_text, metadata}, ...]}
    GET /health  -> {status, n_docs, loaded}

At startup the service loads passages.npy (float32 [N, 384]) and
passages.jsonl from the corpus directory (see _shared.corpus_dir) and builds
an inner-product index: IVF-Flat with nlist = max(64, int(sqrt(N))) and
nprobe = max(8, nlist // 16) when N >= 50 000 (N = 100 000 gives nlist 316,
nprobe 19), otherwise an exact flat index. The index is trained on the corpus
vectors at every start and kept in memory.

    RAG_VEC_PORT=8202 python vector_search_server.py
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from _shared import BaseReq, corpus_dir

_INDEX = None
_META: List[Dict[str, Any]] = []
_LOCK = threading.Lock()


def _load_index(cdir: str) -> None:
    global _INDEX, _META
    import faiss  # noqa: WPS433
    import numpy as np  # noqa: WPS433

    vecs = np.load(os.path.join(cdir, "passages.npy"))
    meta: List[Dict[str, Any]] = []
    with open(os.path.join(cdir, "passages.jsonl"), "r", encoding="utf-8") as f:
        for line in f:
            meta.append(json.loads(line))
    if vecs.shape[0] != len(meta):
        raise RuntimeError(f"corpus size mismatch: {vecs.shape[0]} vs {len(meta)}")
    n, d = vecs.shape
    vecs = vecs.astype("float32")
    if n >= 50000:
        nlist = max(64, int(n ** 0.5))
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(vecs)
        index.add(vecs)
        index.nprobe = max(8, nlist // 16)
    else:
        index = faiss.IndexFlatIP(d)
        index.add(vecs)
    with _LOCK:
        _INDEX = index
        _META = meta


app = FastAPI(title="service_qa.vector_search", version="0.1")


class SearchReq(BaseReq):
    query_vec: List[float]
    top_k: int = 10


class SearchResp(BaseModel):
    hits: List[Dict[str, Any]]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "n_docs": len(_META), "loaded": _INDEX is not None}


@app.on_event("startup")
def _on_startup() -> None:
    cdir = corpus_dir()
    if _INDEX is None and os.path.isdir(cdir):
        try:
            _load_index(cdir)
        except FileNotFoundError:
            pass


@app.post("/search", response_model=SearchResp)
def search(req: SearchReq) -> SearchResp:
    if _INDEX is None:
        raise HTTPException(status_code=503, detail="index not loaded")
    import numpy as np  # noqa: WPS433

    q = np.asarray([req.query_vec], dtype="float32")
    scores, idxs = _INDEX.search(q, req.top_k)
    hits: List[Dict[str, Any]] = []
    for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
        if idx < 0:
            continue
        m = _META[idx]
        hits.append({
            "doc_id": m.get("doc_id", f"doc_{idx}"),
            "score": float(score),
            "passage_text": m.get("passage_text", ""),
            "metadata": m.get("metadata", {}),
        })
    return SearchResp(hits=hits)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("RAG_HOST", "127.0.0.1"), port=int(os.environ.get("RAG_VEC_PORT", "8202")))
