"""Inputs of AudioTour: 35 UNESCO World Heritage Sites (location text, interests, duration).

    python -I prepare_data.py                    # check every manifest row's sha256; nothing to download
    python -I prepare_data.py --check-wikidata   # also re-run the source query and report changes
    python -I prepare_data.py --rebuild FILE.csv # re-apply the selection rule to a saved query result

The inputs are short strings carried in the manifest rows, so no files are fetched. A row's sha256 is
sha256(json.dumps({"location", "interests", "duration"}, sort_keys=True)).

The list was selected from a Wikidata query (manifests/audio_tour/SELECTION.md). Wikidata changes
over time, so --check-wikidata reports, for each row, whether the item still carries the same World
Heritage Site ID (P757) and English label; --rebuild reproduces the selection exactly only from the
original query result (sha256 in SELECTION.md). Uses only the standard library.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

WORKLOAD = "audio_tour"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENDPOINT = "https://query.wikidata.org/sparql"
QUERY = ('SELECT ?item ?itemLabel ?whs ?countryLabel WHERE { ?item wdt:P757 ?whs . OPTIONAL { ?item wdt:P17 '
         '?country . } SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }')
CSV_SHA256 = "2707a45a95d3a82034d8bb10b3222810add146c5f0eea33c0c681da22591ae93"
SEED, N_PROFILING, N_TEST = 20261103, 5, 30
UA = "WebAPI-Workflows prepare_data (World Heritage Site list)"


def rows():
    out = []
    for split in ("profiling", "test"):
        with open(os.path.join(REPO, "manifests", WORKLOAD, f"{split}.jsonl"), encoding="utf-8") as f:
            out += [json.loads(x) for x in f if x.strip()]
    return out


def input_sha(r):
    return hashlib.sha256(json.dumps({k: r[k] for k in ("location", "interests", "duration")},
                                     sort_keys=True).encode()).hexdigest()


def select(raw):
    """The selection rule: integer P757 IDs that map to exactly one item with an English label,
    sorted by ID, shuffled with random.Random(SEED); the first 35 (rows 0-4 profiling, 5-34 test)."""
    recs = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    items, label = defaultdict(set), {}
    for r in recs:
        items[r["whs"]].add(r["item"])
        label[r["item"]] = r["itemLabel"]
    ids = sorted((k for k in items if re.fullmatch(r"[0-9]+", k) and len(items[k]) == 1
                  and not re.fullmatch(r"Q[0-9]+", label[next(iter(items[k]))])), key=int)
    random.Random(SEED).shuffle(ids)
    return len(recs), len(ids), [(int(w), label[next(iter(items[w]))]) for w in ids[: N_PROFILING + N_TEST]]


def fetch_csv():
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': QUERY})}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:   # the query service may limit clients to one query a minute
            if e.code != 429 or attempt:
                raise
            time.sleep(min(120, int(e.headers.get("Retry-After") or 65)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check-wikidata", action="store_true")
    p.add_argument("--rebuild", metavar="CSV")
    a = p.parse_args()
    man = rows()
    bad = [r["input_id"] for r in man if input_sha(r) != r["sha256"]]
    print(f"{len(man) - len(bad)}/{len(man)} manifest rows match their sha256" + (f"; mismatches: {bad}" if bad else ""))
    status = 1 if bad else 0
    if a.check_wikidata:
        raw = fetch_csv()
        recs = list(csv.DictReader(raw.decode("utf-8").splitlines()))
        now = defaultdict(set)
        for r in recs:
            now[r["item"]].add((r["whs"], r["itemLabel"]))
        print(f"query result now: {len(recs)} rows, sha256 {hashlib.sha256(raw).hexdigest()} "
              f"(selection used {CSV_SHA256})")
        changed = 0
        for r in man:
            ok = (str(r["whs_id"]), r["location"]) in now.get(r["wikidata"], set())
            changed += not ok
            if not ok:
                print(f"  changed  {r['input_id']} {r['wikidata']}: now {sorted(now.get(r['wikidata'], set()))}")
        print(f"{len(man) - changed}/{len(man)} rows: item, P757 and English label unchanged")
    if a.rebuild:
        with open(a.rebuild, "rb") as f:
            raw = f.read()
        n_rows, n_ids, chosen = select(raw)
        same = chosen == [(r["whs_id"], r["location"]) for r in sorted(man, key=lambda r: r["idx"])]
        print(f"{a.rebuild}: sha256 {hashlib.sha256(raw).hexdigest()} ({'original' if hashlib.sha256(raw).hexdigest() == CSV_SHA256 else 'not the original'}), "
              f"{n_rows} rows, {n_ids} sites after the rule; first 35 {'equal' if same else 'DIFFER from'} the manifest")
        status |= 0 if same else 1
    sys.exit(status)


if __name__ == "__main__":
    main()
