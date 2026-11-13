"""HeadFashion: restyle the hat, then the hair, on one photo. See README.md."""
import base64
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from wbench.harness import Workload, main  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"head_fashion_{name}", os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wf = _load("workflow")


def add_args(p):
    p.add_argument("--a1111-url", default="http://127.0.0.1:7861",
                   help="AUTOMATIC1111 server (default: the instance started with DINO_UNLOAD_AFTER_CALL=1, "
                        "see servers/a1111/README.md)")
    p.add_argument("--inpaint-seed", type=int, default=wf.DEFAULT_SEED,
                   help="img2img seed for both edits (default: 1234, as measured; -1 = random per call)")


def run_one(unit, ctx):
    out_dir = os.path.join(ctx.workdir, str(unit["input_id"]))
    orig_b64 = wf.load_input(os.path.join(ctx.data_dir, unit["file"]), out_dir)
    with ctx.timed():  # first request to final image
        res = wf.edit(orig_b64, ctx.args.a1111_url, out_dir, seed=ctx.args.inpaint_seed)
    return {k: base64.b64decode(v) for k, v in res.items()}


WORKLOAD = Workload(id="head_fashion", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
