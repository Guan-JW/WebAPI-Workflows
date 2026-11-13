"""STAND-IN SERVICE, not part of the upstream app: a local Cohere-compatible rerank endpoint.

The app reranks with Cohere's hosted API (main.py L53: ``Reranker("cohere", api_key=..., lang="en")``,
which posts to https://api.cohere.ai/v1/rerank with model rerank-english-v3.0). The workload was
developed without a Cohere key, so the app's own Cohere client is pointed at this service instead
(app_setup.build_config). It answers ``POST /v1/rerank`` in Cohere's v1 response format.

What it does per request:
  scoring  FlashRank ms-marco-MiniLM-L-12-v2 (ONNX, CPU, in this process), not Cohere's model;
  delay    sleeps --delay-ms (default 175 ms) after scoring and before replying, standing in for
           the network round trip to api.cohere.ai. The delay is per request and does not
           serialize concurrent requests (one thread per request).
Scores and ordering therefore differ from Cohere's. The app reads the order, the scores and the
returned document texts. Run one instance shared by all client processes:

    python rerank_standin.py [--port 18444] [--delay-ms 175] [--cache-dir DIR]

The FlashRank model (a 22 MB zip) is downloaded on first start from
https://huggingface.co/prithivida/flashrank/resolve/main/ms-marco-MiniLM-L-12-v2.zip into --cache-dir.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "ms-marco-MiniLM-L-12-v2"
ONNX_SHA256 = "d3dd7b09fcf06b0c070081d6819b5effbb40b667bcad78b2d7543400271141d1"  # flashrank-MiniLM-L-12-v2_Q.onnx
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    default_cache = os.path.join(os.environ.get("WBENCH_DATA", os.path.join(REPO, "data")), "hybrid_search", "flashrank")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18444)
    ap.add_argument("--delay-ms", type=float, default=175.0)
    ap.add_argument("--cache-dir", default=default_cache)
    args = ap.parse_args()

    from flashrank import Ranker, RerankRequest

    os.makedirs(args.cache_dir, exist_ok=True)
    ranker = Ranker(model_name=MODEL, cache_dir=args.cache_dir)
    onnx = os.path.join(args.cache_dir, MODEL, "flashrank-MiniLM-L-12-v2_Q.onnx")
    with open(onnx, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    if h != ONNX_SHA256:
        print(f"warning: {onnx} sha256 {h} differs from the development copy {ONNX_SHA256}", file=sys.stderr)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/v1/rerank":
                self.send_error(404)
                return
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            passages = [{"id": i, "text": d} for i, d in enumerate(body["documents"])]
            ranked = ranker.rerank(RerankRequest(query=body["query"], passages=passages))
            results = [
                {"index": r["id"], "relevance_score": float(r["score"]),
                 **({"document": {"text": r["text"]}} if body.get("return_documents") else {})}
                for r in ranked[: body.get("top_n", len(ranked))]
            ]
            payload = json.dumps({"id": "local-sim", "results": results, "meta": {"api_version": {"version": "1"}}}).encode()
            time.sleep(args.delay_ms / 1000)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    print(f"rerank stand-in on {args.host}:{args.port}, FlashRank {MODEL}, delay {args.delay_ms} ms", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
