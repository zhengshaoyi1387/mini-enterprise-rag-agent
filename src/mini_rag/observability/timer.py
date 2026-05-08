from __future__ import annotations

import time
from types import TracebackType
from typing import Any


class Timer:
    """简单计时器，用于记录代码块耗时。

    使用方式：

    trace = {}
    with Timer(trace, "retrieval"):
        docs = retriever.search(query)

    结束后 trace 里会出现：
    retrieval_latency_ms: 123.45
    """

    def __init__(self, trace: dict[str, Any], name: str):
        self.trace = trace
        self.name = name
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        self.trace[f"{self.name}_latency_ms"] = round(elapsed_ms, 2)
