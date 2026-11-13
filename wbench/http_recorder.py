"""Count the HTTP requests a workflow makes, and the bytes each one moves.

The recorder patches ``requests.Session.send`` and ``httpx.Client.send`` /
``httpx.AsyncClient.send`` for the duration of a ``with`` block. Workflow code
is not modified. Byte counts are request and response bodies as sent and
received by the client library (after decompression for responses); headers
are not counted.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit


def now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class HttpCall:
    method: str
    url: str
    status: Optional[int]
    t_start_ms: float
    t_end_ms: float
    req_bytes: int
    resp_bytes: int
    error: Optional[str] = None
    req_body: Optional[bytes] = None
    resp_body: Optional[bytes] = None

    @property
    def latency_ms(self) -> float:
        return max(0.0, self.t_end_ms - self.t_start_ms)

    def host(self) -> str:
        return urlsplit(self.url).netloc

    def path(self) -> str:
        u = urlsplit(self.url)
        return u.path

    def req_json(self) -> Any:
        try:
            return json.loads(self.req_body.decode("utf-8")) if self.req_body is not None else None
        except Exception:  # noqa: BLE001
            return None

    def resp_json(self) -> Any:
        try:
            return json.loads(self.resp_body.decode("utf-8")) if self.resp_body is not None else None
        except Exception:  # noqa: BLE001
            return None

    def to_record(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "host": self.host(),
            "path": self.path(),
            "status": self.status,
            "latency_ms": round(self.latency_ms, 3),
            "req_bytes": self.req_bytes,
            "resp_bytes": self.resp_bytes,
            "error": self.error,
        }


def _body_bytes(body: Any) -> Optional[bytes]:
    if isinstance(body, str):
        return body.encode("utf-8", "ignore")
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return None


class HttpRecorder:
    """Thread-safe recorder of client-side HTTP calls.

    ``keep_bodies=True`` keeps raw bodies in memory, for workloads whose
    output check needs what crossed the wire.
    """

    def __init__(self, keep_bodies: bool = False) -> None:
        self.keep_bodies = keep_bodies
        self.calls: List[HttpCall] = []
        self._lock = threading.Lock()
        self._orig: Dict[str, Any] = {}
        self._installed = False

    # -- stats -------------------------------------------------------------
    def window(self, t0: float, t1: float) -> List[HttpCall]:
        """Calls that started inside [t0, t1]."""
        with self._lock:
            return [c for c in self.calls if t0 <= c.t_start_ms <= t1]

    def clear(self) -> None:
        with self._lock:
            self.calls = []

    def _add(self, call: HttpCall) -> None:
        with self._lock:
            self.calls.append(call)

    # -- install / uninstall ------------------------------------------------
    def __enter__(self) -> "HttpRecorder":
        self.install()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.uninstall()

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        rec = self

        try:
            import requests

            orig_send = requests.Session.send
            self._orig["requests"] = orig_send

            def send(self_s, request, **kwargs):  # type: ignore[no-untyped-def]
                body_b = _body_bytes(request.body)
                t0 = now_ms()
                status, err, content = None, None, b""
                try:
                    r = orig_send(self_s, request, **kwargs)
                    status = r.status_code
                    content = r.content or b""
                    return r
                except Exception as e:  # noqa: BLE001
                    err = repr(e)
                    raise
                finally:
                    rec._add(HttpCall(request.method or "?", request.url or "?", status, t0, now_ms(),
                                      len(body_b or b""), len(content), err,
                                      body_b if rec.keep_bodies else None,
                                      content if rec.keep_bodies else None))

            requests.Session.send = send  # type: ignore[assignment]
        except ImportError:
            pass

        for modname in ("httpx", "httpx2"):  # httpx2: used by recent openai releases
            self._install_httpx_like(modname)

    def _install_httpx_like(self, modname: str) -> None:
        import importlib

        rec = self
        try:
            httpx = importlib.import_module(modname)
        except ImportError:
            return
        orig_hsend = httpx.Client.send
        orig_asend = httpx.AsyncClient.send
        self._orig[modname] = orig_hsend
        self._orig[modname + "_async"] = orig_asend

        def _req_body(request) -> bytes:  # type: ignore[no-untyped-def]
            try:
                return bytes(request.content)
            except Exception:  # noqa: BLE001  (streaming body)
                return b""

        def hsend(self_c, request, **kwargs):  # type: ignore[no-untyped-def]
            body_b = _req_body(request)
            t0 = now_ms()
            status, err, n_in, content = None, None, 0, None
            try:
                r = orig_hsend(self_c, request, **kwargs)
                status = r.status_code
                if not kwargs.get("stream"):
                    content = r.content or b""
                    n_in = len(content)
                return r
            except Exception as e:  # noqa: BLE001
                err = repr(e)
                raise
            finally:
                rec._add(HttpCall(request.method, str(request.url), status, t0, now_ms(), len(body_b), n_in,
                                  err, body_b if rec.keep_bodies else None,
                                  content if rec.keep_bodies else None))

        async def asend(self_c, request, **kwargs):  # type: ignore[no-untyped-def]
            body_b = _req_body(request)
            t0 = now_ms()
            status, err, n_in, content = None, None, 0, None
            try:
                r = await orig_asend(self_c, request, **kwargs)
                status = r.status_code
                if not kwargs.get("stream"):
                    content = r.content or b""
                    n_in = len(content)
                return r
            except Exception as e:  # noqa: BLE001
                err = repr(e)
                raise
            finally:
                rec._add(HttpCall(request.method, str(request.url), status, t0, now_ms(), len(body_b), n_in,
                                  err, body_b if rec.keep_bodies else None,
                                  content if rec.keep_bodies else None))

        httpx.Client.send = hsend  # type: ignore[assignment]
        httpx.AsyncClient.send = asend  # type: ignore[assignment]

    def uninstall(self) -> None:
        if not self._installed:
            return
        self._installed = False
        if "requests" in self._orig:
            import requests

            requests.Session.send = self._orig["requests"]  # type: ignore[assignment]
        import importlib

        for modname in ("httpx", "httpx2"):
            if modname in self._orig:
                m = importlib.import_module(modname)
                m.Client.send = self._orig[modname]  # type: ignore[assignment]
                m.AsyncClient.send = self._orig[modname + "_async"]  # type: ignore[assignment]
        self._orig.clear()
