from __future__ import annotations

"""JSONL request logging for the FastAPI gateway.

The middleware is implemented as plain ASGI instead of Starlette's
BaseHTTPMiddleware. Plain ASGI middleware is simple, avoids test shutdown edge
cases, and is enough for logging method/path/status/latency.
"""

import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from mini_rag.config import Settings
from mini_rag.utils import ensure_dir

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class RequestLoggerMiddleware:
    """Write one JSON line per HTTP request.

    Notes:
    - We do not log request bodies to avoid leaking user questions or secrets.
    - ``X-Request-Id`` is returned for every HTTP response.
    - Agent internals are still recorded separately in trace JSON files.
    """

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]], settings: Settings):
        self.app = app
        self.settings = settings
        self.log_path = Path(settings.request_log_path)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or f"req_{uuid4().hex}"
        started = time.perf_counter()
        status_code = 500
        error: str | None = None

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
                raw_headers = list(message.get("headers") or [])
                raw_headers.append((b"x-request-id", request_id.encode("latin1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            client = scope.get("client") or (None, None)
            self._write_line(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "client": client[0],
                    "error": error,
                }
            )

    def _write_line(self, payload: dict[str, Any]) -> None:
        ensure_dir(self.log_path.parent)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
