"""ChatWithPDF: questions about one PDF in the pinned Streamlit app, driven headlessly with AppTest.

Streamlit reruns the whole script (chat_pdf.py L15-36) on every interaction. A document session is
the sequence of script runs one user triggers on a fresh page: load the page, type the OpenAI key
(L17-21), upload the PDF (L23-30), then type each question and press Enter (L32-36), one script run
per question, in dataset order. The unit is one question's script run (the AppTest.run() call);
load, key and upload are session set-up and are not timed. Units of one document form one group
(wbench group_key), so a session's questions always run together and in order.

    python run.py --split test                     # needs OPENAI_API_KEY and the PDFs (prepare_data.py)
    python run.py --split test --dry-run           # resolve inputs, load the page once, print the plan

Outputs per unit: `answer` (the answer shown on the page) and `chat_request` (the `messages` of the
chat-completions request, canonical JSON). extra: session, q_index, history_sha256; see check.py.
"""
import argparse
import collections
import gc
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from wbench import manifest  # noqa: E402
from wbench.harness import UnitResult, Workload, add_common_args, main  # noqa: E402

ID = "chat_with_pdf"
APP_PATH = "advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf/chat_pdf.py"
APP_SHA256 = "3f1d44bf1913dcc5620c37d64c556bfedbc02e7861e5757bdfd4cca6f2c61f84"
KEY_LABEL = "OpenAI API Key"                       # chat_pdf.py L17
UPLOAD_LABEL = "Upload a PDF file"                 # L23
QUESTION_LABEL = "Ask a question about the PDF"    # L32
CALLS = ["POST /v1/embeddings (every chunk of the PDF, re-added by this rerun)",
         "POST /v1/embeddings (the question)", "POST /v1/chat/completions (gpt-4o-mini)"]


def sha256(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def add_args(p):
    p.add_argument("--upstream-dir", default=None, help="where fetch_upstream.sh put the app (default: ./upstream)")
    p.add_argument("--dry-run", action="store_true", help="resolve inputs, load the page once, print the plan")


def app_script(args):
    return os.path.join(args.upstream_dir or os.path.join(HERE, "upstream"), APP_PATH)


def set_environment(workdir):
    """README "Adaptations": telemetry opt-out and per-client locations for the app's own files.
    Must run before embedchain is imported (it reads EMBEDCHAIN_CONFIG_DIR at import)."""
    for d in ("tmp", "ec_home", "ec_db"):
        os.makedirs(os.path.join(workdir, d), exist_ok=True)
    os.environ["EC_TELEMETRY"] = "False"
    os.environ["EMBEDCHAIN_CONFIG_DIR"] = os.path.join(workdir, "ec_home")
    os.environ["EMBEDCHAIN_DB_URI"] = f"sqlite:///{os.path.join(workdir, 'ec_home', 'unused.db')}"
    os.environ["TMPDIR"] = os.path.join(workdir, "tmp")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    tempfile.tempdir = None
    assert tempfile.gettempdir() == os.path.join(workdir, "tmp"), tempfile.gettempdir()


def _widget(widgets, label):
    for w in widgets:
        if w.label == label:
            return w
    raise LookupError(f"widget {label!r} not rendered")


class Session:
    """One user on a fresh page: its own AppTest (st.session_state) and embedchain metadata DB."""

    def __init__(self, ctx, arxiv_id, pdf):
        from streamlit.testing.v1 import AppTest

        ctx.state["seq"] += 1
        self.seq, self.arxiv_id, self.pdf = ctx.state["seq"], arxiv_id, pdf
        self.workdir = ctx.workdir
        self.db = os.path.join(ctx.workdir, "ec_db", f"s{self.seq}.db")
        if os.path.exists(self.db):
            os.remove(self.db)
        self.created = []          # entries this session's script runs left in TMPDIR
        self.answers = []          # answers shown so far: the app's chat history in this session
        self.next_q = 0
        self.at = AppTest.from_file(ctx.state["script"], default_timeout=900)

    def script_run(self, action):
        """One script run, with this session's metadata DB selected first (embedchain reads
        EMBEDCHAIN_DB_URI whenever the script builds its App)."""
        os.environ["EMBEDCHAIN_DB_URI"] = f"sqlite:///{self.db}"
        tmp = os.path.join(self.workdir, "tmp")
        before = set(os.listdir(tmp))
        try:
            action()
        finally:
            self.created += sorted(set(os.listdir(tmp)) - before)
        if self.at.exception:
            raise RuntimeError(f"app exception: {self.at.exception[0].message}"[:300])

    def open(self, key):
        """Load, key, upload: untimed session set-up (0, 0 and 1 HTTP calls)."""
        self.script_run(lambda: self.at.run())
        self.script_run(lambda: _widget(self.at.text_input, KEY_LABEL).input(key).run())
        self.script_run(lambda: _widget(self.at.file_uploader, UPLOAD_LABEL).set_value(
            (f"{self.arxiv_id}.pdf", self.pdf, "application/pdf")).run())
        return self

    def close(self):
        """Release what the session left behind (never inside a timed window)."""
        try:
            from chromadb.api.shared_system_client import SharedSystemClient

            SharedSystemClient.clear_system_cache()   # the app opens a new client per rerun, never closes it
        except Exception:  # noqa: BLE001
            pass
        self.at = None
        gc.collect()
        tmp = os.path.join(self.workdir, "tmp")
        for name in self.created:
            p = os.path.join(tmp, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else (os.path.exists(p) and os.remove(p))
        if os.path.exists(self.db):
            os.remove(self.db)


def _pdf(ctx, unit):
    path = os.path.join(ctx.data_dir, unit["file"])
    with open(path, "rb") as f:
        b = f.read()
    if sha256(b) != unit["sha256"]:
        raise RuntimeError(f"{path}: sha256 differs from the manifest (run prepare_data.py)")
    return b


def closed_loop_plan(args, units):
    """The units this client runs in closed-loop mode, in the harness's order (wbench.harness.main):
    groups in manifest order, --limit, --shard, shuffled with seed * 1000 + client id; one warm-up
    unit, then --requests units cycling through the list."""
    by = collections.OrderedDict()
    for u in units:
        by.setdefault(u["arxiv_id"], []).append(u)
    groups = list(by.values())
    if args.limit is not None:
        groups = groups[: args.limit]
    i, n = (int(x) for x in args.shard.split("/"))
    order = groups[i::n]
    random.Random(args.seed * 1000 + args.client_id).shuffle(order)
    flat = [u for g in order for u in g]
    return [flat[0]] + [flat[k % len(flat)] for k in range(args.requests)] if flat else []


def setup(ctx):
    args = ctx.args
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    script = app_script(args)
    if not os.path.exists(script) or manifest.sha256_file(script) != APP_SHA256:
        raise SystemExit(f"{script} missing or not the pinned file; run fetch_upstream.sh")
    set_environment(ctx.workdir)
    units = manifest.load(ID, args.split)
    ctx.state.update(script=script, key=os.environ["OPENAI_API_KEY"], seq=0, session=None,
                     last_q={}, preopened=collections.deque())
    for u in units:
        ctx.state["last_q"][u["arxiv_id"]] = max(ctx.state["last_q"].get(u["arxiv_id"], -1), u["q_index"])
    if args.requests is not None:
        # Closed loop: open every session this client will need before the timed window, so that
        # the window holds question runs only (the uploads embed whole PDFs).
        for u in closed_loop_plan(args, units):
            if u["q_index"] == 0:
                ctx.state["preopened"].append(Session(ctx, u["arxiv_id"], _pdf(ctx, u)).open(ctx.state["key"]))


def _session_for(unit, ctx):
    s = ctx.state["session"]
    if unit["q_index"] == 0:
        if s is not None:
            s.close()
        pre = ctx.state["preopened"]
        if pre and pre[0].arxiv_id == unit["arxiv_id"]:
            s = pre.popleft()
        else:
            s = Session(ctx, unit["arxiv_id"], _pdf(ctx, unit)).open(ctx.state["key"])
        ctx.state["session"] = s
    elif s is None or s.arxiv_id != unit["arxiv_id"] or s.next_q != unit["q_index"]:
        raise RuntimeError(f"question {unit['q_index']} of {unit['arxiv_id']} has no open session at that position")
    return s


def _chat_request(ctx):
    chats = [c for c in ctx.recorder.calls if c.path().endswith("/chat/completions") and c.req_body]
    if not chats:
        return None
    messages = json.loads(chats[-1].req_body.decode("utf-8"))["messages"]
    return json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")


def run_one(unit, ctx):
    s = _session_for(unit, ctx)
    history = sha256(json.dumps(s.answers, ensure_ascii=False))
    s.next_q = unit["q_index"] + 1
    n_tmp = len(s.created)
    try:
        with ctx.timed():
            s.script_run(lambda: _widget(s.at.text_input, QUESTION_LABEL).input(unit["question"]).run())
        md = [el.value for el in s.at.markdown]
        answer = md[-1] if md else None
        s.answers.append(answer)
        chat = _chat_request(ctx)
        extra = {"session": f"c{ctx.args.client_id}-s{s.seq}", "session_seq": s.seq, "arxiv_id": unit["arxiv_id"],
                 "q_index": unit["q_index"], "history_sha256": history,
                 "tmp_entries_created": len(s.created) - n_tmp}
        return UnitResult({"answer": answer.encode("utf-8") if answer is not None else None,
                           "chat_request": chat}, extra)
    finally:
        if unit["q_index"] >= ctx.state["last_q"].get(unit["arxiv_id"], unit["q_index"]):
            s.close()
            ctx.state["session"] = None


def teardown(ctx):
    for s in [ctx.state.get("session"), *ctx.state.get("preopened", [])]:
        if s is not None:
            s.close()


WORKLOAD = Workload(id=ID, run_one=run_one, add_args=add_args, setup=setup, teardown=teardown,
                    group_key=lambda u: u["arxiv_id"], keep_bodies=True)


def dry_run(argv):
    """Resolve split, groups, PDFs and the upstream script; run the page-load script run once
    (no key typed, no HTTP call); print the plan."""
    p = argparse.ArgumentParser(prog=f"{ID}/run.py")
    add_common_args(p)
    add_args(p.add_argument_group(ID))
    args = p.parse_args(argv)
    units = manifest.load(ID, args.split)
    by = collections.OrderedDict()
    for u in units:
        by.setdefault(u["arxiv_id"], []).append(u)
    groups = list(by.values())[: args.limit] if args.limit else list(by.values())
    i, n = (int(x) for x in args.shard.split("/"))
    groups = groups[i::n]
    print(f"workload {ID}, split {args.split}: {len(units)} questions in {len(by)} document sessions; "
          f"{len(groups)} sessions after --limit/--shard")
    script = app_script(args)
    ok = os.path.exists(script) and manifest.sha256_file(script) == APP_SHA256
    print(f"upstream script: {script} ({'ok' if ok else 'MISSING or hash differs'})")
    workdir = os.path.abspath(args.workdir or os.path.join("runs", ID, "dryrun"))
    if ok:
        set_environment(workdir)
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(script, default_timeout=120)
        at.run()
        print(f"page load: title={[t.value for t in at.title]} inputs={[w.label for w in at.text_input]} "
              f"exceptions={len(at.exception)}")
    print(f"set-up per session: load (0 calls), key (0 calls), upload (1 x POST /v1/embeddings); "
          f"per question ({len(CALLS)} calls): " + "; ".join(CALLS))
    for g in groups:
        path = os.path.join(manifest.data_dir(ID), g[0]["file"])
        present = os.path.exists(path) and manifest.sha256_file(path) == g[0]["sha256"]
        print(f"  session {g[0]['arxiv_id']}  {g[0]['file']} ({'ok' if present else 'missing: prepare_data.py'})")
        for u in g:
            print(f"    q{u['q_index']} {u['input_id']}  {u['question'][:70]!r}")
    if args.requests is not None:
        plan = closed_loop_plan(args, units)
        print(f"closed loop client {args.client_id}: warm-up {plan[0]['input_id']}, then "
              f"{len(plan) - 1} units; sessions opened before the window: {sum(u['q_index'] == 0 for u in plan)}")


if __name__ == "__main__":
    if "--dry-run" in sys.argv[1:]:
        dry_run(sys.argv[1:])
    else:
        main(WORKLOAD)
