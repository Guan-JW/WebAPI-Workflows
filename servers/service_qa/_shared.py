# -*- coding: utf-8 -*-
"""Helpers shared by the five question-answering services."""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def corpus_dir() -> str:
    """Directory with passages.jsonl (and passages.npy for the vector index).

    RAG_CORPUS_DIR, else $WBENCH_DATA/service_qa/corpus, else <repo>/data/service_qa/corpus.
    """
    if os.environ.get("RAG_CORPUS_DIR"):
        return os.environ["RAG_CORPUS_DIR"]
    data = os.environ.get("WBENCH_DATA", os.path.join(REPO_ROOT, "data"))
    return os.path.join(data, "service_qa", "corpus")


class BaseReq(BaseModel):
    """The client sends a per-question ``trace_id`` and a step name ``node_id``
    with every request. The services accept and ignore both."""

    trace_id: Optional[str] = None
    node_id: Optional[str] = None
