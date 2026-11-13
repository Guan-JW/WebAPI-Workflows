"""HybridSearch: one question to the pinned hybrid-search RAG app, asked in a fresh chat.

The unit is the question branch of the app's script (main.py L186-207) with the Streamlit display
calls left out: perform_search, the empty-result gate, then rag() with the app's system prompt,
hybrid_search, max_contexts=5 and an empty chat history, consuming the token stream.

    python run.py --split test                      # needs OPENAI_API_KEY, the index and the rerank stand-in
    python run.py --split test --dry-run            # resolve inputs and print the plan; no API calls

Outputs per unit: `answer` (the streamed answer text) and `chat_request` (the `messages` of the
request sent to the answering LLM, canonical JSON); see README "Measurement" and check.py.
"""
import argparse
import json
import os
import shutil
import socket
import sys
import time
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from wbench import manifest  # noqa: E402
from wbench.harness import UnitResult, Workload, add_common_args, main  # noqa: E402

import app_setup  # noqa: E402

ID = "hybrid_search"
CALLS = ["POST /v1/embeddings (query, perform_search)", "POST /v1/rerank (10 chunks, perform_search)",
         "POST /v1/embeddings (query, rag)", "POST /v1/rerank (20 chunks, rag)",
         "POST /v1/chat/completions (gpt-4o-mini, streamed)"]


class FallbackNotRun(RuntimeError):
    """perform_search returned no chunks; the app would answer with Anthropic (not part of this workload)."""


def add_args(p):
    p.add_argument("--rerank-url", default=os.environ.get("RERANK_URL", app_setup.DEFAULT_RERANK_URL),
                   help="rerank stand-in endpoint (default: %(default)s)")
    p.add_argument("--index", default=None,
                   help="index built by build_index.py (default: data/hybrid_search/index/raglite.sqlite)")
    p.add_argument("--upstream-dir", default=None, help="where fetch_upstream.sh put the app (default: ./upstream)")
    p.add_argument("--dry-run", action="store_true", help="resolve inputs and print the plan; make no API calls")


def index_path(args):
    return os.path.abspath(args.index or os.path.join(manifest.data_dir(ID), "index", "raglite.sqlite"))


def setup(ctx):
    args = ctx.args
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    src = index_path(args)
    if not os.path.exists(src):
        raise SystemExit(f"index not found: {src} (run build_index.py)")
    u = urlsplit(args.rerank_url)
    try:
        socket.create_connection((u.hostname, u.port or 80), timeout=3).close()
    except OSError as e:
        raise SystemExit(f"rerank stand-in not reachable at {args.rerank_url}: {e} (start rerank_standin.py)")
    # Each client process queries its own byte-identical copy of the index: the query path only
    # reads, but SQLite in WAL mode keeps -wal/-shm files next to the database.
    db = os.path.join(ctx.workdir, "raglite.sqlite")
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(db + ext):
            os.remove(db + ext)
    shutil.copyfile(src, db)
    ctx.state["index_sha256"] = manifest.sha256_file(src)
    if manifest.sha256_file(db) != ctx.state["index_sha256"]:
        raise SystemExit("index copy differs from its source")
    app = app_setup.load_app(args.upstream_dir)
    config = app_setup.build_config(db, args.rerank_url)
    app_setup.install_config(config)
    ctx.state.update(app=app, config=config)
    # The rerank client prints every response to stdout (rerankers APIRanker._parse_response).
    # The measured runs discarded stdout; so does this driver. Harness messages go to stderr.
    ctx.state["stdout"] = sys.stdout
    sys.stdout = open(os.devnull, "w")


def teardown(ctx):
    if ctx.state.get("stdout") is not None:
        sys.stdout.close()
        sys.stdout = ctx.state["stdout"]


def _chat_request(ctx):
    """`messages` of the last chat-completions request of this unit, as canonical JSON bytes."""
    chats = [c for c in ctx.recorder.calls if c.path().endswith("/chat/completions") and c.req_body]
    if not chats:
        return None
    messages = json.loads(chats[-1].req_body.decode("utf-8"))["messages"]
    return json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")


def run_one(unit, ctx):
    app, config = ctx.state["app"], ctx.state["config"]
    question = unit["question"]
    parts, t_first = [], None
    with ctx.timed():
        t0 = time.time()
        reranked_chunks = app.perform_search(query=question)                      # L186
        if not reranked_chunks or len(reranked_chunks) == 0:                      # L187
            raise FallbackNotRun("no chunks retrieved; the app would fall back to Anthropic (not run)")
        formatted_messages = []                                                   # L192-193, fresh chat
        response_stream = app.rag(prompt=question, system_prompt=app.RAG_SYSTEM_PROMPT,
                                  search=app.hybrid_search, messages=formatted_messages,
                                  max_contexts=5, config=config)                  # L195-200
        for chunk in response_stream:                                             # L203-205
            if chunk and t_first is None:
                t_first = time.time()
            parts.append(chunk)
    answer = "".join(parts)
    chat = _chat_request(ctx)
    extra = {"ttft_ms": round((t_first - t0) * 1000, 1) if t_first else None,
             "n_contexts": chat.decode("utf-8").count("<context index=") if chat else None,
             "answer_chars": len(answer), "index_sha256": ctx.state["index_sha256"]}
    return UnitResult({"answer": answer.encode("utf-8"), "chat_request": chat}, extra)


WORKLOAD = Workload(id=ID, run_one=run_one, add_args=add_args, setup=setup, teardown=teardown, keep_bodies=True)


def dry_run(argv):
    """Resolve the split, files, upstream app and configuration; print the plan. No API calls."""
    p = argparse.ArgumentParser(prog=f"{ID}/run.py")
    add_common_args(p)
    add_args(p.add_argument_group(ID))
    args = p.parse_args(argv)
    units = manifest.load(ID, args.split)
    groups = [[u] for u in units][: args.limit] if args.limit else [[u] for u in units]
    i, n = (int(x) for x in args.shard.split("/"))
    groups = groups[i::n]
    print(f"workload {ID}, split {args.split}: {len(units)} units, {len(groups)} after --limit/--shard")
    d = app_setup.app_dir(args.upstream_dir)
    ok_app = os.path.exists(os.path.join(d, "main.py")) and \
        manifest.sha256_file(os.path.join(d, "main.py")) == app_setup.APP_SHA256
    print(f"upstream app: {d} ({'ok' if ok_app else 'MISSING or hash differs'})")
    if ok_app:
        app = app_setup.load_app(args.upstream_dir)
        cfg = app_setup.build_config(os.path.join(args.workdir or "runs/hybrid_search/dryrun", "raglite.sqlite"),
                                     args.rerank_url)
        print(f"app imported: {app.__file__}; llm={cfg.llm} embedder={cfg.embedder} "
              f"reranker={type(cfg.reranker).__name__}({cfg.reranker.model}) -> {cfg.reranker.url}")
    idx = index_path(args)
    print(f"index: {idx} ({'present' if os.path.exists(idx) else 'not built yet: build_index.py'})")
    print(f"calls per unit ({len(CALLS)}): " + "; ".join(CALLS))
    for g in groups:
        u = g[0]
        print(f"  {u['input_id']}  {u['arxiv_id']}  {u['question'][:70]!r}")


if __name__ == "__main__":
    if "--dry-run" in sys.argv[1:]:
        dry_run(sys.argv[1:])
    else:
        main(WORKLOAD)
