# -*- coding: utf-8 -*-
"""gen_backend.py -- generation backends for the generator service.

  * QwenBackend     -- Qwen/Qwen2.5-1.5B-Instruct (revision pinned below) via
                       transformers; greedy decoding; float16 with
                       device_map="auto" when CUDA is available, float32 on CPU
                       otherwise. Loaded once per process on first use; calls to
                       model.generate are serialized by a lock. This is the
                       backend of the reference runs.
  * TemplateBackend -- deterministic stand-in with a fixed sleep, for checking
                       the plumbing without a model. Not for measurements.

Selected with RAG_GEN_BACKEND = "qwen" (default) | "template".
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict


class TemplateBackend:
    name = "template"

    def __init__(self, sleep_ms: int = 200) -> None:
        self.sleep_ms = sleep_ms

    def generate(self, prompt: str, *, max_new_tokens: int = 128) -> Dict[str, Any]:
        time.sleep(self.sleep_ms / 1000.0)
        answer = f"[template] answered based on {prompt[:120].splitlines()[0]}"
        return {"answer": answer, "tokens_in": len(prompt.split()), "tokens_out": len(answer.split()),
                "cancelled": False}


class QwenBackend:
    name = "qwen"
    MODEL_ID = os.environ.get("RAG_QWEN_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    MODEL_REVISION = os.environ.get("RAG_QWEN_REVISION", "989aa7980e4cf806f80c7fef2b1adb7bc71aa306")

    _model = None
    _tokenizer = None
    _load_lock = threading.Lock()
    _gen_lock = threading.Lock()  # one generate() at a time on the device

    def _ensure_loaded(self) -> None:
        if QwenBackend._model is not None:
            return
        with QwenBackend._load_lock:
            if QwenBackend._model is not None:
                return
            import torch  # noqa: WPS433
            from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: WPS433

            rev = self.MODEL_REVISION or None
            tok = AutoTokenizer.from_pretrained(self.MODEL_ID, revision=rev)
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            model = AutoModelForCausalLM.from_pretrained(
                self.MODEL_ID,
                revision=rev,
                torch_dtype=dtype,
                device_map="auto" if torch.cuda.is_available() else None,
            )
            model.eval()
            QwenBackend._tokenizer = tok
            QwenBackend._model = model

    def generate(self, prompt: str, *, max_new_tokens: int = 128) -> Dict[str, Any]:
        self._ensure_loaded()
        import torch  # noqa: WPS433

        tok = QwenBackend._tokenizer
        model = QwenBackend._model
        messages = [{"role": "user", "content": prompt}]
        chat = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        enc = tok(chat, return_tensors="pt")
        if torch.cuda.is_available():
            enc = {k: v.to(model.device) for k, v in enc.items()}
        input_len = enc["input_ids"].shape[1]
        with QwenBackend._gen_lock, torch.no_grad():
            out = model.generate(
                **enc,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=1.0,
                pad_token_id=tok.eos_token_id,
            )
        gen_ids = out[0, input_len:]
        answer = tok.decode(gen_ids, skip_special_tokens=True)
        return {"answer": answer, "tokens_in": int(input_len), "tokens_out": int(gen_ids.shape[0]),
                "cancelled": False}


def get_backend(name: str):
    n = (name or "qwen").lower()
    if n == "qwen":
        return QwenBackend()
    if n == "template":
        return TemplateBackend(sleep_ms=int(os.environ.get("RAG_TEMPLATE_SLEEP_MS", "200")))
    raise ValueError(f"unknown backend {name!r}; expected 'qwen' or 'template'")
