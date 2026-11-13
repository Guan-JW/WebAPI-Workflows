# HybridSearch inputs: selection

**Source.** QASPER (`allenai/qasper`, CC BY 4.0), test split, served by the Hugging Face
datasets-server rows API (`dataset=allenai/qasper&config=qasper&split=test&offset=0&length=10`),
retrieved 2026-11-01. The saved page had sha256
`16c6731a7ba0c9f0b746a0c98ce4bc1287278fd1e0903d97cde6449d636569a1`.

**Rule.** No sampling and no seed:
- documents: test rows 0-9, in row order;
- questions: every question of those documents, in dataset order (30 questions);
- `profiling`: the first 5 questions in that order (4 from 1911.10742, 1 from 1904.09131);
- `test`: the remaining 25 (documents 1611.06322 to 2003.13016).

No question is in both splits, and no document has questions in both splits. All 10 documents are
in the one index that every question searches (`workloads/hybrid_search/build_index.py`).

**Revision.** The 2026-11-01 download did not record a dataset revision. Rows 0-9 of that page are
identical to rows 0-9 of the test split downloaded on 2026-11-03, which recorded revision
`fdc9d8214fbab5dd782958601db4d678e6934a54` (ChatWithPDF's inputs). On 2026-11-12,
`prepare_data.py --verify-questions` found that revision still current and all 30 question ids and
texts unchanged.

**PDFs.** `https://arxiv.org/pdf/<arxiv_id>` (no version suffix). The manifest pins each file's
sha256 and size. On 2026-11-12 all 10 downloads matched.

**Fields.** `input_id` is the QASPER question id. `arxiv_id` is QASPER's document id, `q_index` is
the question's position in the document's question list, and `manifest_index` is the position in the
30-question list above. `dataset_row_idx` is the row in the test split. `file` is relative to
`data/hybrid_search/`; `sha256` and `pdf_bytes` describe that PDF.
