# Result rows

Every workload writes JSON Lines, one row per unit and round, plus a
`<file>.meta.json` with the command line, host and Python version.

| Field | Meaning |
|---|---|
| `suite_version` | version of this repository's harness |
| `workload`, `split`, `label` | which workload and split; `label` is free text (default `baseline`) |
| `input_id`, `input_sha256` | the manifest row |
| `group_id` | session or group the unit belongs to (equals `input_id` when units are independent) |
| `round`, `warmup` | round index; warm-up rows are excluded from summaries |
| `client_id` | client process (closed-loop runs) |
| `status`, `error` | `ok` or `error` with the exception |
| `t_start_ms`, `t_end_ms`, `t_start_utc` | the timed window, epoch milliseconds |
| `latency_ms` | `t_end_ms - t_start_ms` |
| `http_calls` | HTTP requests started inside the timed window |
| `bytes_out`, `bytes_in` | request and response body bytes of those calls (headers excluded). Calls are recorded for `requests`, `httpx` and `httpx2`; a streamed response body (for example a streamed LLM answer) is counted as 0 bytes |
| `http_span_ms` | first request start to last response end |
| `calls` | per call: method, host, path, status, latency, request and response bytes |
| `outputs`, `output_bytes` | sha256 and size of each named output |
| `extra` | workload-specific fields documented in the workload card |

`python -m wbench.summarize <files>` reports p50, p95 and mean latency, median
calls and bytes, and, for closed-loop runs, completed throughput.
`python -m wbench.compare <reference> <candidate>` checks outputs input by input.
