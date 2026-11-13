# service_qa services

The five HTTP services of the ServiceQA workload (`workloads/service_qa/`),
part of this suite. Details, model revisions and changes from the
reference version: `workloads/service_qa/README.md`.

| File | Service | Port (env) |
|---|---|---|
| `embedder_server.py` | `POST /embed`: all-MiniLM-L6-v2 | 8201 (`RAG_EMBED_PORT`) |
| `vector_search_server.py` | `POST /search`: FAISS IVF-Flat over `passages.npy` | 8202 (`RAG_VEC_PORT`) |
| `bm25_server.py` | `POST /bm25`: rank-bm25 BM25Okapi over `passages.jsonl` | 8203 (`RAG_BM25_PORT`) |
| `reranker_server.py` | `POST /rerank`: cross-encoder ms-marco-MiniLM-L-6-v2 | 8204 (`RAG_RERANK_PORT`) |
| `generator_server.py`, `gen_backend.py` | `POST /generate`: Qwen2.5-1.5B-Instruct, greedy | 8205 (`RAG_GEN_PORT`) |
| `embed_corpus.py` | one-off: `passages.jsonl` -> `passages.npy` | |
| `_shared.py` | request base model, corpus directory | |

Every service also answers `GET /health`. Other settings: `RAG_HOST`
(default 127.0.0.1), `RAG_CORPUS_DIR` (default
`$WBENCH_DATA/service_qa/corpus`, else `<repo>/data/service_qa/corpus`),
`RAG_GEN_BACKEND` (`qwen`, or `template` for a plumbing check),
`RAG_EMBED_MODEL` / `RAG_EMBED_REVISION`, `RAG_RERANK_MODEL` /
`RAG_RERANK_REVISION`, `RAG_QWEN_MODEL` / `RAG_QWEN_REVISION`.

```bash
python3.10 -m venv .venv-qa && .venv-qa/bin/pip install -r servers/service_qa/requirements.txt
.venv-qa/bin/python servers/service_qa/embed_corpus.py        # after workloads/service_qa/prepare_data.py
PYTHON=.venv-qa/bin/python bash servers/service_qa/start_services.sh
bash servers/service_qa/stop_services.sh
```
