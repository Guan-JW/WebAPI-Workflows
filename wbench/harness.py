"""Common runner for all workloads.

A workload's ``run.py`` defines a :class:`Workload` and calls :func:`main`.
The runner loads the split's manifest, runs every unit (one request, or one
user interaction) for warm-up plus timed rounds, records HTTP calls with
:class:`~wbench.http_recorder.HttpRecorder`, hashes the outputs, and writes
one JSON line per unit and round (schema: ``docs/results.md``).

Two modes:

* **rounds** (default): ``--warmup`` untimed rounds, then ``--rounds`` timed
  rounds; the unit order is reshuffled every round with ``--seed + round``.
* **closed loop** (``--requests K``): used by ``python -m wbench.closed_loop``
  for client concurrency. One untimed warm-up unit, a wait until
  ``--start-at``, then K units back to back, cycling through this client's
  shard.

Units that share ``Workload.group_key`` (for example, the questions of one
document session) always run together, in manifest order; only the order of
groups is shuffled, and groups are what ``--shard`` deals out.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import platform
import random
import socket
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from . import SUITE_VERSION, manifest
from .http_recorder import HttpRecorder, now_ms


@dataclass
class UnitResult:
    """What ``run_one`` may return instead of a plain ``{name: bytes}`` dict."""

    outputs: Dict[str, bytes]
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Workload:
    id: str
    run_one: Callable[[Dict[str, Any], "Context"], Union[Dict[str, bytes], UnitResult]]
    add_args: Optional[Callable[[argparse.ArgumentParser], None]] = None
    units: Optional[Callable[[argparse.Namespace], List[Dict[str, Any]]]] = None
    setup: Optional[Callable[["Context"], None]] = None
    reset: Optional[Callable[[Dict[str, Any], "Context"], None]] = None
    teardown: Optional[Callable[["Context"], None]] = None
    group_key: Optional[Callable[[Dict[str, Any]], str]] = None
    keep_bodies: bool = False


class Context:
    """Per-process state handed to the workload's callbacks."""

    def __init__(self, workload: Workload, args: argparse.Namespace, recorder: HttpRecorder) -> None:
        self.workload = workload
        self.args = args
        self.recorder = recorder
        self.data_dir = manifest.data_dir(workload.id)
        self.workdir = os.path.abspath(args.workdir or os.path.join("runs", workload.id, f"work_c{args.client_id}"))
        os.makedirs(self.workdir, exist_ok=True)
        self.round = 0
        self.state: Dict[str, Any] = {}  # free for the workload (sessions, clients, ...)
        self._window: Optional[List[float]] = None

    @contextlib.contextmanager
    def timed(self) -> Iterator[None]:
        """Mark the timed part of ``run_one``.

        If ``run_one`` never enters this block, the whole call is timed. If it
        does, latency and HTTP counts cover only the block (for example, to
        leave per-session setup out of a per-question measurement).
        """
        t0 = now_ms()
        try:
            yield
        finally:
            self._window = [t0, now_ms()]


def add_common_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("runner")
    g.add_argument("--split", default="test", help="manifest split (default: test)")
    g.add_argument("--rounds", type=int, default=3, help="timed rounds (default: 3)")
    g.add_argument("--warmup", type=int, default=1, help="untimed warm-up rounds (default: 1)")
    g.add_argument("--limit", type=int, default=None, help="use only the first N groups of the split")
    g.add_argument("--seed", type=int, default=0, help="seed for the unit order (default: 0)")
    g.add_argument("--out", default=None, help="results JSONL (default: runs/<workload>/<split>_<utc>.jsonl)")
    g.add_argument("--label", default="baseline", help="free-form label stored in every row (default: baseline)")
    g.add_argument("--save-outputs", default=None, help="also write raw outputs under this directory")
    g.add_argument("--workdir", default=None, help="scratch directory for this client (default: runs/<workload>/work_c<id>)")
    g.add_argument("--shard", default="0/1", help="i/n: run only groups i, i+n, i+2n, ... (default: 0/1)")
    g.add_argument("--client-id", type=int, default=0)
    g.add_argument("--requests", type=int, default=None, help="closed-loop mode: timed units for this client")
    g.add_argument("--start-at", type=float, default=None, help="closed-loop mode: epoch seconds to start the timed window")


def _groups(workload: Workload, units: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if workload.group_key is None:
        return [[u] for u in units]
    order: List[str] = []
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for u in units:
        k = workload.group_key(u)
        if k not in by_key:
            by_key[k] = []
            order.append(k)
        by_key[k].append(u)
    return [by_key[k] for k in order]


def _utc(ms: float) -> str:
    return _dt.datetime.fromtimestamp(ms / 1000.0, tz=_dt.timezone.utc).isoformat(timespec="milliseconds")


class _Writer:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.f = open(path, "a", encoding="utf-8")

    def write(self, row: Dict[str, Any]) -> None:
        self.f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


def _run_unit(workload: Workload, ctx: Context, unit: Dict[str, Any], group_id: str, round_idx: int,
              warmup: bool, writer: _Writer) -> Dict[str, Any]:
    args = ctx.args
    ctx.round = round_idx
    if workload.reset is not None:
        workload.reset(unit, ctx)
    ctx._window = None
    status, err, outputs, extra = "ok", None, {}, {}
    t0 = now_ms()
    try:
        res = workload.run_one(unit, ctx)
        if isinstance(res, UnitResult):
            outputs, extra = res.outputs, res.extra
        else:
            outputs = res or {}
    except Exception as e:  # noqa: BLE001
        status, err = "error", f"{type(e).__name__}: {e}"
        extra = {"traceback": traceback.format_exc(limit=6)}
    t1 = now_ms()
    if ctx._window is not None:
        t0, t1 = ctx._window
    calls = ctx.recorder.window(t0, t1)
    ctx.recorder.clear()
    row = {
        "suite_version": SUITE_VERSION,
        "workload": workload.id,
        "split": args.split,
        "label": args.label,
        "input_id": unit.get("input_id"),
        "input_sha256": unit.get("sha256"),
        "group_id": group_id,
        "round": round_idx,
        "warmup": warmup,
        "client_id": args.client_id,
        "status": status,
        "error": err,
        "t_start_ms": round(t0, 3),
        "t_end_ms": round(t1, 3),
        "t_start_utc": _utc(t0),
        "latency_ms": round(t1 - t0, 3),
        "http_calls": len(calls),
        "bytes_out": sum(c.req_bytes for c in calls),
        "bytes_in": sum(c.resp_bytes for c in calls),
        "http_span_ms": round(max(c.t_end_ms for c in calls) - min(c.t_start_ms for c in calls), 3) if calls else None,
        "calls": [c.to_record() for c in calls],
        "outputs": {k: manifest.sha256_bytes(v) for k, v in outputs.items() if v is not None},
        "output_bytes": {k: len(v) for k, v in outputs.items() if v is not None},
        "extra": extra,
    }
    writer.write(row)
    if args.save_outputs and outputs:
        d = os.path.join(args.save_outputs, str(unit.get("input_id")), f"r{round_idx}_c{args.client_id}")
        os.makedirs(d, exist_ok=True)
        for k, v in outputs.items():
            if v is not None:
                with open(os.path.join(d, k), "wb") as f:
                    f.write(v)
    tag = "warmup" if warmup else f"r{round_idx}"
    print(f"[{workload.id}] {tag} {unit.get('input_id')}: {status} {row['latency_ms']:.0f} ms, "
          f"{row['http_calls']} calls" + (f"  ({err})" if err else ""), file=sys.stderr, flush=True)
    return row


def main(workload: Workload, argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(prog=f"{workload.id}/run.py", description=f"Run the {workload.id} workload.")
    add_common_args(p)
    if workload.add_args is not None:
        workload.add_args(p.add_argument_group(workload.id))
    args = p.parse_args(argv)

    units = workload.units(args) if workload.units is not None else manifest.load(workload.id, args.split)
    groups = _groups(workload, units)
    if args.limit is not None:
        groups = groups[: args.limit]
    i, n = (int(x) for x in args.shard.split("/"))
    groups = groups[i::n]
    if not groups:
        raise SystemExit("no units to run (check --split / --limit / --shard)")

    out = args.out or os.path.join("runs", workload.id,
                                   f"{args.split}_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}_c{args.client_id}.jsonl")
    writer = _Writer(out)
    recorder = HttpRecorder(keep_bodies=workload.keep_bodies)
    ctx = Context(workload, args, recorder)
    meta = {"suite_version": SUITE_VERSION, "workload": workload.id, "argv": sys.argv, "host": socket.gethostname(),
            "python": platform.python_version(), "platform": platform.platform(), "started_utc": _utc(now_ms())}
    with open(out + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, sort_keys=True)

    def gid(g: List[Dict[str, Any]]) -> str:
        return workload.group_key(g[0]) if workload.group_key else str(g[0].get("input_id"))

    recorder.install()
    try:
        if workload.setup is not None:
            workload.setup(ctx)
        recorder.clear()
        if args.requests is None:
            for r in range(args.warmup + args.rounds):
                order = list(groups)
                random.Random(args.seed + r).shuffle(order)
                for g in order:
                    for u in g:
                        _run_unit(workload, ctx, u, gid(g), r, r < args.warmup, writer)
        else:
            order = list(groups)
            random.Random(args.seed * 1000 + args.client_id).shuffle(order)
            flat = [(gid(g), u) for g in order for u in g]
            _run_unit(workload, ctx, flat[0][1], flat[0][0], 0, True, writer)
            if args.start_at is not None:
                time.sleep(max(0.0, args.start_at - time.time()))
            for k in range(args.requests):
                g_id, u = flat[k % len(flat)]
                _run_unit(workload, ctx, u, g_id, 1, False, writer)
    finally:
        if workload.teardown is not None:
            with contextlib.suppress(Exception):
                workload.teardown(ctx)
        recorder.uninstall()
        writer.close()
    print(f"[{workload.id}] wrote {out}", file=sys.stderr)
