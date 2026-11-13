# HybridSearch

A user has loaded ten research articles (PDFs) into a retrieval-augmented chat app and asks a
question about them. The app embeds the question, searches its index with vector and keyword
search, reranks the hits, and streams an answer from an LLM grounded in the best passages. One unit
of work is one question, asked in a fresh chat.

| | |
|---|---|
| Domain | Retrieval-augmented question answering over PDFs |
| Source | awesome-llm-apps `rag_tutorials/hybrid_search_rag` at `6c16b23` (Apache-2.0), run unmodified |
| Services | OpenAI embeddings and chat (hosted); rerank stand-in for Cohere (self-hosted, local) |
| Calls per unit | 5: 2 embeddings, 2 rerank, 1 streamed chat completion |
| Inputs | QASPER, 5 profiling / 25 test questions over one index of 10 documents |
| Unit | one question |

## Source

Application: `rag_tutorials/hybrid_search_rag` of
[Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) at commit
`6c16b23f1bacd0fdf240bb5141ef45e59e82c306` (Apache-2.0). `fetch_upstream.sh` fetches it and checks
the sha256 of `main.py`, `requirements.txt`, `README.md` and `LICENSE`. The app code is imported
unmodified. It uses RAGLite 0.2.1 and rerankers 0.6.0, both pinned by the app. Hashes, versions and
datasets are in `source.json`.

### Adaptations

1. **Answering LLM: `gpt-4o-mini` instead of `claude-3-opus-20240229`.** The upstream model is
   retired, and no Anthropic key was available. Embedder and all retrieval settings are the app's:
   `text-embedding-3-large`, `embedder_normalize=True`, `chunk_max_size=2000`,
   `embedder_sentence_window_size=2`, `max_contexts=5`, `RAG_SYSTEM_PROMPT`.
2. **Rerank goes to a stand-in service (`rerank_standin.py`) instead of api.cohere.ai.** No Cohere
   key was available. The app's own Cohere client (`Reranker("cohere", lang="en")`, model
   `rerank-english-v3.0`) is kept, and only its `url` is pointed at the stand-in.
   - What it does: it answers `POST /v1/rerank` in Cohere's v1 format. It scores with FlashRank
     `ms-marco-MiniLM-L-12-v2` on the CPU and then sleeps a fixed 175 ms before replying.
   - The delay stands in for the network round trip to Cohere. It was taken from a probe of
     api.cohere.ai (fresh TCP and TLS, about 20 KB body, 401 reply). The saved probe holds 12 samples
     from 176 to 351 ms, median 217 ms, so 175 ms is close to the fastest sample.
   - Run history: an early run on 2026-11-01 used FlashRank in-process, with no HTTP rerank. Every
     later measurement, including the ones this card's numbers come from, used this stand-in. This
     workload ships the stand-in.
3. **Configuration built by the driver** (`app_setup.build_config`) instead of the sidebar form
   (`initialize_config`, L23-56). `db_url` is a SQLite file chosen by the driver; SQLite is the UI's
   default backend. Only the values in 1 and 2 differ from `initialize_config`.
4. **Headless driver.** `run.py` runs the question branch of `main()` (L186-207) without its
   Streamlit display calls. Each question is asked in a fresh chat, so the history passed to `rag()`
   is empty.
5. **The fallback branch is not run.** That branch (L187-190, answer with Anthropic when the search
   finds nothing) needs an Anthropic key. A unit that reaches it is recorded as an error. It was
   never reached on this corpus during development.
6. **Index built without the upload widget.** `build_index.py` calls the app's `process_document`
   on each PDF path. The upload widget would first copy the file to `temp_<name>`. RAGLite derives
   the document id from the file bytes, so only the stored filename differs.
7. **Environment:**
   - `LITELLM_LOCAL_MODEL_COST_MAP=True`: litellm 1.53.9 cannot parse today's online model map, and
     RAGLite would then assume a 2,048-token context and refuse to answer.
   - `TOKENIZERS_PARALLELISM=false`.
8. **stdout is discarded during runs.** rerankers prints every rerank response, and the
   development runs discarded stdout too. Harness messages go to stderr.
9. **The app import holds a file lock.** Importing RAGLite builds its default configuration, which
   loads two FlashRank models from `./.flashrank_cache` and downloads them (about 120 MB) if they are
   missing. The workload does not use them, but concurrent first imports would race on the download.
10. **Dependency pins added to the app's:** litellm 1.53.9 (1.15-1.52 are no longer on PyPI), numpy
    1.26.4 (spacy 3.7 and thinc), llama-cpp-python 0.3.2 (imported by RAGLite; the 0.3.35 metal wheel
    was malformed).
11. **HTTP accounting.** The pinned openai 3.42.0 sends its requests with `httpx2`;
    `wbench.http_recorder` records those calls. The streamed chat answer is counted as 0
    response bytes (see `docs/results.md`).

## Workflow

One unit, in order:

1. `perform_search(question)` (main.py L79-100):
   - `hybrid_search(q, num_results=10)` sends **POST /v1/embeddings** with the question
     (`text-embedding-3-large`).
   - Vector search and keyword search then run locally on SQLite, 100 hits each, merged by
     reciprocal rank (RRF).
   - `retrieve_chunks` reads the top 10 chunks.
   - `rerank_chunks` sends **POST /v1/rerank** with the question and the 10 chunk texts, and gets
     the reordered list back.
2. **The gate** (L187). If that list is empty, the app falls back to Anthropic (adaptation 5).
   Otherwise the list is not used further.
3. `rag(question, search=hybrid_search, max_contexts=5, messages=[])` (RAGLite `_rag.py`):
   - `hybrid_search(q, num_results=20)` sends a second **POST /v1/embeddings**, with the same
     question, and searches locally again.
   - `rerank_chunks` sends **POST /v1/rerank** with 20 chunks.
   - The top 5 chunks are extended with their neighbours, merged into segments, and placed in the
     system prompt as `<context>` blocks.
4. **POST /v1/chat/completions** (`gpt-4o-mini`, `stream=True`) with that system prompt and the
   question. The driver consumes the stream to the last token.

## Inputs

[QASPER](https://huggingface.co/datasets/allenai/qasper) (CC BY 4.0) at revision `fdc9d821`:
- the 10 documents in test-split rows 0-9 and all of their 30 questions;
- profiling: the first 5 questions; test: the other 25;
- no sampling and no seed.

The PDFs are arXiv e-prints, fetched from `https://arxiv.org/pdf/<id>` under each article's arXiv
license and checked against the sha256 in the manifest. The rule, the source hashes and the
revision check are in `manifests/hybrid_search/SELECTION.md`.

## Deployment

**Hosted services.** OpenAI `text-embedding-3-large` and `gpt-4o-mini`, streamed. There is no
replica count.

**Rerank stand-in.** One `rerank_standin.py` process (127.0.0.1:18444, a ThreadingHTTPServer)
serves all client processes. Its FlashRank model stays loaded.

**Index.** `build_index.py` builds the index once. This makes paid embedding calls. The development
index held 10 documents and 214 chunks in a 109 MB SQLite file. Each client process queries its own
byte-identical copy in its `--workdir`, made in `setup`: the query path only reads, but SQLite in WAL
mode keeps `-wal`/`-shm` files next to the database.

**Caches.** RAGLite keeps its database engine and search index loaded within a process. There is no
result cache across questions.

**Development hardware.** Apple Silicon Mac (14 cores, 48 GB), CPython 3.11.18 arm64. The stand-in
ran on the same machine, so its scoring shared the client's CPU.

## Measurement

**Timed window.** From `perform_search` to the last streamed token (the `ctx.timed()` block in
`run.py`).

**Outputs.**
- `answer`: the streamed text.
- `chat_request`: the `messages` of the chat-completions request, as canonical JSON (sorted keys,
  UTF-8).
- `extra`: `ttft_ms`, `n_contexts`, `answer_chars`, and `index_sha256`, the index the run used.

**Equivalence rule** (`check.py`). A request is equivalent when its `chat_request` equals one of the
reference's requests for the same question, over all timed ok reference rows. This is the request
sent to the answering LLM. The answer text is not compared, because the hosted LLM need not repeat
itself. Both runs must use the same index.

**Development reference** (2026-11-09, one client, 16 requests):
- mean / p50 / p95 latency 4733 / 4591 / 7059 ms;
- 0 errors and 0 HTTP 429 or 5xx responses;
- every request sent 2 embeddings, 2 reranks and 1 chat call.

The p50 was 3.0 s on 2026-11-02 with byte-identical requests, so compare runs only within one
session.

## Running

```bash
cd workloads/hybrid_search
./fetch_upstream.sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --index-strategy unsafe-best-match \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/metal -r requirements.txt   # see the file's header
.venv/bin/python -I prepare_data.py                      # 10 PDFs into data/hybrid_search/, sha256-checked
export OPENAI_API_KEY=...                                # paid calls from here on
.venv/bin/python build_index.py                          # data/hybrid_search/index/raglite.sqlite
.venv/bin/python rerank_standin.py &                     # leave running; one for all clients
.venv/bin/python run.py --split test --dry-run           # plan only, no API calls
.venv/bin/python run.py --split test                     # 1 warm-up + 3 timed rounds -> runs/hybrid_search/
.venv/bin/python check.py <reference.jsonl> --candidate <candidate.jsonl>
cd ../.. && workloads/hybrid_search/.venv/bin/python -m wbench.closed_loop hybrid_search --clients 4
python -m wbench.summarize runs/hybrid_search/*.jsonl
```

## Known limitations

- **The rerank stand-in is not Cohere.** Its scores and order differ, its delay is fixed, and its
  scoring competes with the clients for the CPU.
- **The answering model is not the app's.** `claude-3-opus` would be slower and would change the
  latency mix.
- **Rebuilt indexes can differ.** Embedding responses are not bit-stable across calls, so a rebuilt
  index can retrieve differently. Compare runs only on the same index (`extra.index_sha256`).
- **Streamed responses count 0 bytes.** The recorder does not read a streamed response, so the chat
  call's response bytes are 0.
- **Warm-up differs from development.** The development runs used one warm-up question per process.
  wbench's default warm-up round runs every unit once.
- **llama-cpp-python is platform-specific.** The development install used a macOS arm64 wheel; other
  platforms build it from source.
