# -*- coding: utf-8 -*-
"""ServiceQA: answer one question through five self-hosted services.

    python workloads/service_qa/run.py --split test
"""
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from wbench.harness import UnitResult, Workload, main  # noqa: E402

import qa_client  # noqa: E402

URL_FLAGS = {"embed": "embed-url", "vec": "vec-url", "bm25": "bm25-url", "rerank": "rerank-url", "gen": "gen-url"}


def add_args(p):
    for key, flag in URL_FLAGS.items():
        p.add_argument(f"--{flag}", default=qa_client.DEFAULT_URLS[key],
                       help=f"default: {qa_client.DEFAULT_URLS[key]}")
    p.add_argument("--top-k", type=int, default=10, help="hits requested from each retriever (default: 10)")
    p.add_argument("--top-n", type=int, default=10, help="merged candidates sent to the reranker (default: 10)")
    p.add_argument("--rerank-k", type=int, default=5, help="passages kept by the reranker (default: 5)")
    p.add_argument("--max-new-tokens", type=int, default=64, help="generation length cap (default: 64)")
    p.add_argument("--timeout-s", type=float, default=120.0, help="HTTP timeout per request (default: 120)")


def _enc(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def run_one(unit, ctx):
    import httpx

    a = ctx.args
    with open(os.path.join(ctx.data_dir, unit["file"]), "rb") as f:
        query = f.read().decode("utf-8")
    urls = {key: getattr(a, flag.replace("-", "_")).rstrip("/") for key, flag in URL_FLAGS.items()}
    trace_id = f"tr_{uuid.uuid4().hex[:12]}"
    with httpx.Client(timeout=a.timeout_s) as client:
        with ctx.timed():
            res = qa_client.answer_question(client, urls, query, trace_id=trace_id, top_k=a.top_k, top_n=a.top_n,
                                            rerank_k=a.rerank_k, max_new_tokens=a.max_new_tokens)
    rerank_ids = [h.get("doc_id") for h in res["reranked"]]
    rerank_scores = [h.get("score") for h in res["reranked"]]
    return UnitResult(
        outputs={
            "answer": str(res["answer"]).encode("utf-8"),
            "prompt": res["prompt"].encode("utf-8"),
            "rerank_doc_ids": _enc(rerank_ids),
            "rerank_scores": _enc(rerank_scores),
            "merged_doc_ids": _enc([h.get("doc_id") for h in res["merged"]]),
        },
        extra={
            "rerank_doc_ids": rerank_ids,
            "rerank_scores": rerank_scores,
            "is_duplicate": bool(unit.get("is_duplicate")),
            "n_vec": res["n_vec"],
            "n_bm25": res["n_bm25"],
            "tokens_in": res["tokens_in"],
            "tokens_out": res["tokens_out"],
            "backend": res["backend"],
        },
    )


WORKLOAD = Workload(id="service_qa", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
