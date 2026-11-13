# ChatWithPDF

A user opens a Streamlit page, enters an OpenAI key, uploads one PDF (a research article) and asks
it several questions in a row. Streamlit reruns the whole script on every interaction, and this
script builds a new embedchain App with a new temporary Chroma index on every rerun, adds the
uploaded PDF to it again, then answers the question with the session's chat history. One unit of
work is one question's script run within a document session.

| | |
|---|---|
| Domain | Chat over one uploaded PDF |
| Source | awesome-llm-apps `advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf` at `6c16b23` (Apache-2.0), run unmodified |
| Services | OpenAI embeddings and chat (hosted) |
| Calls per unit | 3: embeddings of every chunk, embedding of the question, chat completion |
| Inputs | QASPER, 8 profiling / 37 test questions (2 / 10 document sessions) |
| Unit | one question (script run) in a document session |

## Source

Application: `advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf/chat_pdf.py` of
[Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) at commit
`6c16b23f1bacd0fdf240bb5141ef45e59e82c306` (Apache-2.0). `fetch_upstream.sh` fetches it and checks
the sha256 of `chat_pdf.py`, `requirements.txt` and `LICENSE`.

The script runs byte for byte as published. Its requirements are unpinned (`streamlit`,
`embedchain`, `streamlit-chat`). `requirements.txt` pins what they resolved to in development:
embedchain 0.1.128 (the last release; the project was archived on 2026-05-22), streamlit 1.66.1,
chromadb 0.5.23 and openai 1.109.1. No model, key or service was replaced. The models are
embedchain's defaults: `text-embedding-ada-002`, and `gpt-4o-mini` with temperature 0 and
max_tokens 1000.

### Adaptations

1. **Headless driver.** `streamlit.testing.v1.AppTest` runs the unmodified script, one script run per
   user interaction. The key, the upload and each question go through the app's own widgets, found
   by their labels. `FileUploader.set_value` uses Streamlit's own upload path, so no shim is needed.
2. **The API key comes from `OPENAI_API_KEY`**, typed into the app's "OpenAI API Key" field. It is
   never logged.
3. **`EC_TELEMETRY=False`.** This is embedchain's documented opt-out of its PostHog analytics. Those
   events are not workflow calls.
4. **`EMBEDCHAIN_CONFIG_DIR=<client workdir>/ec_home`.** This keeps embedchain's config file out of
   the home directory and separate per client.
5. **`EMBEDCHAIN_DB_URI` points at a fresh SQLite file per document session**, set before every
   script run. embedchain keeps chat history in one process-wide metadata database, and the next App
   reads it. A fresh file is the app's first launch, so sessions do not see each other's history.
   Within a session, history accumulates as it does in the app.
6. **`TMPDIR=<client workdir>/tmp`.** The app's `mkdtemp` vector databases and its upload temporary
   files stay in the client's directory. A session's entries are deleted when the session ends,
   outside any timed window.
7. **Chroma's client cache is cleared after each session** (`SharedSystemClient.clear_system_cache()`
   and garbage collection, untimed). The app opens a new Chroma client on every rerun and never
   closes it.

## Workflow

**Session set-up.** Untimed, in this order:
1. Load the page: 0 calls.
2. Type the key (L17-21): 0 calls. The script builds an App on a new temporary directory.
3. Upload the PDF (L23-30): **POST /v1/embeddings** with every chunk.

**One question.** Typing it and pressing Enter reruns L15-36:
1. L19-21: a new temporary directory and a new embedchain App with a Chroma vector store.
2. L25-29: the upload is written to a temporary file, then `app.add` runs. It parses the PDF
   locally (pypdf), chunks it, and sends **POST /v1/embeddings** with every chunk. The temporary file
   is then deleted.
3. L34-35: `app.chat(question)` sends **POST /v1/embeddings** with the question and queries Chroma
   locally. It then builds one prompt from the retrieved chunks and the session's earlier questions
   and answers (embedchain adds up to 10 earlier rounds) and sends **POST /v1/chat/completions**.
4. L36: the answer is written to the page.

## Inputs

[QASPER](https://huggingface.co/datasets/allenai/qasper) (CC BY 4.0) at revision `fdc9d821`, seed
20261103:
- profiling: 2 documents from the validation split;
- test: 10 documents from the test split, excluding rows 0-9, which HybridSearch uses;
- per document, the first 4 questions in dataset order (3 if the document has only 3).

The PDFs are arXiv e-prints, fetched from `https://arxiv.org/pdf/<id>` under each article's arXiv
license and checked against the sha256 in the manifest. A document's questions form one session
(wbench `group_key`); they always run together, in order. Details are in
`manifests/chat_with_pdf/SELECTION.md`.

## Deployment

**Services.** Hosted OpenAI APIs only; there is no replica count.

**Local state.**
- One Chroma directory per script run (the app's behavior).
- One embedchain metadata database per session.
- Each client process has its own `TMPDIR` and `EMBEDCHAIN_CONFIG_DIR` under its `--workdir`, and
  each session its own `AppTest`, which holds `st.session_state`.
- No cache lives across script runs: the app rebuilds its index every time.

**Closed loop.** `setup` opens every session the client will need (load, key, upload) before the
timed window, so the window holds question runs only. The warm-up question runs in its own,
throwaway session.

**Development hardware.** Apple Silicon Mac, CPython 3.11.18 arm64. The parsing, chunking and
Chroma work of each question runs on the client CPU.

## Measurement

**Timed window.** The question's `AppTest.run()`.

**Outputs.**
- `answer`: the text shown.
- `chat_request`: the `messages` of the chat-completions request, as canonical JSON.
- `extra`: `session`, `q_index`, `history_sha256` (the session's earlier answers) and
  `tmp_entries_created` (one index directory per run).

**Equivalence rule** (`check.py`). Each candidate question run is paired with the reference run at
the same round, client, question and visit, and judged:
- **identical**: the chat messages are byte-identical;
- **history differs**: they differ, and so do the session's earlier answers. A hosted LLM need not
  repeat an earlier answer, so this case is not counted either way;
- **DIFFERS**: they differ although the history is identical.

Any DIFFERS fails the check. Run a second baseline against the first (A/A) to see the noise floor.
During development, the unmodified app itself sent one of two different requests for the first
question of 1911.01214, which has no history. This happened in 1 of 80 first-question runs, and it
is the only DIFFERS seen.

**Development reference** (2026-11-09, one client, 16 question runs):
- mean / p50 / p95 latency 2097 / 1770 / 3514 ms;
- 0 errors and 0 HTTP 429 responses;
- per question, about 5.9k embedding tokens and 0.9k chat tokens (a smoke run on profiling
  document 1904.07904).

## Running

```bash
cd workloads/chat_with_pdf
./fetch_upstream.sh
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -I prepare_data.py              # 12 PDFs into data/chat_with_pdf/, sha256-checked
.venv/bin/python run.py --split test --dry-run   # loads the page once (no key, no API call), prints the plan
export OPENAI_API_KEY=...                        # paid calls from here on
.venv/bin/python run.py --split test             # 1 warm-up + 3 timed rounds; sessions keep their order
.venv/bin/python check.py <reference.jsonl> --candidate <candidate.jsonl>
cd ../.. && workloads/chat_with_pdf/.venv/bin/python -m wbench.closed_loop chat_with_pdf --clients 4
python -m wbench.summarize runs/chat_with_pdf/*.jsonl
```

## Known limitations

- **embedchain is archived.** The pinned versions are the only tested ones.
- **Chunk embeddings are not bit-stable.** Identical embedding requests do not return
  byte-identical vectors. In development, chat requests still matched whenever the history matched.
- **Closed-loop pre-opening copies the harness's order.** `setup` reproduces the harness's
  closed-loop order to decide which sessions to open. A session it did not foresee is opened when
  needed, inside the window but untimed.
- **Session dealing differs from development.** wbench deals sessions to clients in manifest order;
  the development runs shuffled them first (seed 20261109).
- **AppTest is not a browser.** It runs the script in-process, with no websocket or front-end.
