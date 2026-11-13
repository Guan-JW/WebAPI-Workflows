"""IOPaint: remove three objects from a photo, upscale it 2x, save it. One unit = one web-UI session.

    python workloads/iopaint/run.py --split test --iopaint-url http://127.0.0.1:8380

Each session drives an IOPaint server through iopaint_web.py, a headless port
of IOPaint's web client: open the app, open the photo, then for each of the
three objects choose interactive segmentation, click the object, Accept, Erase;
then RealESRGAN 2x and Save. Output `saved_image` = the bytes the client sends
to /api/v1/save_image, which the server writes unchanged to its output
directory. See README.md.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import requests  # noqa: E402

from iopaint_web import File, WebApp  # noqa: E402
from wbench import manifest  # noqa: E402
from wbench.harness import UnitResult, Workload, main  # noqa: E402

WORKLOAD_ID = "iopaint"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}  # File.type from the file picker
PLAN = (["GET /api/v1/server-config", "GET /api/v1/model", "POST /api/v1/gen-info"]
        + ["POST /api/v1/run_plugin_gen_mask", "POST /api/v1/inpaint"] * 3
        + ["POST /api/v1/run_plugin_gen_image", "POST /api/v1/save_image"])


def run_session(base_url, http, image, file_name, mime, clicks):
    """One session, as a user performs it in the web UI. Returns (saved bytes, app)."""
    app = WebApp(base_url, http)
    app.mount()                                        # page load
    app.openImage(File(image, file_name, mime))        # open the photo
    for x, y in clicks:
        app.toggleInteractiveSeg()                     # plugin menu: InteractiveSeg
        app.onCanvasMouseUp(x, y)                      # one positive click on the object
        app.store.handleInteractiveSegAccept()         # Accept
        app.store.runInpainting()                      # Erase (toolbar "Run Inpainting")
    app.store.runRenderablePlugin(False, "RealESRGAN", {"upscale": 2})  # plugin menu: RealESRGAN 2x
    saved = app.download()                             # Save (auto-saving: POST save_image)
    errors = [d for v, d in app.store.toasts if v == "destructive"]
    if errors:
        raise RuntimeError("; ".join(errors))
    return saved, app


class _Session(requests.Session):
    """A fresh browser page: own connection pool and cookies. Adds a request timeout as a safety net."""

    def __init__(self, timeout):
        super().__init__()
        self._timeout = timeout

    def request(self, *a, **kw):
        kw.setdefault("timeout", self._timeout)
        return super().request(*a, **kw)


def add_args(p):
    p.add_argument("--iopaint-url", default="http://127.0.0.1:8380",
                   help="IOPaint server; a comma-separated list gives client i the entry i mod n "
                        "(one server per client, see README)")
    p.add_argument("--server-output-dir", default=None,
                   help="the server's --output-dir, if this host can read it (comma-separated, aligned with "
                        "--iopaint-url). The saved file is deleted before and checked after each session, untimed.")
    p.add_argument("--unique-names", action="store_true",
                   help="open each photo under a per-session file name (c<client>-<n>-<name>) so that sessions "
                        "never share a save path; the image bytes do not change")
    p.add_argument("--http-timeout", type=float, default=600.0, help="per-request timeout, s (default: 600)")
    p.add_argument("--dry-run", action="store_true", help="print the units and the request plan, then exit")


def _pick(value, client_id):
    if value is None:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items[client_id % len(items)]


def units(args):
    rows = manifest.load(WORKLOAD_ID, args.split)
    if args.dry_run:
        n = len(rows) if args.limit is None else min(args.limit, len(rows))
        print(f"{WORKLOAD_ID} split={args.split}: {n} units, one session each, {len(PLAN)} requests per session")
        for r in rows[:n]:
            print(f"  {r['input_id']}  {r['file']}  {r['width']}x{r['height']}  clicks={r['clicks']}  "
                  f"objects={[o['category'] for o in r['objects']]}")
        print("request plan of one session:")
        for i, c in enumerate(PLAN, 1):
            print(f"  {i:2d}. {c}")
        sys.exit(0)
    return rows


def setup(ctx):
    a = ctx.args
    ctx.state["url"] = _pick(a.iopaint_url, a.client_id).rstrip("/")
    ctx.state["out_dir"] = _pick(a.server_output_dir, a.client_id)
    ctx.state["seq"] = 0
    for r in manifest.load(WORKLOAD_ID, a.split):
        path = os.path.join(ctx.data_dir, r["file"])
        if not os.path.exists(path) or manifest.sha256_file(path) != r["sha256"]:
            raise SystemExit(f"missing or changed input {path}; run workloads/iopaint/prepare_data.py")
    cfg = requests.get(ctx.state["url"] + "/api/v1/server-config", timeout=60).json()  # untimed check
    if not cfg.get("enableAutoSaving"):
        raise SystemExit("the IOPaint server has no --output-dir; start it with servers/iopaint/start.sh")


def reset(unit, ctx):
    ctx.state["seq"] += 1
    name = unit["file_name"]
    if ctx.args.unique_names:
        name = f"c{ctx.args.client_id}-{ctx.state['seq']:05d}-{name}"
    ctx.state["name"] = name
    out_dir = ctx.state["out_dir"]
    if out_dir and os.path.exists(os.path.join(out_dir, name)):
        os.remove(os.path.join(out_dir, name))


def run_one(unit, ctx):
    path = os.path.join(ctx.data_dir, unit["file"])
    with open(path, "rb") as f:
        image = f.read()
    name = ctx.state["name"]
    mime = MIME[os.path.splitext(unit["file_name"])[1].lower()]
    http = _Session(ctx.args.http_timeout)
    try:
        with ctx.timed():
            saved, app = run_session(ctx.state["url"], http, image, name, mime, unit["clicks"])
    finally:
        http.close()
    extra = {"save_name": name, "saved_file_checked": False}
    out_dir = ctx.state["out_dir"]
    if out_dir:
        with open(os.path.join(out_dir, name), "rb") as f:
            on_disk = f.read()
        if on_disk != saved:
            raise RuntimeError(f"saved file {name} differs from the bytes sent to save_image")
        extra["saved_file_checked"] = True
    return UnitResult({"saved_image": saved}, extra)


WORKLOAD = Workload(id=WORKLOAD_ID, run_one=run_one, add_args=add_args, units=units, setup=setup, reset=reset)

if __name__ == "__main__":
    main(WORKLOAD)
