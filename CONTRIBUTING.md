# Adding or changing a workload

## Layout

```text
workloads/<id>/
  README.md          workload card (template below)
  run.py             defines WORKLOAD and calls wbench.harness.main
  prepare_data.py    downloads the inputs listed in manifests/<id>/ into data/<id>/ and checks sha256
  source.json        machine-readable source: upstream code, datasets, models, licenses
  requirements.txt   client-side dependencies, pinned
  check.py           only if exact output hashes are not the right equivalence rule
  ...                client modules the workflow needs
manifests/<id>/<split>.jsonl
servers/<name>/      self-hosted services: setup script, pinned upstream refs, patches, service code
```

Rules:

- **Baseline only.** A workload is the application as it runs. Optimized
  variants belong in the repositories of the tools that produce them.
- **Pinned.** Upstream code is fetched at a fixed commit, not copied in. Models
  are named with their download URL and sha256 where one exists.
- **Inputs are listed, not copied.** A manifest row gives `input_id`, the
  source URL or dataset revision, `sha256`, and the license. `prepare_data.py`
  fetches the files. Splits: `profiling` (inputs a tool may observe before
  deployment) and `test` (held out); some workloads add `test2` or
  `validation`. No input appears in two splits of the same workload.
- **Adaptations are written down.** Every difference from the upstream
  application (a replaced model, a stand-in service, a headless driver, an
  environment variable) goes in the card's Source section with the reason.
- **Runs without a GPU are not a goal.** Each card states the hardware the
  workload was developed on.

## run.py

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wbench.harness import Workload, UnitResult, main

def add_args(p):            # workload-specific flags (service URLs, parameters)
    p.add_argument("--service-url", default="http://127.0.0.1:7860")

def run_one(unit, ctx):     # one manifest row -> {output name: bytes}
    ...
    return {"final_image": png_bytes}

WORKLOAD = Workload(id="<id>", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
```

Optional hooks: `setup(ctx)` once per client process (untimed), `reset(unit,
ctx)` before each unit (untimed), `teardown(ctx)`, `group_key(unit)` for units
that must run together in order (a session), `units(args)` to build units
from something other than the manifest. Inside `run_one`, a `with
ctx.timed():` block narrows the timed window; without it the whole call is
timed. `ctx.workdir` is private to the client process; write every file there.
`ctx.data_dir` is `data/<id>/`.

## Workload card template

```markdown
# <Name>

<One paragraph: what a user of this application is doing, and what one unit of work is.>

| | |
|---|---|
| Domain | ... |
| Source | source repository at a pinned commit, or the application area and the components the workflow is built on |
| Services | ... (self-hosted or hosted) |
| Calls per unit | ... |
| Inputs | <dataset>, <n> profiling / <n> test |
| Unit | one request / one session / one question |

## Source
Where the workflow comes from: the source repository at a pinned commit, or
the application area it is derived from and the components it is built on.
Every adaptation, with the reason.

## Workflow
The call sequence of one unit: endpoint, what is sent, what comes back, which
later step consumes it.

## Inputs
Dataset and revision, selection rule, seed, split sizes, licenses.

## Deployment
Services and how to start them, models and versions, what stays loaded
between requests, any caches and their scope, hardware used in development.

## Measurement
What one timed unit covers, what the outputs are, and the equivalence rule
for comparing two runs.

## Running
Commands, from set-up to a result file.

## Known limitations
```
