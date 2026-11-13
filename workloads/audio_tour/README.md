# AudioTour

A user types a place name into the AI Audio Tour Agent. They keep the default interests, History and
Architecture, and the default length of 10 minutes, and click "Generate Tour". The app asks a
planner agent for a time plan and runs one research agent per interest, each with hosted web search.
An orchestrator agent writes the tour from the research, and the tour is turned into speech. The user
reads the tour and downloads the MP3. One unit of work is one click.

| | |
|---|---|
| Domain | Multi-step LLM content generation with web search and text-to-speech |
| Source | awesome-llm-apps `voice_ai_agents/ai_audio_tour_agent` at `6c16b23` (Apache-2.0), run unmodified |
| Services | OpenAI Responses API (gpt-4o; gpt-4o-mini with hosted web search) and speech API (gpt-4o-mini-tts), hosted |
| Calls per unit | 5: 4 Responses calls and 1 speech call (plus one retried attempt; see Workflow) |
| Inputs | UNESCO World Heritage Sites via Wikidata (CC0), 5 profiling / 30 test |
| Unit | one "Generate Tour" click |

## Source

Application: `voice_ai_agents/ai_audio_tour_agent` of
[Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) at commit
`6c16b23f1bacd0fdf240bb5141ef45e59e82c306` (Apache-2.0). `fetch_upstream.sh` fetches it and checks
the sha256 of `ai_audio_tour_agent.py`, `manager.py`, `agent.py`, `printer.py`, `requirements.txt`,
`README.md` and `LICENSE`. The app files are imported unmodified.

`requirements.txt` keeps the app's own pins: openai 1.68.2, openai-agents 0.0.6, pydantic 2.10.6 and
streamlit 1.43.2. No model, key or service was replaced; every model the app names answered in
development.

### Adaptations

1. **Tracing off: `OPENAI_AGENTS_DISABLE_TRACING=1`**, set before `agents` is imported. This is the
   SDK's documented switch. openai-agents 0.0.6 otherwise uploads trace batches to
   `api.openai.com/v1/traces/ingest` from a background thread. Those uploads are telemetry, not
   workflow calls. `TourManager.run` still opens its `trace(...)` block, now a no-op, and still
   prints a trace URL.
2. **Headless driver.**
   - `ai_audio_tour_agent.py` is imported in Streamlit bare mode. Its widgets return their defaults
     and `st.button` returns False, so the import starts no work.
   - `run.py` then makes the click's calls in the script's order: `set_default_openai_key` (L48),
     `TourManager().run` through the app's `run_async` (L102-L105), `tts` (L114), and reading the
     MP3 file (L122).
   - The `st.*` display calls in between are not made. `voice_style` (L86-L90) is never read on
     this path.
3. **The API key comes from `OPENAI_API_KEY`.** It is passed to `set_default_openai_key` as L48
   does with the sidebar value. `tts()` builds `OpenAI()`, which reads the same variable.
4. **One copy of the app per client process.** Each client imports its own byte-identical,
   hash-checked copy of the four app files from its `--workdir`. The app writes `speech_tour.mp3`
   next to its module, so concurrent clients need separate output paths.
5. **`STREAMLIT_LOGGER_LEVEL=error`** silences Streamlit's bare-mode warnings.
6. **The input list comes from Wikidata (P757), not the UNESCO XML export.**
   `whc.unesco.org/en/list/xml/` answered scripted downloads with a Cloudflare challenge (HTTP 403)
   on 2026-11-03.

## Workflow

One click (`manager.py` L30-97, `ai_audio_tour_agent.py` L102-L122). Calls run one after another:

1. **POST /v1/responses**, the planner (`gpt-4o`, structured output `Planner`). Its input is the
   location, the interests and the duration. Its result is not read later in the click.
2. **POST /v1/responses**, architecture research (`gpt-4o-mini`, hosted `web_search_preview`,
   `tool_choice=required`). The word limit is 750-770: 10 minutes × 150 words per minute, divided
   between the 2 interests.
3. **POST /v1/responses**, history research. The setup is the same as in step 2.
4. **POST /v1/responses**, the orchestrator (`gpt-4o-mini`, structured output `FinalTour`). Its
   prompt contains the history output and then the architecture output, in the order of the
   interests.
5. The tour is the orchestrator's `architecture` and `history` fields joined by a blank line
   (L78-95).
6. **POST /v1/audio/speech** (`gpt-4o-mini-tts`, voice `nova`, the app's instructions). Its input is
   the tour. The returned MP3 is written to `speech_tour.mp3` and read back.

**The retried first call.** `run_async` calls `asyncio.run` once per click. The agents SDK's shared
`httpx.AsyncClient` keeps a pooled connection bound to the previous click's event loop, which is
now closed. So, in a long-lived process, the first call of every click after the first fails at
once (`RuntimeError`). The openai SDK retries it about 0.4-0.5 s later, with
`x-stainless-retry-count: 1`.

The recorder counts the failed attempt as a call without a status: 6 calls instead of 5
(`extra.sdk_retries`). A Streamlit server process pays this retry too. In development it occurred
on every click after a process's first in the throughput runs, and in 33 of 87 baseline clicks in
the interleaved latency runs.

## Inputs

35 UNESCO World Heritage Sites, taken from Wikidata (CC0 1.0) on 2026-11-03:
- the rule keeps whole sites with one English label (1,090 sites), shuffles them with seed
  20261103, and takes the first 35;
- profiling: rows 0-4; test: rows 5-34;
- location: the English label; interests and duration: the UI defaults.

The inputs are short strings in the manifest, so `prepare_data.py` only checks their hashes. It can
also re-check the source or re-apply the rule to a saved query result. Details are in
`manifests/audio_tour/SELECTION.md`.

## Deployment

**Services.** Hosted OpenAI APIs only; there is no replica count. Web search runs inside the
Responses calls.

**State.** One client process serves its clicks one after another, as one Streamlit server process
would. The agents SDK's client and connection pool persist across clicks in that process. There is
no cache.

**Development hardware.** Apple Silicon Mac, CPython 3.11.18 arm64.

## Measurement

**Timed window.** The whole click: from `set_default_openai_key` to the MP3 bytes having been read.
The checks run after the window.

**Outputs.**
- `tour`: the text shown; `audio`: the MP3 served.
- `req_planner`, `req_architecture`, `req_history`: the request bodies of the three calls whose
  bytes depend only on the input.
- `extra`: `dataflow`, `tour_words`, `audio_seconds` and `sdk_retries`.

**Equivalence rule** (`check.py`). Tour text and audio are not compared between runs, because model,
search and speech outputs vary. A candidate click passes when all three checks hold:
- **live**: it finished without error, with a non-empty tour and MP3 audio;
- **dataflow**: the orchestrator prompt contains this click's own research outputs; the tour is the
  orchestrator's sections joined as the app does; the speech input is the tour; and the audio is
  the speech response body;
- **inputs**: the input-determined requests are byte-identical to a reference request for the same
  input. That means the architecture and history requests, and the planner request when it is sent.

Failed clicks are counted, never dropped.

**Development reference** (2026-11-03, 30 test inputs × 3 rounds, one process):
- 87 of 90 baseline clicks succeeded; pooled p50 60,997 ms, p95 92,676 ms;
- the 3 failures were the app's own `ModelBehaviorError: Invalid JSON` (see below);
- estimated cost, at list prices: $0.12-0.14 per click.

## Running

```bash
cd workloads/audio_tour
./fetch_upstream.sh
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -I prepare_data.py              # checks the 35 inline inputs
.venv/bin/python run.py --split test --dry-run   # imports the app, prints the plan; no API calls
export OPENAI_API_KEY=...                        # paid calls from here on (about $0.13 per click)
.venv/bin/python run.py --split test             # 1 warm-up + 3 timed rounds
.venv/bin/python check.py <reference.jsonl> --candidate <candidate.jsonl>
cd ../.. && workloads/audio_tour/.venv/bin/python -m wbench.closed_loop audio_tour --clients 4
python -m wbench.summarize runs/audio_tour/*.jsonl
```

## Known limitations

- **The app's own structured-output failure.** A research agent's JSON output can end mid-string
  (`ModelBehaviorError: Invalid JSON`), and the app does not retry. This happened in 3 of 90
  development baseline clicks.
- **Outputs change from run to run.** Web search results, research text and speech audio vary
  between runs and over time.
- **The default warm-up round costs money.** It runs every unit once; development used one warm-up
  click per process (test input whs-332).
- **Latency drifts during the day.** Hosted-API latency changed within an evening in development.
  Compare configurations interleaved, in one session.
