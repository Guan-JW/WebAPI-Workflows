# ServiceQA input selection

Source: MS MARCO v2.1, dev split, as the Hugging Face file
`microsoft/ms_marco` `v2.1/validation-00000-of-00001.parquet` at revision
`a47ee7aae8d7d466ba15f9f0bfac3b3681087b3a`
(https://huggingface.co/datasets/microsoft/ms_marco/resolve/a47ee7aae8d7d466ba15f9f0bfac3b3681087b3a/v2.1/validation-00000-of-00001.parquet,
209 628 787 bytes, sha256 `a07a87f483e602f5812573bff45109e5cbd934773c1c364366f176dd791e44d7`,
101 093 rows). License: the MS MARCO terms and conditions
(microsoft.github.io/msmarco) allow non-commercial research use only and
extend no license; the Hugging Face card gives none. The manifests therefore
list query ids, parquet row indexes and sha256 values, not the query text;
`prepare_data.py` extracts the text.

A query's text is the parquet `query` field with surrounding whitespace
stripped; `sha256` is the sha256 of its UTF-8 bytes.

## Corpus (served, not a split)

`corpus/passages.jsonl`: the first 100 000 distinct passage texts in file
order (rows in order, each row's `passages.passage_text` list in order,
whitespace-stripped, empty texts skipped), numbered `p00000` to `p99999`,
each with `metadata = {"source": "ms_marco_v2.1_dev"}`. sha256
`f3dd62a7b8437aaec1044067a05634d8961c9d6acdb47cb2b623687787be148f`
(39 000 589 bytes). It is drawn from parquet rows 0 to 10 214 (the last row
contributes only part of its passages).

## Duplicates are part of every split

Each split has 60 units: 50 distinct questions and 10 byte-exact repeats of
10 of them (`is_duplicate: true`, `dup_of` = the input_id of the original in
the same split). A repeated question is a separate unit with its own
input_id and the same sha256.

## profiling (60)

A fixed set chosen before the test splits existed: the first 50 distinct
non-empty query texts in parquet row order (`old_q0000` ... `old_q0049`),
plus 10 repeats `old_d0000` ... `old_d0009`, where `old_d000k` repeats query
number `random.Random(42).sample(range(50), 10)[k]`. `msmarco_query_id`,
`parquet_row_idx` and `query_type` of these rows were added for the release
(first row with that text); in SRC their `dup_of` held the query number
(`q0040`), here it holds the input_id (`old_q0040`).

## test (60) and test2 (60)

Seed 20261030. Pool: parquet rows whose every passage text (stripped) is in
the 100k corpus, whose query text is non-empty, not one of the 50 profiling
texts and not equal to the text of an earlier eligible row. 10 214 rows have
all passages in the corpus; 50 of them are profiling queries; 10 164 are
eligible.

1. Sort the eligible MS MARCO query ids as strings and shuffle them with
   `random.Random(20261030).shuffle`. The first 75 are the test candidates,
   the next 75 the test2 candidates.
2. Every candidate was run once through the baseline workflow and kept if all
   five calls return 200, the reranker returns at least one passage and the
   answer is non-empty. All 150 passed. The first 50 candidates of each list
   (by `order_idx`) were kept.
3. Ten of the 50 are repeated: `random.Random(20261030 + 1).sample(range(50), 10)`
   for test and `random.Random(20261030 + 2)` for test2, in manifest order;
   the j-th pick is appended as `dup{j:02d}_of_<input_id>`.

`n_passages` / `n_passages_in_corpus` give the number of passages of the
MS MARCO record and how many are in the corpus (always equal here). In SRC
the test split was called `test1`. Splits share no query text.
