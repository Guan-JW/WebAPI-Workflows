# Third-party components and data

The suite's own code (`wbench/`, the workload clients and drivers, the
service code under `servers/service_qa/` and `servers/a1111/extensions/`) is
under the Apache License 2.0. Upstream code is fetched at pinned commits and
is not redistributed here, except where noted. Exact pins, URLs and hashes are
in each workload's `source.json`.

## Applications and services

| Component | Used by | License | In this repository |
|---|---|---|---|
| AUTOMATIC1111 stable-diffusion-webui v1.10.1 | HeadFashion, CaptionCompare, ImageBlur, SegmentOCR | AGPL-3.0 | fetched by `servers/a1111/setup.sh` |
| sd-webui-segment-anything (continue-revolution) | HeadFashion, ImageBlur, SegmentOCR | none stated upstream | fetched; small patches in `servers/a1111/patches/` |
| sd-webui-ocr (SpenserCai) | SegmentOCR | none stated upstream | fetched; small patch in `servers/a1111/patches/` |
| sd-webui-blur | ImageBlur | part of this suite; Apache-2.0 | `servers/a1111/extensions/sd-webui-blur/` |
| Code-review services | CodeReview | adapted from an outside developer's practice project (no license file in the original) | `servers/code_review/` |
| ruff, Bandit | CodeReview | MIT, Apache-2.0 | pip |
| sentence-transformers, transformers, torch, faiss-cpu, rank-bm25, FastAPI, uvicorn | ServiceQA | Apache-2.0, Apache-2.0, BSD-3-Clause, MIT, Apache-2.0, MIT, BSD-3-Clause | pip |
| awesome-llm-apps (Shubhamsaboo), apps `hybrid_search_rag`, `chat_with_pdf`, `ai_audio_tour_agent` | HybridSearch, ChatWithPDF, AudioTour | Apache-2.0 | fetched by each workload's `fetch_upstream.sh` |
| RAGLite, rerankers / FlashRank, embedchain, Streamlit, OpenAI Agents SDK | HybridSearch, ChatWithPDF, AudioTour | see each package | pip (versions in `requirements.txt`) |
| IOPaint 1.6.0 (Sanster) | IOPaint | Apache-2.0 | fetched by `servers/iopaint/setup.sh` |

## Models

| Model | Used by | License |
|---|---|---|
| Stable Diffusion v1.5 (`v1-5-pruned-emaonly`) | HeadFashion | CreativeML OpenRAIL-M |
| SAM ViT-H (`sam_vit_h_4b8939`) | HeadFashion, ImageBlur, SegmentOCR | Apache-2.0 |
| GroundingDINO SwinT-OGC | HeadFashion, ImageBlur, SegmentOCR | Apache-2.0 |
| BLIP base caption, CLIP ViT-L/14 | CaptionCompare | BSD-3-Clause, MIT |
| ESRGAN_4x | SegmentOCR | not stated for the file (release asset of cszn/KAIR, MIT; ESRGAN project Apache-2.0) |
| PP-OCRv4 server detection and recognition (ONNX) | SegmentOCR | Apache-2.0 |
| all-MiniLM-L6-v2, ms-marco-MiniLM-L-6-v2 cross-encoder, Qwen2.5-1.5B-Instruct | ServiceQA | Apache-2.0 |
| LaMa (big-lama), SAM 2.1 Hiera tiny, Real-ESRGAN realesr-general-x4v3 | IOPaint | Apache-2.0, Apache-2.0, BSD-3-Clause |
| OpenAI hosted models (embeddings, chat, web search, text-to-speech) | HybridSearch, ChatWithPDF, AudioTour | OpenAI terms of use |

## Data

| Dataset | Used by | License or terms |
|---|---|---|
| Open Images V7 (validation and test subsets, V5 boxes) | HeadFashion | annotations CC BY 4.0; images CC BY 2.0 (per-image URL in the manifest) |
| COCO 2017 val | CaptionCompare, ImageBlur, IOPaint | annotations CC BY 4.0; images under per-image Flickr Creative Commons licenses (recorded per row; many are NonCommercial or NoDerivs) |
| OpenALPR benchmarks `endtoend/us` | SegmentOCR | AGPL-3.0 (repository license; no separate image license stated). Blurred copies are generated locally. |
| CPython 3.9.6 standard library | CodeReview | PSF-2.0 |
| MS MARCO v2.1 | ServiceQA | MS MARCO terms: non-commercial research use only. Query texts are not stored in the manifests; `prepare_data.py` extracts them. |
| QASPER | HybridSearch, ChatWithPDF | CC BY 4.0 |
| arXiv articles (PDF) | HybridSearch, ChatWithPDF | each article's arXiv license; downloaded from arXiv, not redistributed |
| UNESCO World Heritage List via Wikidata (P757) | AudioTour | CC0 1.0 |
