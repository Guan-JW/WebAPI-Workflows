"""SegmentOCR: read the license plate in a low-quality camera frame. See README.md."""
import base64
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from wbench.harness import Workload, main  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"segment_ocr_{name}", os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wf = _load("workflow")


def add_args(p):
    p.add_argument("--a1111-url", default="http://127.0.0.1:7861",
                   help="AUTOMATIC1111 server (default: the instance started with DINO_UNLOAD_AFTER_CALL=1, "
                        "see servers/a1111/README.md)")


def run_one(unit, ctx):
    out_dir = os.path.join(ctx.workdir, str(unit["input_id"]))
    img = wf.load_input(os.path.join(ctx.data_dir, unit["file"]))
    first = wf.extras_payload(img)      # the frame is PNG-encoded before the first request is sent
    with ctx.timed():                   # first request to OCR text
        d = wf.read_plate(first, ctx.args.a1111_url, out_dir)
    out = {k: base64.b64decode(d[k]) for k in ("car_mask", "plate_mask", "plate_crop")}
    out["ocr_text"] = d["ocr_text"].encode("utf-8")
    if d["plate_bbox"] is not None:
        out["plate_bbox"] = json.dumps(d["plate_bbox"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    return out


WORKLOAD = Workload(id="segment_ocr", run_one=run_one, add_args=add_args)

if __name__ == "__main__":
    main(WORKLOAD)
