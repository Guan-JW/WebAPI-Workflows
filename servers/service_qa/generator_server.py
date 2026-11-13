# -*- coding: utf-8 -*-
"""generator_server.py -- answer generation (port 8205).

    POST /generate
      {prompt: str, max_new_tokens: int, trace_id?, node_id?}
      -> {answer: str, tokens_in: int, tokens_out: int, cancelled: false, backend: str}
    GET /health

The prompt is wrapped as one user turn with the tokenizer's chat template and
decoded greedily for at most max_new_tokens tokens (see gen_backend.py).
``cancelled`` is always false; it is kept so the response has the same fields
as in the reference runs.

    RAG_GEN_PORT=8205 RAG_GEN_BACKEND=qwen python generator_server.py
"""

from __future__ import annotations

import os
from typing import Dict

from fastapi import FastAPI
from pydantic import BaseModel

from _shared import BaseReq
from gen_backend import get_backend

BACKEND_NAME = os.environ.get("RAG_GEN_BACKEND", "qwen")
_BACKEND = get_backend(BACKEND_NAME)

app = FastAPI(title="service_qa.generator", version="0.1")


class GenReq(BaseReq):
    prompt: str
    max_new_tokens: int = 128


class GenResp(BaseModel):
    answer: str
    tokens_in: int
    tokens_out: int
    cancelled: bool
    backend: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "backend": _BACKEND.name}


@app.post("/generate", response_model=GenResp)
def generate(req: GenReq) -> GenResp:
    result = _BACKEND.generate(req.prompt, max_new_tokens=req.max_new_tokens)
    return GenResp(
        answer=result["answer"],
        tokens_in=result["tokens_in"],
        tokens_out=result["tokens_out"],
        cancelled=result["cancelled"],
        backend=_BACKEND.name,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.environ.get("RAG_HOST", "127.0.0.1"), port=int(os.environ.get("RAG_GEN_PORT", "8205")))
