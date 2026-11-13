# code_review services

The four HTTP services of the CodeReview workload (`workloads/code_review/`).
Adapted from a practice project by an outside developer. Source and every
change from the original are listed in `workloads/code_review/README.md`.

| File | Service | Port |
|---|---|---|
| `parser_server.py` | `POST /parse`: `ast.parse` + `ast.dump` | 8101 |
| `linter_server.py` | `POST /lint`: one `ruff check` process per request | 8102 |
| `scanner_server.py` | `POST /scan`: one `bandit` process per request | 8103 |
| `summarizer_server.py` | `POST /summarize`: deterministic review template | 8104 |
| `_shared.py` | request base model, tool lookup, subprocess helper | |

```bash
python3.10 -m venv .venv-cr && .venv-cr/bin/pip install -r servers/code_review/requirements.txt
PYTHON=.venv-cr/bin/python bash servers/code_review/start_services.sh   # Ctrl+C stops all four
```

Each service also takes `--host` and `--port`.
