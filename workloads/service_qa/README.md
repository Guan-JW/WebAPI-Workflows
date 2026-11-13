# ServiceQA

A user asks a self-hosted support or knowledge-base assistant a question. The
assistant is built from five microservices: it embeds the question, retrieves
passages from a 100 000-passage collection with a dense and a sparse
retriever, merges and reranks the candidates, and has a small instruction-
tuned language model write a short answer from the top passages. One unit of
work is one question.

| | |
|---|---|
| Domain | Retrieval-augmented question answering (support / knowledge-base assistant) |
| Source | Derived from self-hosted support and knowledge-base assistants; five FastAPI services in this suite, built on sentence-transformers, FAISS, rank-bm25, a cross-encoder reranker and Qwen2.5-1.5B-Instruct |
| Services | 5 self-hosted FastAPI services: embedder (all-MiniLM-L6-v2), dense retrieval (FAISS IVF-Flat over 100k MS MARCO passages), sparse retrieval (BM25, rank-bm25), reranker (cross-encoder ms-marco-MiniLM-L-6-v2), generator (Qwen2.5-1.5B-Instruct) |
| Calls per unit | 5, sequential: embed, search, bm25, rerank, generate |
| Inputs | MS MARCO v2.1 dev questions, 60 profiling / 60 test / 60 test2; each split is 50 distinct questions plus 10 exact repeats of 10 of them |
| Unit | one question |

## Source

The workload is derived from self-hosted support and knowledge-base
assistants. The five services and the client are part of this suite.

The same call pattern appears in public code, for example in [OPEA GenAIExamples ChatQnA](https://github.com/opea-project/GenAIExamples/blob/f56422671c8bdf46f59dd758c8c9e38ca41d6555/ChatQnA/chatqna.py#L262-L301); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

The upstream components are used unmodified, at pinned versions:

| Component | Version / revision | License |
|---|---|---|
| sentence-transformers/all-MiniLM-L6-v2 (embedder) | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 |
| cross-encoder/ms-marco-MiniLM-L-6-v2 (reranker) | `233902d25c440f23af6f7d6e94d2946bac0bee0a` | Apache-2.0 |
| Qwen/Qwen2.5-1.5B-Instruct (generator) | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | Apache-2.0 |
| sentence-transformers / transformers / torch | 6.2.0 / 5.20.2 / 2.14.1 | Apache-2.0 / Apache-2.0 / BSD-3-Clause |
| faiss-cpu / rank-bm25 | 1.15.1 / 0.2.2 | MIT / Apache-2.0 |
| MS MARCO v2.1 dev (questions and passages) | Hugging Face `microsoft/ms_marco` at `a47ee7aae8d7d466ba15f9f0bfac3b3681087b3a` | MS MARCO terms (non-commercial research) |

Model file hashes are in `source.json`. The Hugging Face name of the
cross-encoder now redirects to `cross-encoder/ms-marco-MiniLM-L6-v2`; the
pinned revision is the same repository.

Changes from the version used for the reference runs:

- Tracing removed from the services and the client.
- Endpoints and options the workflow does not call are not included. Each
  service exposes only `GET /health` and the one POST endpoint listed under
  Workflow. The reranker no longer loads a doc_id-to-passage table, which
  only served candidates sent without passage text.
- Model revisions are pinned (`RAG_EMBED_REVISION`, `RAG_RERANK_REVISION`,
  `RAG_QWEN_REVISION`) to the snapshots the reference deployment had cached;
  the reference services loaded the default branch.
- The generator defaults to the configuration of the reference runs (Qwen
  backend, Qwen2.5-1.5B-Instruct); the earlier default was a template
  backend and Qwen2.5-0.5B-Instruct. The template backend is kept for
  checking the plumbing without a model and is not for measurements.
- The corpus is rebuilt from the parquet with pyarrow instead of the
  `datasets` library. The result is byte-identical (sha256 checked).
- The manifests do not contain the question texts; `prepare_data.py`
  extracts them from the parquet.

## Workflow

Every request body also carries `trace_id` (`tr_` + 12 hex digits, one per
question) and `node_id` (the step name); the services ignore both.
Parameters (as in the reference runs): `top_k` 10, `top_n` 10, `rerank_k` 5,
`max_new_tokens` 64, HTTP timeout 120 s. Transport errors are retried up to
three times (50, 150, 450 ms back-off).

| # | Call | Sent | Returned | Used by |
|---|---|---|---|---|
| 1 | `POST embedder:8201/embed` | `texts: [question]` | 384-d normalized vector, `dim`, `model` | vector to call 2 |
| 2 | `POST vector_search:8202/search` | `query_vec`, `top_k` | `top_k` hits: `doc_id`, `score`, `passage_text`, `metadata` | merge |
| 3 | `POST bm25:8203/bm25` | `query`, `top_k` | `top_k` hits, same fields | merge |
| - | client merge | | union by `doc_id`, score = max of the two, sorted by score, first `top_n` | call 4 |
| 4 | `POST reranker:8204/rerank` | `query`, `candidates` (merged hits with passage text), `top_k` = `rerank_k` | `rerank_k` hits with the cross-encoder score | prompt |
| - | client prompt | | `"Context:\n- <passage>\n...\n\nQuestion: <q>\nAnswer:"` | call 5 |
| 5 | `POST generator:8205/generate` | `prompt`, `max_new_tokens` | `answer`, `tokens_in`, `tokens_out`, `cancelled`, `backend` | the result |

Calls 2 and 3 both depend only on the question (and its vector); the client
issues them one after the other. Retrieved passages travel to the client in
full and are sent back to the reranker.

## Inputs

MS MARCO v2.1 dev, from the Hugging Face parquet pinned above (sha256
`a07a87f4…`). The MS MARCO terms allow non-commercial research use only and
extend no license; the Hugging Face card gives none.

- Corpus: the first 100 000 distinct passage texts of the parquet, in file
  order (sha256 `f3dd62a7…`).
- profiling (60): the first 50 distinct questions of the parquet plus 10
  repeats drawn with seed 42; fixed before the test splits existed.
- test (60) and test2 (60): questions whose passages are all in the corpus,
  disjoint from profiling and from each other, drawn with seed 20261030; 50
  per split plus 10 repeats of 10 of them (seeds 20261031 and 20261032).

The repeats are part of the input distribution: in every split, 10 of the 60
units ask a question that another unit of the same split asks too
(`is_duplicate`, `dup_of`). Selection rules and counts:
`manifests/service_qa/SELECTION.md`.

## Deployment

1. `workloads/service_qa/prepare_data.py` downloads the parquet (about
   210 MB, or `--parquet PATH`), writes `data/service_qa/corpus/passages.jsonl`
   and one file per question under `data/service_qa/queries/`, and checks the
   hashes.
2. `servers/service_qa/embed_corpus.py` embeds the corpus into
   `passages.npy` (100 000 x 384 float32). The reference embedding was made
   on CUDA (sha256 `600d8803…`); on other hardware the low-order bits can
   differ.
3. `servers/service_qa/start_services.sh` starts the five services on
   127.0.0.1:8201-8205 and waits until both indexes are loaded;
   `stop_services.sh` stops them.

Python 3.10; `servers/service_qa/requirements.txt` pins the versions of the
reference environment (Linux x86_64, CUDA 13.0 torch build). The models are
downloaded from Hugging Face on first use.

What stays loaded: the vector service trains the IVF-Flat index (inner
product, nlist 316, nprobe 19) on the corpus vectors at every start; the BM25
service tokenizes the corpus and builds its index at start and scores every
passage for each query; the three models load on their first request and stay
in memory (embedder and reranker on the GPU when one is visible, generator in
float16 on the GPU). Generation calls are serialized by a lock. Each service
is one uvicorn process with default settings (access log on). There are no
caches.

Reference runs: all five services on one node with one NVIDIA A40 (46 GB),
AMD EPYC 7763, RHEL 9.6, Python 3.10.22; client on an Apple Mac (Python
3.10.18, httpx 0.28.1) over an SSH tunnel with a ping round trip of about
30 ms.

## Measurement

The timed window covers the five calls of one question. Reading the
question file, creating the HTTP client and encoding the outputs are outside
it. Each unit uses a new `httpx.Client`, so connections are opened inside
the window.

| Output | Content |
|---|---|
| `rerank_doc_ids` | ordered doc ids returned by `/rerank` |
| `prompt` | the prompt sent to `/generate` |
| `answer` | the generated answer |
| `merged_doc_ids` | ordered doc ids sent to `/rerank` |
| `rerank_scores` | reranker scores (JSON) |

`extra` holds `rerank_doc_ids`, `rerank_scores`, `is_duplicate`, `n_vec`,
`n_bm25`, `tokens_in`, `tokens_out` and `backend`.

Equivalence rule (`python workloads/service_qa/check.py reference.jsonl
candidate.jsonl`): `rerank_doc_ids` and `prompt` identical, every reranker
score within 1e-4; differences in `answer` and `merged_doc_ids` are
reported. On the reference hardware all five outputs, the answer included,
were identical across rounds and across eight separate service starts.

## Running

```bash
# data and corpus
python3.10 -m venv .venv && .venv/bin/pip install -r workloads/service_qa/requirements.txt
.venv/bin/python workloads/service_qa/prepare_data.py

# services (GPU node, Python 3.10)
python3.10 -m venv .venv-qa && .venv-qa/bin/pip install -r servers/service_qa/requirements.txt
.venv-qa/bin/python servers/service_qa/embed_corpus.py
PYTHON=.venv-qa/bin/python bash servers/service_qa/start_services.sh

# client
.venv/bin/python workloads/service_qa/run.py --split test --warmup 1 --rounds 3 \
    --out runs/service_qa/test.jsonl
.venv/bin/python -m wbench.summarize runs/service_qa/test.jsonl
bash servers/service_qa/stop_services.sh
```

Service URLs: `--embed-url`, `--vec-url`, `--bm25-url`, `--rerank-url`,
`--gen-url`; parameters: `--top-k`, `--top-n`, `--rerank-k`,
`--max-new-tokens`, `--timeout-s`. The warm-up round absorbs the model loads.

## Known limitations

- MS MARCO is for non-commercial research use only.
- Dense retrieval depends on the corpus embedding and on the IVF index
  trained at service start; on other hardware or library versions some
  queries can get different neighbours, and then a different prompt and
  answer.
- The corpus covers only the first 10 215 dev records, and the test questions
  are restricted to records whose passages are all in it.
- In the reference runs the trace id carried run metadata and was 35-46
  characters longer, so each request body was that many bytes larger; the
  reference services also built and discarded a trace record per request.
  Neither is part of this release.
- The generator answers from at most 64 new tokens; answers are short and
  sometimes cut off.
