# ChatWithPDF inputs: selection

**Source.** QASPER (`allenai/qasper`, CC BY 4.0) at revision
`fdc9d8214fbab5dd782958601db4d678e6934a54`. The validation and test splits were read in pages of 100
rows from the Hugging Face datasets-server rows API on 2026-11-03. PDFs come from
`https://arxiv.org/pdf/<arxiv_id>`.

**Rule.** Fixed before any run, seed `20261103`:
- `profiling`: QASPER validation split. Row indices are shuffled with `random.Random(20261103)`;
  take the first 2 documents that have at least 3 questions and whose arXiv PDF downloads.
- `test`: QASPER test split without rows 0-9 (HybridSearch uses those). Shuffle the same way and take
  the first 10 documents that have at least 3 questions and whose PDF downloads.
- questions: the first 4 questions of each document in dataset order, or all 3 if it has 3.

Result: profiling 2 documents / 8 questions (1904.07904, 1910.03634); test 10 documents /
37 questions (1908.09283, 1801.05617, 1909.12208, 2003.07459, 1703.04009, 1711.03759, 1911.01214,
1610.06510, 1912.07940, 1807.08089). No PDF download failed, so nothing was skipped. The splits share
no document.

**Check (2026-11-12).** `prepare_data.py --verify-questions` found the revision still current. All
45 question ids and texts were unchanged, and all 12 PDFs matched their sha256.

**Fields.** `input_id` is the QASPER question id and `arxiv_id` is QASPER's document id. `q_index`
is the question's position within its document session, starting at 0. `dataset_split` and
`dataset_row_idx` locate the QASPER row. `file` is relative to `data/chat_with_pdf/`, and `sha256`
and `pdf_bytes` describe that PDF.
