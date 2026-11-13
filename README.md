# WebAPI-Workflows

A benchmark suite of ten application workflows built from calls to
model-serving web APIs.

In each workflow, one user action (an edit, a question, a review request, a
tour request) sends several HTTP requests to model services. The services are
either self-hosted (Stable Diffusion WebUI and its extensions, FastAPI
microservices, IOPaint) or hosted (the OpenAI API). The suite pins the
application code, the service versions and the inputs. It provides one
harness for latency, client-concurrency and output-equivalence measurements,
so that tools for such applications (profilers, serving systems, caching
layers, schedulers, program optimizers) can be compared on the same
workloads.

## Why this suite

Model compute is only part of the end-to-end time of these applications. The
rest depends on how the application composes its calls:
- how much data crosses the client–service boundary, and how often;
- whether identical requests repeat;
- whether independent calls run one after another;
- whether state is rebuilt on every interaction;
- which service keeps a model loaded between requests.

These effects appear only when the whole workflow runs as the application
runs it, with its own client code, its own request sequence and realistic
inputs. The suite packages ten such workflows, from four domains (image
editing and analysis, retrieval-augmented question answering, developer
tooling, speech generation), with fixed inputs.

## Workloads

### Image editing and analysis

**[HeadFashion](workloads/head_fashion/) — try on a new look.** A shopper
uploads a portrait to a hat-and-hairstyle preview tool. They swap in a new
hat, then ask for a different hairstyle on the edited photo. Each edit finds
its target from a text prompt and repaints it, and the second edit starts
from the result of the first.
*Stable Diffusion WebUI · GroundingDINO + SAM · SD v1.5 inpainting · 4 calls per photo*

**[CaptionCompare](workloads/caption_compare/) — one upload, many captions.**
A newly uploaded photo needs a caption in several places at once: alt text
for accessibility, tags for search, a line for the preview card. Each feature
asks the captioning service for its own caption of the same image with the
same model.
*Stable Diffusion WebUI interrogator (BLIP + CLIP) · 3 identical calls per photo*

**[ImageBlur](workloads/image_blur/) — blur before you post.** Before a street
photo goes public, a sharing service finds the faces and the cars in it,
blurs those regions and pastes them back into the original, so the published
picture shows the scene but no one's identity.
*Stable Diffusion WebUI · GroundingDINO + SAM · blur and compose extension · 4 calls per photo*

**[SegmentOCR](workloads/segment_ocr/) — read the plate.** A parking-lot
camera captures a soft, low-resolution frame. The system sharpens it,
confirms there is a car in view, isolates the license plate, crops it and
reads the characters.
*Stable Diffusion WebUI · ESRGAN · SAM · PP-OCRv4 · 4 calls per frame (5 when the first plate query misses)*

**[IOPaint](workloads/iopaint/) — clean up a photo.** In IOPaint's web
editor, a user clicks three unwanted objects one at a time to select and
erase them, then upscales the cleaned photo 2× and saves it.
*IOPaint server · SAM 2.1 · LaMa · Real-ESRGAN · 11 calls per session*

### Question answering over documents

**[ServiceQA](workloads/service_qa/) — ask the help desk.** A support
assistant that runs entirely on a company's own servers answers a customer's
question. It searches its knowledge base two ways (semantic vectors and
keywords), reranks what it found and has a small language model write the
answer from the best passages.
*Five FastAPI services · MiniLM · FAISS + BM25 · cross-encoder · Qwen2.5-1.5B · 5 calls per question*

**[HybridSearch](workloads/hybrid_search/) — ask your reading list.** A
researcher loads a stack of articles into a RAG app and asks about their
methods and results. The app checks that its hybrid search finds relevant
passages, then retrieves, reranks and answers with an LLM.
*awesome-llm-apps · RAGLite · OpenAI embeddings and chat · rerank service · 5 calls per question*

**[ChatWithPDF](workloads/chat_with_pdf/) — chat with a document.** A user
drops a PDF into a chat app and asks a series of follow-up questions about
it. Each answer draws on the document and on the conversation so far.
*awesome-llm-apps · Streamlit + embedchain · OpenAI embeddings and chat · 3 calls per question*

### Developer tooling

**[CodeReview](workloads/code_review/) — review this file.** A developer
submits a Python module and gets an automated review back: the code is
parsed, linted, scanned for security problems and summarized into an
approve or request-changes verdict, through four microservices.
*Four FastAPI services · ruff · Bandit · 5 calls per file*

### Speech generation

**[AudioTour](workloads/audio_tour/) — a tour guide in your pocket.** A
traveller names a landmark, picks what they care about (history,
architecture, ...) and how long the tour should be. The app plans the tour,
researches each topic on the web, writes a script and narrates it as an
audio file.
*awesome-llm-apps · OpenAI Agents SDK · web search · text-to-speech · 5 calls per tour*

### Inputs

| Workload | Inputs | Data license |
|---|---|---|
| HeadFashion | Open Images V7 photos with a hat and a person | images CC BY 2.0, annotations CC BY 4.0 |
| CaptionCompare | COCO val2017 images | per-image Flickr CC licenses, annotations CC BY 4.0 |
| ImageBlur | COCO val2017 images with people and cars | per-image Flickr CC licenses, annotations CC BY 4.0 |
| SegmentOCR | OpenALPR benchmark frames (US), Gaussian-blurred | AGPL-3.0 (repository license) |
| IOPaint | COCO val2017 images with three separate objects, plus click points | per-image Flickr CC licenses, annotations CC BY 4.0 |
| ServiceQA | MS MARCO v2.1 dev questions, 100k-passage corpus | MS MARCO terms (non-commercial research) |
| HybridSearch | QASPER questions and their arXiv articles | QASPER CC BY 4.0; articles under their arXiv licenses |
| ChatWithPDF | QASPER questions and their arXiv articles, one chat session per article | QASPER CC BY 4.0; articles under their arXiv licenses |
| CodeReview | CPython 3.9.6 standard-library modules of different sizes | PSF-2.0 |
| AudioTour | UNESCO World Heritage sites (via Wikidata), with interests and tour length | CC0 |

No input is chosen by hand. Each workload's inputs come from a public
dataset through a fixed selection rule and random seed, written down with
its exclusions in `manifests/<id>/SELECTION.md`. Raw inputs are not stored
in this repository; each workload's `prepare_data.py` downloads them and
checks their sha256.

## Sources

Where each workload comes from. The workload cards give the details: pinned
commits, model versions, and every adaptation with the reason for it.

| Workload | Source |
|---|---|
| HeadFashion | Derived from image editing (headwear and hairstyle preview). Built on [AUTOMATIC1111 WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) v1.10.1, [sd-webui-segment-anything](https://github.com/continue-revolution/sd-webui-segment-anything) (GroundingDINO, SAM) and Stable Diffusion v1.5. |
| CaptionCompare | Derived from image captioning. Built on the interrogate endpoint of AUTOMATIC1111 WebUI v1.10.1 (BLIP, CLIP). |
| ImageBlur | Derived from privacy-preserving photo sharing. Built on AUTOMATIC1111 WebUI v1.10.1, sd-webui-segment-anything and the sd-webui-blur extension in this suite. |
| SegmentOCR | Derived from license-plate recognition. Built on AUTOMATIC1111 WebUI v1.10.1, sd-webui-segment-anything, [sd-webui-ocr](https://github.com/SpenserCai/sd-webui-ocr) (PP-OCRv4) and ESRGAN. |
| CodeReview | A practice project on multi-service web APIs by an outside developer, included in adapted form. Built on ruff and Bandit. |
| ServiceQA | Derived from self-hosted support and knowledge-base assistants. Five FastAPI services in this suite, built on sentence-transformers, FAISS, rank-bm25, a cross-encoder reranker and Qwen2.5-1.5B-Instruct. |
| HybridSearch | [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) `rag_tutorials/hybrid_search_rag` at `6c16b23`, run unmodified. |
| ChatWithPDF | awesome-llm-apps `advanced_llm_apps/chat_with_X_tutorials/chat_with_pdf` at `6c16b23`, run unmodified. |
| AudioTour | awesome-llm-apps `voice_ai_agents/ai_audio_tour_agent` at `6c16b23`, run unmodified. |
| IOPaint | [Sanster/IOPaint](https://github.com/Sanster/IOPaint) 1.6.0 at `61a759fb`, server run unmodified. |

For the four applications taken from public repositories, the suite adds a
headless driver that issues the application's own request sequence. Their
cards list every adaptation, for example a model replaced because the
original was retired, or HybridSearch's Cohere reranker replaced by a local
stand-in service with a fixed delay. How these four were chosen:
[docs/selection_upstream_apps.md](docs/selection_upstream_apps.md).

### The same call patterns in public projects

The workloads derived from application areas, and CodeReview, follow call
patterns that also appear in public code. Each entry links the commit and
the lines where the pattern appears.

| Workload | Public project | What it does the same way |
|---|---|---|
| HeadFashion | [Auto-Photoshop-StableDiffusion-Plugin](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin) (7.3k★, MIT) | Turns a text prompt into a mask with the same `/sam/sam-predict` request with GroundingDINO ([sam.tsx L31-45](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin/blob/6f6d4907adf0b6a6e562d084238f02ed6b7503c1/typescripts/sam/sam.tsx#L31-L45)), then inpaints the masked region through `/sdapi/v1/img2img` ([modes.ts L539](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin/blob/6f6d4907adf0b6a6e562d084238f02ed6b7503c1/typescripts/session/modes.ts#L539), [L356](https://github.com/AbdullahAlfaraj/Auto-Photoshop-StableDiffusion-Plugin/blob/6f6d4907adf0b6a6e562d084238f02ed6b7503c1/typescripts/session/modes.ts#L356)). |
| HeadFashion | [Fashion-Model-Generation-with-Stable-Diffusion](https://github.com/ybai789/Fashion-Model-Generation-with-Stable-Diffusion) (Apache-2.0) | Generates garment-model photos: a SAM mask from `/sam/sam-predict` ([service.py L342](https://github.com/ybai789/Fashion-Model-Generation-with-Stable-Diffusion/blob/e5059c9d334a0326a7cc2850f3f463f5cf495a35/service.py#L342)), then inpainting through `/sdapi/v1/img2img` ([L134-168](https://github.com/ybai789/Fashion-Model-Generation-with-Stable-Diffusion/blob/e5059c9d334a0326a7cc2850f3f463f5cf495a35/service.py#L134-L168)). |
| ImageBlur | Auto-Photoshop-StableDiffusion-Plugin (above) | Text-prompted segmentation on the WebUI as the first step of an edit of the selected region. |
| ImageBlur | [celantur-arcgis-tools](https://github.com/celantur/celantur-arcgis-tools) (client of the Celantur anonymization service) | Blurs faces and license plates in images through a web API: create a task, upload the image, poll, download the anonymized image ([CelanturBlurringToolbox.pyt L103-158](https://github.com/celantur/celantur-arcgis-tools/blob/8a956486d3beaf40b491c535eb40147694e3a380/geoprocessing-toolbox/CelanturBlurringToolbox.pyt#L103-L158)). |
| SegmentOCR | [CodeProject.AI ALPR module](https://github.com/codeproject/CodeProject.AI-ALPR) (for CodeProject.AI Server, 1k★) | Asks a separate plate-detection service for plate boxes ([ALPR.py L86](https://github.com/codeproject/CodeProject.AI-ALPR/blob/450f6c96996e15069619237251db663b03f87d86/ALPR.py#L86)), crops each plate ([L128](https://github.com/codeproject/CodeProject.AI-ALPR/blob/450f6c96996e15069619237251db663b03f87d86/ALPR.py#L128)), rescales it ([L243](https://github.com/codeproject/CodeProject.AI-ALPR/blob/450f6c96996e15069619237251db663b03f87d86/ALPR.py#L243)) and runs PaddleOCR on it ([L367](https://github.com/codeproject/CodeProject.AI-ALPR/blob/450f6c96996e15069619237251db663b03f87d86/ALPR.py#L367)). |
| CaptionCompare | [Open WebUI](https://github.com/open-webui/open-webui) (158k★) | After each chat turn, three features (follow-up suggestions, a title, tags) each send the conversation to the model in a separate request ([middleware.py L3609](https://github.com/open-webui/open-webui/blob/f7ac7ee10962ddec0017f5c29b6740d9b9c5faca/backend/open_webui/utils/middleware.py#L3609), [L3662](https://github.com/open-webui/open-webui/blob/f7ac7ee10962ddec0017f5c29b6740d9b9c5faca/backend/open_webui/utils/middleware.py#L3662), [L3718](https://github.com/open-webui/open-webui/blob/f7ac7ee10962ddec0017f5c29b6740d9b9c5faca/backend/open_webui/utils/middleware.py#L3718)). |
| ServiceQA | [OPEA GenAIExamples](https://github.com/opea-project/GenAIExamples) ChatQnA (LF AI & Data, Apache-2.0) | The same chain of separate services: embedding (`/embed`), retriever, reranker (`/rerank`), LLM ([chatqna.py L262-301](https://github.com/opea-project/GenAIExamples/blob/f56422671c8bdf46f59dd758c8c9e38ca41d6555/ChatQnA/chatqna.py#L262-L301)). |
| CodeReview | [pr-agent](https://github.com/The-PR-Agent/pr-agent) (16k★, MIT) | An automated pull-request reviewer: collects the change from the Git host's REST API ([pr_reviewer.py L328-387](https://github.com/The-PR-Agent/pr-agent/blob/8257f6adb2514889fe2f3a96f332a010a4c36538/pr_agent/commands/pr_reviewer.py#L328-L387), [L723](https://github.com/The-PR-Agent/pr-agent/blob/8257f6adb2514889fe2f3a96f332a010a4c36538/pr_agent/commands/pr_reviewer.py#L723)), sends it to an LLM ([L734](https://github.com/The-PR-Agent/pr-agent/blob/8257f6adb2514889fe2f3a96f332a010a4c36538/pr_agent/commands/pr_reviewer.py#L734)) and posts the review ([L827](https://github.com/The-PR-Agent/pr-agent/blob/8257f6adb2514889fe2f3a96f332a010a4c36538/pr_agent/commands/pr_reviewer.py#L827)). |

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r workloads/code_review/requirements.txt -r servers/code_review/requirements.txt

python workloads/code_review/prepare_data.py           # inputs -> data/code_review/
bash servers/code_review/start_services.sh             # four local services, CPU only
python workloads/code_review/run.py --split test       # -> runs/code_review/test_<utc>_c0.jsonl
python -m wbench.summarize runs/code_review/*.jsonl
```

Each workload card lists its own services, models and commands. The image
workloads need a GPU server (`servers/a1111/`, `servers/iopaint/`). The
hosted-API workloads need an OpenAI API key, and running them costs money.

Common runner options for every `run.py`: `--split`, `--rounds` (default 3),
`--warmup` (default 1), `--limit`, `--seed`, `--out`, `--save-outputs`.
Client concurrency:

```bash
python -m wbench.closed_loop code_review --clients 4 --split test
```

## Measurement protocol

The protocol is in [docs/protocol.md](docs/protocol.md) and the result schema
in [docs/results.md](docs/results.md). In short:
- tools may observe profiling inputs only, and results are reported on test
  inputs;
- latency is the p50 over three timed rounds after one warm-up round, with
  bootstrap confidence intervals over inputs;
- concurrency is a closed loop with C = 1, 2, 4 and 8 isolated clients;
- each workload defines an output-equivalence rule, and every configuration
  under test is checked against the original.

## Repository layout

```text
wbench/                 harness: runner, HTTP recorder, summaries, output comparison, concurrency
workloads/<id>/         workload card, run.py, client code, prepare_data.py, source.json
manifests/<id>/         input lists per split, with selection rules (SELECTION.md)
servers/<name>/         set-up for self-hosted services: pinned upstream code, patches, service code
docs/                   protocol, result schema, selection of upstream applications
tests/                  harness tests
```

## Status

Version 0.1.0. On the hardware the suite was developed on, every workload ran
end to end. For this release, each extracted client was checked against the
reference client on a deterministic mock backend, or against live local
services where they run on a CPU (CodeReview, IOPaint). The two cases
compared request sequences and outputs. The GPU set-up scripts have not yet
been run from a clean machine; reports are welcome.

## Licenses

The suite's own code is under the Apache License 2.0 ([LICENSE](LICENSE)).
Upstream applications, extensions, models and datasets keep their own
licenses, listed in [THIRD_PARTY.md](THIRD_PARTY.md) and in each workload's
`source.json`. Several datasets allow non-commercial research use only.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workload layout and card
template.
