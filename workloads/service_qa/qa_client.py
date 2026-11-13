# -*- coding: utf-8 -*-
"""The question-answering workflow for one question.

Five sequential HTTP calls:

    1. POST embedder/embed       {texts: [query]}                    -> vectors[0]
    2. POST vector/search        {query_vec, top_k}                  -> top_k hits (doc_id, score, passage_text, metadata)
    3. POST bm25/bm25            {query, top_k}                      -> top_k hits (same fields)
       client-side merge: union by doc_id, max of the two scores, sorted by score, first top_n
    4. POST reranker/rerank      {query, candidates: merged, top_k: rerank_k} -> rerank_k hits
       client-side prompt: the reranked passages as a bullet list, then the question
    5. POST generator/generate   {prompt, max_new_tokens}            -> answer

Every request body also carries ``trace_id`` (one per question) and
``node_id`` (the step name). Transport errors are retried up to three times
with 50 ms, 150 ms and 450 ms back-off.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

DEFAULT_URLS = {
    "embed": "http://127.0.0.1:8201",
    "vec": "http://127.0.0.1:8202",
    "bm25": "http://127.0.0.1:8203",
    "rerank": "http://127.0.0.1:8204",
    "gen": "http://127.0.0.1:8205",
}

_RETRYABLE = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.WriteError,
    httpx.ReadError,
)


def _post(client: httpx.Client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    backoff = 0.05
    for attempt in range(4):
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except _RETRYABLE:
            if attempt == 3:
                raise
            time.sleep(backoff)
            backoff *= 3
    raise AssertionError("unreachable")


def merge_hits(vec_hits: List[Dict[str, Any]], bm25_hits: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for h in vec_hits:
        by_id[h["doc_id"]] = dict(h)
    for h in bm25_hits:
        doc_id = h["doc_id"]
        if doc_id in by_id:
            by_id[doc_id]["score"] = max(by_id[doc_id].get("score", 0.0), h.get("score", 0.0))
            by_id[doc_id].setdefault("passage_text", h.get("passage_text", ""))
        else:
            by_id[doc_id] = dict(h)
    return sorted(by_id.values(), key=lambda x: -x.get("score", 0.0))[:top_n]


def build_prompt(query: str, passages: List[Dict[str, Any]]) -> str:
    ctx = "\n".join(f"- {p.get('passage_text', '')}" for p in passages)
    return f"Context:\n{ctx}\n\nQuestion: {query}\nAnswer:"


def answer_question(client: httpx.Client, urls: Dict[str, str], query: str, *, trace_id: str,
                    top_k: int, top_n: int, rerank_k: int, max_new_tokens: int) -> Dict[str, Any]:
    emb = _post(client, f"{urls['embed']}/embed",
                {"texts": [query], "trace_id": trace_id, "node_id": "embed_q"})
    qvec = emb["vectors"][0]
    vec = _post(client, f"{urls['vec']}/search",
                {"query_vec": qvec, "top_k": top_k, "trace_id": trace_id, "node_id": "vec_search"})
    bm25 = _post(client, f"{urls['bm25']}/bm25",
                 {"query": query, "top_k": top_k, "trace_id": trace_id, "node_id": "bm25_search"})
    merged = merge_hits(vec["hits"], bm25["hits"], top_n)
    rr = _post(client, f"{urls['rerank']}/rerank",
               {"query": query, "candidates": merged, "top_k": rerank_k, "trace_id": trace_id,
                "node_id": "rerank"})
    prompt = build_prompt(query, rr["hits"])
    gen = _post(client, f"{urls['gen']}/generate",
                {"prompt": prompt, "max_new_tokens": max_new_tokens, "trace_id": trace_id,
                 "node_id": "generate"})
    return {"answer": gen["answer"], "prompt": prompt, "merged": merged, "reranked": rr["hits"],
            "n_vec": len(vec["hits"]), "n_bm25": len(bm25["hits"]), "tokens_in": gen.get("tokens_in"),
            "tokens_out": gen.get("tokens_out"), "backend": gen.get("backend")}
