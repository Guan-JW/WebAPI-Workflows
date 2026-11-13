"""AudioTour: one "Generate Tour" click of the pinned AI Audio Tour Agent, driven headlessly.

The unit is the click's script path in ai_audio_tour_agent.py, without the st.* display calls:
L48 set_default_openai_key(<the key typed in the sidebar>), L102-L105 TourManager().run(location,
interests, duration) via the app's run_async, L114 tts(final_tour), which writes speech_tour.mp3 next
to the app module, and L122 reading that file. The whole click is timed.

    python run.py --split test                    # needs OPENAI_API_KEY
    python run.py --split test --dry-run          # resolve inputs, import the app, print the plan

Outputs per unit: `tour` (text shown), `audio` (MP3 served), and the request bodies of the three
calls whose bytes depend only on the input: `req_planner`, `req_architecture`, `req_history`.
extra.dataflow holds the per-request checks of check.py.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from wbench import manifest  # noqa: E402
from wbench.harness import UnitResult, Workload, add_common_args, main  # noqa: E402

import tour_checks  # noqa: E402

ID = "audio_tour"
APP_PATH = "voice_ai_agents/ai_audio_tour_agent"
APP_FILES = {  # sha256 at the pinned commit (fetch_upstream.sh checks the same values)
    "ai_audio_tour_agent.py": "12cb4026c537a324122b4761ed637460fd31fe16c2511890053ea9f6366ca3d5",
    "manager.py": "75a43dbb23a0fba507100db15ae0e58c51a1625a39b744b86d7f9a14cba1617c",
    "agent.py": "31aa8fba009757713e0bfb8eab0edce75fdb8b7659a60059cf76f0ef3765ca68",
    "printer.py": "e58f32a96db2903e1347e007cd08a8b597f8b811d95968bd87eeb9809d9826f4",
}
CALLS = ["POST /v1/responses (planner, gpt-4o, structured output)",
         "POST /v1/responses (architecture, gpt-4o-mini + web_search_preview, tool_choice=required)",
         "POST /v1/responses (history, gpt-4o-mini + web_search_preview, tool_choice=required)",
         "POST /v1/responses (orchestrator, gpt-4o-mini, structured output)",
         "POST /v1/audio/speech (gpt-4o-mini-tts, voice nova, MP3)"]


def add_args(p):
    p.add_argument("--upstream-dir", default=None, help="where fetch_upstream.sh put the app (default: ./upstream)")
    p.add_argument("--dry-run", action="store_true", help="resolve inputs, import the app, print the plan")


def set_environment():
    """README "Adaptations". Must run before `agents` is imported."""
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"       # SDK telemetry upload off (not a workflow call)
    os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")  # silence Streamlit's bare-mode warnings


def app_copy(args, dst):
    """Byte-identical copy of the four app files into dst (this client's own speech_tour.mp3 path)."""
    src = os.path.join(args.upstream_dir or os.path.join(HERE, "upstream"), APP_PATH)
    os.makedirs(dst, exist_ok=True)
    for f, h in APP_FILES.items():
        if not os.path.exists(os.path.join(src, f)) or manifest.sha256_file(os.path.join(src, f)) != h:
            raise SystemExit(f"{os.path.join(src, f)} missing or not the pinned file; run fetch_upstream.sh")
        shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
        assert manifest.sha256_file(os.path.join(dst, f)) == h
    return dst


def import_app(appdir):
    set_environment()
    sys.path.insert(0, appdir)
    import ai_audio_tour_agent as ui  # noqa: E402  Streamlit bare mode: widget calls return defaults, no work starts

    for m in ("ai_audio_tour_agent", "manager", "agent", "printer"):
        got = os.path.dirname(os.path.abspath(sys.modules[m].__file__))
        if got != os.path.abspath(appdir):
            raise SystemExit(f"module {m} imported from {got}, expected {appdir}")
    return ui


def setup(ctx):
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")   # tts() builds OpenAI(), which reads it
    ui = import_app(app_copy(ctx.args, os.path.join(ctx.workdir, "app")))
    ctx.state.update(ui=ui, key=os.environ["OPENAI_API_KEY"])


def run_one(unit, ctx):
    ui = ctx.state["ui"]
    with ctx.timed():
        ui.set_default_openai_key(ctx.state["key"])                                # L48
        mgr = ui.TourManager()                                                     # L102
        final_tour = ui.run_async(mgr.run, unit["location"], list(unit["interests"]),
                                  unit["duration"])                                # L103-L105
        tour_audio = ui.tts(final_tour)                                            # L114
        with open(tour_audio, "rb") as file:                                       # L122
            audio = file.read()
    # Checks below are not timed.
    if not isinstance(final_tour, str) or not final_tour.strip():
        raise RuntimeError("empty tour text")
    secs = tour_checks.mp3_seconds(audio)
    if secs <= 0:
        raise RuntimeError("no MP3 frames in the audio file")
    calls = tour_checks.classify(ctx.recorder.calls)
    outputs = {"tour": final_tour.encode("utf-8"), "audio": audio}
    for name in ("planner", "architecture", "history"):
        if calls.get(name) is not None:
            outputs[f"req_{name}"] = calls[name].req_body
    extra = {"tour_chars": len(final_tour), "tour_words": len(final_tour.split()), "audio_seconds": round(secs, 2),
             "dataflow": tour_checks.dataflow(calls, unit["interests"], final_tour, audio),
             "sdk_retries": sum(1 for c in ctx.recorder.calls if c.status is None)}
    return UnitResult(outputs, extra)


WORKLOAD = Workload(id=ID, run_one=run_one, add_args=add_args, setup=setup, keep_bodies=True)


def dry_run(argv):
    p = argparse.ArgumentParser(prog=f"{ID}/run.py")
    add_common_args(p)
    add_args(p.add_argument_group(ID))
    args = p.parse_args(argv)
    units = manifest.load(ID, args.split)
    bad = [u["input_id"] for u in units if hashlib.sha256(json.dumps(
        {k: u[k] for k in ("location", "interests", "duration")}, sort_keys=True).encode()).hexdigest() != u["sha256"]]
    groups = [[u] for u in units][: args.limit] if args.limit else [[u] for u in units]
    i, n = (int(x) for x in args.shard.split("/"))
    groups = groups[i::n]
    print(f"workload {ID}, split {args.split}: {len(units)} units ({len(bad)} hash mismatches), "
          f"{len(groups)} after --limit/--shard")
    workdir = os.path.abspath(args.workdir or os.path.join("runs", ID, "dryrun"))
    ui = import_app(app_copy(args, os.path.join(workdir, "app")))
    print(f"app imported from {os.path.dirname(ui.__file__)}; TourManager={ui.TourManager.__module__}; "
          f"tracing disabled={os.environ.get('OPENAI_AGENTS_DISABLE_TRACING')}")
    print(f"calls per unit ({len(CALLS)}): " + "; ".join(CALLS))
    for g in groups:
        u = g[0]
        print(f"  {u['input_id']:9s} {u['location'][:60]!r} interests={u['interests']} duration={u['duration']}")


if __name__ == "__main__":
    if "--dry-run" in sys.argv[1:]:
        dry_run(sys.argv[1:])
    else:
        main(WORKLOAD)
