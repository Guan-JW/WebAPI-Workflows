# Selection of the upstream applications

Three workloads are third-party applications run unmodified:
- HybridSearch: `rag_tutorials/hybrid_search_rag`;
- ChatWithPDF: `advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf`;
- AudioTour: `voice_ai_agents/ai_audio_tour_agent`.

All three come from [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)
at commit `6c16b23f1bacd0fdf240bb5141ef45e59e82c306` (2026-10-21, Apache-2.0).

## Criteria

A catalog scan on 2026-11-02 applied five filters to every application in the repository. The scan
read source code at the pinned commit and executed nothing.

- **F1: public, licensed, third-party.**
- **F2: a fixed, non-agentic workflow.** These count as agentic: tool-calling loops, multi-agent
  coordination, handoffs, MCP, browser or desktop agents, knowledge-search tools, and skill scripts.
  Two things are allowed: an LLM classifier choosing between branches written in code, and tools
  hosted inside a single HTTP call (for example, OpenAI web search).
- **F3: at least 3 HTTP calls across at least 2 endpoints per user action.** An endpoint is a
  (service, operation) pair. Because Streamlit reruns the whole script on every interaction, that
  work counts, and so do polling calls. Telemetry, Neo4j Bolt and WebSocket traffic do not count.
- **F4: runnable as-is** with an OpenAI key, free-tier keys, or self-hostable services.
- **F5: at least 30 public inputs.**

## Funnel

The scan split the catalog into 186 applications by a fixed walk of its folders. The counts below
come from the scan's per-application table and were recounted from it.

| Stage | Applications |
|---|---|
| Enumerated | 186 |
| F1 | 186 |
| F2 | 87 |
| F3 | 32 |
| F4 | 27 |
| F5 | 23 |
| Remaining after excluding `hybrid_search_rag`, which had been selected before the scan | 22 |

ChatWithPDF and AudioTour were chosen by hand from these 22 candidates. They are not a random
sample of them.

## The three applications

| | HybridSearch | ChatWithPDF | AudioTour |
|---|---|---|---|
| How selected | Chosen before the scan; the scan recorded it as already in use and did not count it as a candidate | Passed F1-F5 | Passed F1-F5 |
| F2 (fixed workflow) | RAGLite pipeline: search, rerank, answer | embedchain App: add the PDF, then chat | planner, research agents, orchestrator, then TTS. Web search runs inside each Responses call |
| F3 (scan estimate) | 4-5 calls: embeddings, rerank, chat | 3 or more: chunk embeddings, query embedding, chat | up to 7: planner, up to 4 research calls, orchestrator, TTS |
| F3 (measured, this suite) | 5 calls on 3 endpoints | 3 calls on 2 endpoints | 5 calls on 2 endpoints, with the default 2 interests |
| F4 | Needs OpenAI, Anthropic and Cohere keys as published. Here it runs with OpenAI only: `gpt-4o-mini` replaces the retired Claude model, and a local rerank stand-in replaces Cohere (see its card) | OpenAI key | OpenAI key |
| F5 (inputs) | QASPER documents and questions | QASPER documents and questions | UNESCO World Heritage Sites (Wikidata) |

The scan's call counts are estimates from reading code. Each workload card gives the call sequence
measured in development.

## IOPaint

IOPaint ([Sanster/IOPaint](https://github.com/Sanster/IOPaint), 1.6.0, Apache-2.0) was chosen by
hand, not through the catalog scan. It is a self-hosted image-editing application: a FastAPI server
and a React web client, with about 41k lines of Python. Its own web client chains several model calls
on one server and uploads each returned image again as the input of the next call. A separate scan
of third-party clients of self-hosted model services searched GitHub code and repositories, including
the endpoint string `run_plugin_gen_mask`. It found no independent IOPaint client: every IOPaint hit
was a fork or an in-process use. The workload therefore drives the server with a headless port of
IOPaint's own web client; see `workloads/iopaint/README.md` for the port and how it differs from a
browser session.
