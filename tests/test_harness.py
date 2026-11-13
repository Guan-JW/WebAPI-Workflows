"""Harness self-test against a local HTTP server (no workload services needed)."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from wbench.harness import UnitResult, Workload, main  # noqa: E402
from wbench.summarize import load, summarize  # noqa: E402


class Echo(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Length", str(len(body) * 2))
        self.end_headers()
        self.wfile.write(body * 2)

    def log_message(self, *a):
        pass


def _server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def test_rounds_and_groups(tmp_path):
    import requests

    srv = _server()
    url = f"http://127.0.0.1:{srv.server_address[1]}/echo"
    units = [{"input_id": f"q{i}", "session": f"s{i // 2}", "sha256": None} for i in range(4)]

    def run_one(u, ctx):
        requests.post(url, data=b"x" * 10)  # untimed set-up call
        with ctx.timed():
            r = requests.post(url, data=u["input_id"].encode())
        return UnitResult({"answer": r.content}, {"session": u["session"]})

    wl = Workload(id="selftest", run_one=run_one, units=lambda a: units, group_key=lambda u: u["session"])
    out = tmp_path / "r.jsonl"
    main(wl, ["--rounds", "2", "--warmup", "1", "--out", str(out), "--workdir", str(tmp_path / "w")])
    rows = load([str(out)])
    assert len(rows) == 12
    assert all(r["http_calls"] == 1 and r["bytes_out"] == 2 and r["bytes_in"] == 4 for r in rows)
    for rnd in range(3):  # questions of one session stay adjacent and ordered
        ids = [r["input_id"] for r in rows if r["round"] == rnd]
        assert sorted([ids[0:2], ids[2:4]]) == [["q0", "q1"], ["q2", "q3"]]
    s = summarize(rows)[0]
    assert s["units"] == 8 and s["errors"] == 0 and s["median_calls"] == 1
    srv.shutdown()


def test_closed_loop_cli(tmp_path):
    """Two clients through wbench.closed_loop on a tiny generated workload."""
    srv = _server()
    url = f"http://127.0.0.1:{srv.server_address[1]}/echo"
    wdir = tmp_path / "repo"
    wdir.mkdir()
    (wdir / "wbench").symlink_to(os.path.join(REPO, "wbench"))
    (wdir / "workloads" / "tiny").mkdir(parents=True)
    (wdir / "manifests" / "tiny").mkdir(parents=True)
    with open(wdir / "manifests" / "tiny" / "test.jsonl", "w") as f:
        for i in range(4):
            f.write(json.dumps({"input_id": f"u{i}"}) + "\n")
    (wdir / "workloads" / "tiny" / "run.py").write_text(
        "import os, sys\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))\n"
        "import requests\n"
        "from wbench.harness import Workload, main\n"
        f"URL = {url!r}\n"
        "def run_one(u, ctx):\n"
        "    return {'r': requests.post(URL, data=u['input_id'].encode()).content}\n"
        "if __name__ == '__main__':\n"
        "    main(Workload(id='tiny', run_one=run_one))\n")
    out = tmp_path / "conc"
    env = dict(os.environ, PYTHONPATH=str(wdir))
    subprocess.run([sys.executable, "-m", "wbench.closed_loop", "tiny", "--clients", "2", "--warmup-budget-s", "5",
                    "--out", str(out)], check=True, cwd=str(wdir), env=env)
    rows = load([str(out / "client0.jsonl"), str(out / "client1.jsonl")])
    timed = [r for r in rows if not r["warmup"]]
    assert len(timed) == 16 and {r["client_id"] for r in timed} == {0, 1}
    s = summarize(rows)[0]
    assert s["clients"] == 2 and s["throughput_per_s"] > 0
    srv.shutdown()
