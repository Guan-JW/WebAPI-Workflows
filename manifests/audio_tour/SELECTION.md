# AudioTour inputs: selection

**Source.** Every Wikidata item with a World Heritage Site ID (property P757), with its English
label and country (CC0 1.0). Query, sent to `https://query.wikidata.org/sparql` with CSV output:

```sparql
SELECT ?item ?itemLabel ?whs ?countryLabel WHERE { ?item wdt:P757 ?whs . OPTIONAL { ?item wdt:P17 ?country . } SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }
```

The query was retrieved at 2026-11-03T07:18Z. The result had 6,738 rows and sha256
`2707a45a95d3a82034d8bb10b3222810add146c5f0eea33c0c681da22591ae93` (manifest field `dataset_sha256`).
The official export at `https://whc.unesco.org/en/list/xml/` answered scripted downloads with a
Cloudflare challenge (HTTP 403) that day.

**Rule.** Seed `20261103`:
- keep IDs that are plain integers (whole sites, not components) and map to exactly one item with
  an English label: 1,090 sites;
- sort them by ID and shuffle with `random.Random(20261103)`;
- take the first 35: rows 0-4 are `profiling` and rows 5-34 are `test`.
- location: the English label, which is what a user types into "Where would you like to explore?";
- interests and duration: the app's UI defaults, `["History", "Architecture"]` (multiselect default,
  `ai_audio_tour_agent.py` L67-L72) and 10 minutes (slider default, L76-L83).

**Check (2026-11-12).** `prepare_data.py --rebuild` on the original query result reproduces the 35
rows exactly. `prepare_data.py --check-wikidata` found all 35 items still carrying the same P757 ID
and English label (the new result had 6,738 rows and a different sha256).

**Fields.** `input_id` is `whs-<UNESCO list id>`. `idx` is the row in the shuffled list above (the
development records use it). `sha256` is
`sha256(json.dumps({"location", "interests", "duration"}, sort_keys=True))`. `source_url` is the
site's UNESCO page, and `wikidata` is the item URI.
