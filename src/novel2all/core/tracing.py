"""V1.0 GA Day 11-15：轻量 tracing（OTLP-like JSON export）。

设计：不强制依赖 opentelemetry-api（避免破坏现有架构）。
- 提供 Span / Trace 类，自包含
- 导出为 JSON（兼容 OTLP collector / Jaeger / Tempo）
- 线程安全
- 零外部依赖（仅 stdlib）

集成点（后续）：
- LLMProvider.complete / stream
- AdaptiveRouter.record_run
- Cache.get / set
- Web auth endpoints
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# === Constants ===

DEFAULT_LOG_PATH: ClassVar[Path] = Path(".novel2all/traces.jsonl")
MAX_IN_MEMORY_SPANS = 10000


# === Data Models ===


@dataclass
class Span:
    """V1.0 GA：单个 span（OTLP 兼容字段）。"""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time_ns: int
    end_time_ns: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok / error

    @property
    def duration_ms(self) -> float:
        return (self.end_time_ns - self.start_time_ns) / 1e6

    def to_otlp(self) -> dict[str, Any]:
        """V1.0 GA：导出 OTLP 兼容格式。"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time_unix_nano": self.start_time_ns,
            "end_time_unix_nano": self.end_time_ns,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
        }


# === Tracer ===


class Tracer:
    """V1.0 GA：全局 tracer（轻量，零外部依赖）。"""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = Path(log_path) if log_path else DEFAULT_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._spans: list[Span] = []
        self._active_spans: dict[str, str] = {}  # thread_id → span_id
        self._span_stacks: dict[str, list[str]] = defaultdict(list)  # thread_id → [span_id, ...]

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Any:
        """V1.0 GA：创建 span 上下文管理器。

        用法：
            with tracer.span("llm.call", model="deepseek") as span:
                result = await llm.complete(prompt)
                span.set_attribute("output_chars", len(result))
        """

        thread_id = str(threading.get_ident())
        with self._lock:
            stack = self._span_stacks[thread_id]
            if stack:
                # 嵌套 span：从栈顶取 (span_id, trace_id)
                parent_id, trace_id = stack[-1]
            else:
                # 顶层 span：新 trace_id
                trace_id = str(uuid.uuid4())
                parent_id = None
            span_id = str(uuid.uuid4())[:16]
            # push (span_id, trace_id) 到栈
            stack.append((span_id, trace_id))
            span = Span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_id,
                name=name,
                start_time_ns=time.time_ns(),
                attributes=attributes,
            )
        try:
            yield span
        except Exception as e:
            span.status = "error"
            span.attributes["error"] = str(e)
            raise
        finally:
            span.end_time_ns = time.time_ns()
            with self._lock:
                self._spans.append(span)
                # pop 栈顶（tuple）
                if self._span_stacks[thread_id]:
                    self._span_stacks[thread_id].pop()
                # 内存保护：超过上限时丢弃最老的
                if len(self._spans) > MAX_IN_MEMORY_SPANS:
                    self._spans = self._spans[-MAX_IN_MEMORY_SPANS:]
            # 异步 flush 到文件（避免阻塞主流程）
            self._flush(span)

    def _flush(self, span: Span) -> None:
        """V1.0 GA：flush span 到文件（每行 JSON）。"""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(span.to_otlp(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("V1.0 GA: trace flush failed: %s", e)

    def get_recent_spans(self, limit: int = 100) -> list[dict[str, Any]]:
        """V1.0 GA：取最近的 spans（用于 /api/debug/traces）。"""
        with self._lock:
            return [s.to_otlp() for s in self._spans[-limit:]]

    def get_stats(self) -> dict[str, Any]:
        """V1.0 GA：tracer 统计（用于 /api/debug/stats）。"""
        with self._lock:
            total = len(self._spans)
            if total == 0:
                return {"total_spans": 0, "by_name": {}, "errors": 0}
            by_name: dict[str, dict[str, Any]] = defaultdict(
                lambda: {"count": 0, "errors": 0, "total_ms": 0.0}
            )
            for s in self._spans:
                by_name[s.name]["count"] += 1
                by_name[s.name]["total_ms"] += s.duration_ms
                if s.status == "error":
                    by_name[s.name]["errors"] += 1
            return {
                "total_spans": total,
                "by_name": {
                    name: {
                        "count": data["count"],
                        "errors": data["errors"],
                        "avg_ms": round(data["total_ms"] / data["count"], 2),
                    }
                    for name, data in by_name.items()
                },
                "errors": sum(1 for s in self._spans if s.status == "error"),
            }


# === Global singleton ===

_TRACER: Tracer | None = None


def get_tracer() -> Tracer:
    """V1.0 GA：获取全局 tracer（lazy init）。"""
    global _TRACER
    if _TRACER is None:
        _TRACER = Tracer()
    return _TRACER
