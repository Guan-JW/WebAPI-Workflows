# -*- coding: utf-8 -*-
"""Helpers shared by the four code review services.

  * BaseReq          -- request fields every service accepts (trace_id, node_id)
  * find_tool(name)  -- locate a CLI tool, preferring the running interpreter's bin/
  * run_subprocess() -- run a command and return (stdout, stderr, returncode)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from pydantic import BaseModel


class BaseReq(BaseModel):
    """The client sends a per-unit ``trace_id`` and a step name ``node_id``
    with every request. The services accept and ignore both."""

    trace_id: Optional[str] = None
    node_id: Optional[str] = None


def find_tool(name: str) -> str:
    """Locate a CLI tool, preferring the virtualenv that runs this process.

    Tools installed with ``pip install`` into a virtualenv land in the same
    ``bin`` directory as the interpreter, which is not always on PATH when a
    service is started with a bare ``python <service>.py``.
    """
    venv_candidate = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.isfile(venv_candidate) and os.access(venv_candidate, os.X_OK):
        return venv_candidate
    found = shutil.which(name)
    return found or name


def run_subprocess(cmd: list, *, input_text: Optional[str] = None, timeout: int = 30) -> Tuple[str, str, int]:
    """Run a command to completion and return (stdout, stderr, returncode)."""
    proc = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.stdout, proc.stderr, proc.returncode
