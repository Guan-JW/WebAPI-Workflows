"""ImageBlur: blur faces and cars in a photo before it is shared. See README.md."""
import base64
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from wbench.harness import Workload, main  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"image_blur_{name}", os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wf = _load("workflow")


def add_args(p):
    p.add_argument("--a1111-url", default="http://127.0.0.1:7861",
                   help="AUTOMATIC1111 server (default: the instance started with DINO_UNLOAD_AFTER_CALL=1, "
                        "see servers/a1111/README.md)")
    p.add_argument("--blur-ksize", type=int, default=wf.BLUR_KSIZE,
                   help="Gaussian kernel size sent to /blur/generate (default: 41, as measured)")


def run_one(unit, ctx):
    out_dir = os.path.join(ctx.workdir, str(unit["input_id"]))
    image_b64 = wf.read_image_as_b64(os.path.join(ctx.data_dir, unit["file"]))
    with ctx.timed():  # first request to final image
        res = wf.blur_faces_and_cars(image_b64, ctx.args.a1111_url, out_dir, blur_ksize=ctx.args.blur_ksize)
    return {k: base64.b64decode(v) for k, v in res.items()}


WORKLOAD = Workload(id="image_blur", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
