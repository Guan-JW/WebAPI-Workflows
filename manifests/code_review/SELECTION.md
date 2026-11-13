# CodeReview input selection

All inputs are Python modules of the CPython 3.9.6 standard library
(PSF-2.0). `prepare_data.py` fetches them; every manifest row carries the
file's sha256.

Sources:

| source | URL | sha256 |
|---|---|---|
| CPython 3.9.6 source tarball | https://www.python.org/ftp/python/3.9.6/Python-3.9.6.tgz | `d0a35182e19e416fc8eae25a3dcd4d02d4997333e4ad1f2eee6010aadc3fe866` |
| `Lib/mailcap.py` at CPython tag v3.9.16 (commit `595f9ccb0c059f2fb5bf13643bfc0cdd5b55a422`) | https://raw.githubusercontent.com/python/cpython/595f9ccb0c059f2fb5bf13643bfc0cdd5b55a422/Lib/mailcap.py | `b0ce7d29e8233ec412ac6aa16a9e62b3353d4acd44c6b870f6b6ffe1dbebba6f` |

LOC below means non-blank lines that do not start with `#` (after stripping
whitespace). Splits do not share any file (checked by sha256 and input_id).

## profiling (35 files)

A fixed set chosen before the test splits existed. It was drawn from the
Python 3.9.6 standard library shipped with Apple's Command Line Tools:

1. top-level `Lib/*.py`, sorted by path, without `antigravity.py`, `this.py`
   and `__phello__.foo.py`;
2. keep files with LOC in [50, 300];
3. LOC buckets 50-120, 121-220, 221-300 get 12, 12 and 11 files, drawn with
   `random.Random(42).sample(pool, n)`, one generator used for the three
   buckets in that order.

Applying the same rule to `Lib/` of the python.org 3.9.6 tarball selects the
same 35 file names. 34 of the files are byte-identical to the tarball. Apple's
`mailcap.py` carries a backport of the CVE-2015-20107 fix; it is
byte-identical to `Lib/mailcap.py` at CPython v3.9.16, which is where
`prepare_data.py` fetches it from. `loc_manifest_old` is the LOC recorded when
the set was first drawn (equal to `loc` for every row).

## test (20 files) and test2 (15 files)

Seed 20261030. Pool: CPython 3.9.6 `Lib/` from the tarball, LOC in [50, 300].
Excluded at the top level: the 35 profiling files, 14 file names the original
author of the pipeline used as inputs (`branchy_guard_wrong.py`,
`clean_small.py`, `empty.py`, `large_clean.py`, `lint_only.py`, `mixed.py`,
`security_only.py`, `subtle_security.py`, `ast.py`, `dataclasses.py`,
`difflib.py`, `functools.py`, `inspect.py`, `pathlib.py`) and the three files
skipped for profiling. Excluded below the top level: everything under
`Lib/encodings/` (machine-generated codec tables) and every path with a
directory named `test`, `tests`, `idle_test` or starting with `test`.
Eligible pool: 244 files (33 top-level, 211 in sub-packages).

1. Per LOC bucket (50-120, 121-220, 221-300, index i = 0, 1, 2), order the
   bucket's files as: top-level modules sorted by name and shuffled with
   `random.Random(20261030 + i)`, followed by sub-package modules sorted by
   dotted name and shuffled with `random.Random(20261030 + 100 + i)`.
2. Candidate lists of 30 (test) and 23 (test2) files are allocated over the
   buckets in the proportion 12/12/11 (largest remainder, capped by bucket
   size): test 10/10/10, test2 8/8/7. Each bucket's ordered list is consumed
   front to back, test first, then test2.
3. Every candidate was run once through the baseline workflow; a candidate is
   kept if all five calls return 200 and `/summarize` returns an `action`. All
   candidates passed. The first 20 (test) and 15 (test2) candidates in
   `order_idx` order were kept.

Candidates are numbered bucket by bucket, so step 3 keeps the two smaller
buckets and drops the 221-300 bucket entirely. Resulting LOC buckets
(50-120 / 121-220 / 221-300): profiling 12/12/11, test 10/10/0, test2 8/7/0.
The test splits therefore contain no file above 220 LOC.

`tier` says whether a file is a top-level module or in a sub-package;
`loc_bucket` is its bucket. `apple_clt_differs` is true when Apple's copy of
that file differs from the tarball (one test2 file, `linecache.py`); the
benchmark uses the tarball's bytes. `ge_10kb` marks files of 10 KB or more
(information only). In SRC the test split was called `test1`.

Candidates not kept (passed, not needed):

- test: `numbers`, `types`, `importlib.util`, `cgitb`, `distutils.command.config`,
  `idlelib.replace`, `xml.dom.pulldom`, `multiprocessing.queues`,
  `distutils.command.build_py`, `lib2to3.main` (order_idx 20-29).
- test2: `uu`, `multiprocessing.forkserver`, `xml.etree.ElementPath`,
  `tkinter.dnd`, `distutils.cygwinccompiler`, `xml.sax.saxutils`,
  `xml.dom.xmlbuilder`, `idlelib.debugger_r` (order_idx 15-22).
