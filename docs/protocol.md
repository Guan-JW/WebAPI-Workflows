# Measurement protocol

The same protocol applies to every workload. A workload card can tighten it,
for example by fixing a session structure, but never loosens it.

## Splits

Each workload has a `profiling` split and a `test` split, and some add
`test2` or `validation`. A tool that adapts to the workload (a profiler-driven
optimizer, a cache warmer, a tuned scheduler) may observe profiling inputs
only. Report results on `test`. No input appears in two splits of the same
workload.

## Latency

- One untimed warm-up round (`--warmup 1`), then three timed rounds
  (`--rounds 3`). The order of units is reshuffled every round with a fixed
  seed (`--seed`, default 0). Units that form a session keep their order.
- A unit's latency is the wall time of the workflow's request path: from the
  start of its first step to the moment its final output is available on the
  client. Each card says where the timed window starts and ends.
- Report p50 latency over all timed units of the split, with a 95% bootstrap
  confidence interval that resamples inputs (or sessions, for session
  workloads), not individual rounds. Also report p95, median HTTP calls, and
  request and response bytes.
- Run the configurations under comparison interleaved on the same deployment
  (for example, alternating per input), not one after another on different
  days.

## Client concurrency

- Closed loop: C independent client processes, with no shared client state and
  no think time. Suggested levels: C = 1, 2, 4, 8 (`python -m wbench.closed_loop`).
- Each client takes its own shard of the test split. It runs one untimed
  warm-up unit, waits for the common start time, then issues
  k = max(4, ceil(16 / C)) units back to back.
- Throughput is the number of successful units divided by the time from the
  first start to the last end of the timed window. Also report p50 and p95
  latency and counts of errors, HTTP 429 or 5xx responses, and retries.
- Stateful workloads isolate each client: own sessions, file names, output
  paths and local databases. The harness gives every client a private
  `--workdir`.
- For self-hosted services, state how many server replicas served the load.
  For hosted APIs, report the provider and model and do not claim a replica
  count.

## State and caches

- Model weights are loaded once and stay loaded, unless a server's
  configuration specifies otherwise.
- Client-side state is reset before every unit, except state that belongs to
  the session the unit is part of.
- If a tool adds a cache, report its scope (per request, per session, per
  client, global) and its hit rate on the test split. A cache may be shared
  across sessions only for data that is not private to a session.

## Correctness

Each card defines the equivalence rule between a reference run and a
candidate run:

- byte-identical outputs (`python -m wbench.compare`);
- a tolerance-based check for stochastic stages (the card ships a `check.py`);
- for hosted LLM applications, a rule that accounts for nondeterministic
  generations.

Report how many test inputs pass the rule. A failed or non-equivalent unit
counts as such; it is never dropped silently.

## Environment record

Record with every result: the commit of this repository; upstream commits and
versions (`source.json`); model versions; client and server hardware; the
network path between client and services (round-trip time and bandwidth; see
`python -m wbench.probe`); and the provider region for hosted APIs. Results
from different network paths are not comparable.
