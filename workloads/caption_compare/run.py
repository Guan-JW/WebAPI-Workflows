"""CaptionCompare: three identical captioning requests for one image. See README.md."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from wbench.harness import UnitResult, Workload, main  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"caption_compare_{name}", os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wf = _load("workflow")


def add_args(p):
    p.add_argument("--a1111-url", default="http://127.0.0.1:7860",
                   help="AUTOMATIC1111 server (default: the instance without DINO_UNLOAD_AFTER_CALL, "
                        "see servers/a1111/README.md)")
    p.add_argument("--model", default=wf.MODEL, help="interrogate model (default: clip, as measured)")
    p.add_argument("--repeat", type=int, default=wf.REPEAT, help="identical requests per unit (default: 3, as measured)")


def run_one(unit, ctx):
    out_dir = os.path.join(ctx.workdir, str(unit["input_id"]))
    image_b64 = wf.load_input(os.path.join(ctx.data_dir, unit["file"]))
    with ctx.timed():  # first request to the last caption written
        caps = wf.caption_repeat(image_b64, ctx.args.a1111_url, out_dir, model=ctx.args.model, repeat=ctx.args.repeat)
    return UnitResult({"captions": "\n".join(caps).encode("utf-8")}, {"n_captions": len(caps)})


WORKLOAD = Workload(id="caption_compare", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
