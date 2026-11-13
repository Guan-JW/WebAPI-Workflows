# CodeReview

A developer submits one Python source file for automated review. A pipeline
of four HTTP services parses the file, lints it, scans it for security issues
and writes a short review that ends in a verdict (`approve` or
`request_changes`). One unit of work is the review of one file.

| | |
|---|---|
| Domain | Developer tooling: automated code review |
| Source | A practice project on multi-service web APIs by an outside developer, included in adapted form |
| Services | 4 self-hosted FastAPI services: parser (Python `ast`), linter (ruff 0.15.12), security scanner (Bandit 1.9.4), summarizer (deterministic template) |
| Calls per unit | 5, sequential: parse, lint, scan, parse, summarize |
| Inputs | CPython 3.9.6 standard library modules, 35 profiling / 20 test / 15 test2 |
| Unit | one source file |

## Source

An outside developer wrote the pipeline as a practice project on multi-service
web APIs (version of 2026-04-29). The services and the client are included
here in adapted form; the changes are listed below.

The same call pattern appears in public code, for example in [pr-agent](https://github.com/The-PR-Agent/pr-agent/blob/8257f6adb2514889fe2f3a96f332a010a4c36538/pr_agent/commands/pr_reviewer.py#L328-L387); see the [README](../../README.md#the-same-call-patterns-in-public-projects) for the lines.

What comes from where: `servers/code_review/*_server.py` and `_shared.py` from
the upstream `server/code_review/`; the summarizer's template from upstream
`llm_backend.py` (`TemplateBackend`); `start_services.sh` from upstream
`scripts/code_review/run_all_servers.sh`; `review_client.py` from upstream
`client/code_review/basic_client.py`.

Adaptations:

- Tracing removed. The services and the client no longer import the upstream
  profiling helper, no longer write a trace record per request, and the
  services no longer print a log line per request.
- Code the workflow does not use is removed: the parser's `GET /ast/{id}`
  endpoint and its in-memory AST store, the `ast_id` request field of `/lint`
  and `/scan`, the `fields`-based trimming of the `/lint` and `/scan`
  responses, the services' `--parser-url` option and the summarizer's
  optional local-LLM backend (the reference runs used the template). The
  client still sends the `fields` query parameter with every field listed,
  as the original client does; the services now ignore it and always return
  every field, which is what the original returned for that parameter.
- ruff runs with `--isolated`, so a `pyproject.toml` or `ruff.toml` above the
  service's working directory cannot change the rule set. On all 70 inputs
  ruff's output is identical with and without the flag.
- The reference deployment ran a locally modified copy of the scanner that
  adds other execution modes, started in the mode that runs the commit's code
  path (one Bandit process per request, no result cache) on a separate port.
  The modification is not included; the released scanner is the commit's
  code on the upstream default port 8103.
- Inputs are fetched from a python.org tarball and one CPython git file
  instead of being read from a local Python installation.

## Workflow

Every request body also carries `trace_id` (`tr_` + 12 hex digits, one per
unit) and `node_id` (the step name); the services ignore both. HTTP timeout
60 s per call.

| # | Call | Sent | Returned | Used by |
|---|---|---|---|---|
| 1 | `POST parser:8101/parse` | `source` | `ast_json`, `symbols`, `loc`, `ast_id` | `ast_json` to calls 2 and 3 |
| 2 | `POST linter:8102/lint?fields=diagnostics,counts,full_report` | `source`, `ast_json` | `diagnostics` (code, message, line, column, severity), `counts`, `full_report_text` | counts and first 3 diagnostics to call 5 |
| 3 | `POST scanner:8103/scan?fields=issues,severity_max,cwe_refs` | `source`, `ast_json` | `issues`, `severity_max`, `cwe_refs` | `severity_max` and `issues` to call 5 |
| 4 | `POST parser:8101/parse` | `source` | as call 1 | not used |
| 5 | `POST summarizer:8104/summarize` | `source`, `lint_summary`, `sec_summary` | `review_text`, `action`, `tokens_in`, `tokens_out` | the result |

Severities: ruff codes starting with E or F count as errors, W as warnings,
others as info. The summarizer returns `approve` when there are no lint errors
and the highest Bandit severity is NONE, LOW or UNDEFINED.

## Inputs

Python modules of the CPython 3.9.6 standard library (PSF-2.0), with lines
of code (non-blank, non-comment) between 50 and 300. `prepare_data.py`
downloads the python.org 3.9.6 tarball (sha256 `d0a35182…`) and one file from
CPython v3.9.16, extracts the listed files into `data/code_review/` and checks
every sha256.

- profiling (35): a fixed set, stratified 12/12/11 over the LOC buckets
  50-120 / 121-220 / 221-300 with seed 42, top-level modules only.
- test (20) and test2 (15): new modules, seed 20261030, top-level modules
  first and sub-package modules after; both splits contain only files of
  50-220 LOC.

Selection rules, pools, exclusions and hashes: `manifests/code_review/SELECTION.md`.

## Deployment

Python 3.10 for the services (`ast.dump` output, and therefore payload sizes,
change between Python versions). `servers/code_review/requirements.txt` pins
fastapi 0.136.1, uvicorn 0.46.0, pydantic 2.13.3, ruff 0.15.12 and Bandit
1.9.4. `start_services.sh` starts the four services on 127.0.0.1:8101-8104.

No model, no GPU. Between requests only the four Python processes stay
alive; every lint and scan request starts a new ruff or Bandit process. There
are no caches.

Reference runs: services on a node with an AMD EPYC 7763 CPU (RHEL 9.6,
Python 3.10.22); client on an Apple Mac (Python 3.10.18, requests 2.32.5)
over an SSH tunnel with a ping round trip of about 30 ms. The original author
developed the pipeline on an Intel Core i9-13900F desktop (Ubuntu 22.04).

## Measurement

The timed window covers the five calls. Reading the source file and encoding
the outputs are outside it.

Outputs, all deterministic for a given input and tool versions:

| Output | Content |
|---|---|
| `review_json` | `{action, review_text}` from `/summarize`, JSON with sorted keys (token counts left out) |
| `action` | `approve` or `request_changes` |
| `lint_summary` | the lint counts and first three diagnostics sent to `/summarize` |
| `sec_summary` | the highest severity and all security issues sent to `/summarize` |

`extra` holds `action`, `lint_counts`, `severity_max` and `n_security_issues`.

Equivalence rule: identical sha256 of `review_json` for every input
(`python -m wbench.compare reference.jsonl candidate.jsonl --outputs review_json`).
The other three outputs are expected to be identical as well. With the
pinned tool versions, the released services reproduce the output hashes and
the response sizes of the reference runs on all 70 inputs.

## Running

```bash
# services (Python 3.10)
python3.10 -m venv .venv-cr && .venv-cr/bin/pip install -r servers/code_review/requirements.txt
PYTHON=.venv-cr/bin/python bash servers/code_review/start_services.sh &

# client
python3.10 -m venv .venv && .venv/bin/pip install -r workloads/code_review/requirements.txt
.venv/bin/python workloads/code_review/prepare_data.py
.venv/bin/python workloads/code_review/run.py --split test --warmup 1 --rounds 3 \
    --out runs/code_review/test.jsonl
.venv/bin/python -m wbench.summarize runs/code_review/test.jsonl
```

Service URLs: `--parser-url`, `--linter-url`, `--scanner-url`,
`--summarizer-url` (defaults `http://127.0.0.1:8101` to `:8104`).

## Known limitations

- The test splits have no file above 220 LOC, while profiling spans 50-300
  (see SELECTION.md).
- In the reference runs the trace id carried run metadata and was 40-64
  characters longer, so each request body was that many bytes larger; the
  reference services also built and discarded a trace record per request.
  Neither is part of this release.
- Lint and security findings depend on the exact ruff and Bandit versions,
  and parse payloads on the Python version of the parser service.
- The review is a fixed template, not a language model.
