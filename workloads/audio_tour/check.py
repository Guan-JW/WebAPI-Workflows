"""Equivalence check for AudioTour (README "Measurement").

    python check.py reference.jsonl [more reference files] --candidate candidate.jsonl [...]

Hosted LLM, web-search and TTS outputs differ from run to run, so tour text and audio are not
compared between runs. A candidate request passes when:
  live      it finished without error, with a non-empty tour and MP3 audio (run.py raises otherwise);
  dataflow  extra.dataflow.ok: the orchestrator prompt holds this request's research outputs, the
            tour is the orchestrator's sections joined as the app does, the speech input is the
            tour and the audio is the speech response body;
  inputs    the requests whose bytes depend only on the input (architecture and history research,
            and the planner when it is sent) equal a reference request for the same input.
Failed requests are counted, not dropped. Exit status 1 if any request fails a check.
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from wbench.summarize import load  # noqa: E402

INPUT_CALLS = ("req_architecture", "req_history", "req_planner")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference", nargs="+")
    p.add_argument("--candidate", nargs="+", required=True)
    a = p.parse_args()
    ref = [r for r in load(a.reference) if not r.get("warmup") and r["status"] == "ok"]
    cand = [r for r in load(a.candidate) if not r.get("warmup")]
    allowed = defaultdict(lambda: defaultdict(set))
    for r in ref:
        for k in INPUT_CALLS:
            if k in r["outputs"]:
                allowed[r["input_id"]][k].add(r["outputs"][k])
    n = Counter()
    for r in cand:
        n["requests"] += 1
        if r["status"] != "ok":
            n["live_failed"] += 1
            print(f"FAILED   {r['input_id']} r{r['round']}: {r['error']}")
            continue
        if not r["extra"].get("dataflow", {}).get("ok"):
            n["dataflow_failed"] += 1
            print(f"DATAFLOW {r['input_id']} r{r['round']}: {r['extra'].get('dataflow')}")
        if r["input_id"] not in allowed:
            n["no_reference"] += 1
            continue
        for k in INPUT_CALLS:
            h = r["outputs"].get(k)
            if h is None:
                n[f"{k}_not_sent"] += 1
                if k != "req_planner":
                    n["input_calls_differ"] += 1
                    print(f"MISSING  {r['input_id']} r{r['round']}: {k}")
            elif h not in allowed[r["input_id"]][k]:
                n["input_calls_differ"] += 1
                print(f"DIFFERS  {r['input_id']} r{r['round']}: {k}")
        n["checked"] += 1
    print(", ".join(f"{k} {v}" for k, v in sorted(n.items())))
    sys.exit(1 if n["live_failed"] or n["dataflow_failed"] or n["input_calls_differ"] or n["no_reference"] else 0)


if __name__ == "__main__":
    main()
