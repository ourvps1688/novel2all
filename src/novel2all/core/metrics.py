"""V1.0 GA Day 11-15：Prometheus 风格 metrics。

设计：
- Counter / Gauge / Histogram 三种 metric
- 线程安全（threading.Lock）
- 零外部依赖（纯 stdlib）
- 导出 /metrics 端点（Prometheus scrape format）

集成：
- LLM 调用次数（按 model / task 维度）
- Cache hits / misses（按 backend 维度）
- HTTP 请求计数（按 path / status 维度）
- 章节写作（verdict pass / warn / fail）
- AdaptiveRouter 模型选择
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# === Metric types ===


class Counter:
    """V1.0 GA：单调递增计数器（label 字典）。"""

    def __init__(self, name: str, help_text: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.labelnames = labelnames
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """V1.0 GA：递增计数器。"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> list[tuple[dict[str, str], float]]:
        """V1.0 GA：收集所有 label 组合。"""
        with self._lock:
            return [(dict(key), value) for key, value in self._values.items()]


class Gauge:
    """V1.0 GA：可增可减的瞬时值。"""

    def __init__(self, name: str, help_text: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.labelnames = labelnames
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        """V1.0 GA：设置瞬时值。"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """V1.0 GA：递增。"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        """V1.0 GA：递减。"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def collect(self) -> list[tuple[dict[str, str], float]]:
        with self._lock:
            return [(dict(key), value) for key, value in self._values.items()]


@dataclass
class Histogram:
    """V1.0 GA：直方图（bucket 计数）。"""

    name: str
    help_text: str
    buckets: tuple[float, ...] = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        float("inf"),
    )
    _counts: dict[tuple[tuple[str, str], ...], list[int]] = field(default_factory=dict)
    _sums: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, **labels: str) -> None:
        """V1.0 GA：记录观测值。"""
        key = tuple(sorted(labels.items()))
        with self._lock:
            if key not in self._counts:
                self._counts[key] = [0] * len(self.buckets)
                self._sums[key] = 0.0
            for i, bucket in enumerate(self.buckets):
                if value <= bucket:
                    self._counts[key][i] += 1
            self._sums[key] += value

    def collect(self) -> list[dict[str, Any]]:
        """V1.0 GA：收集所有 buckets + sum + count。"""
        with self._lock:
            result = []
            for key, counts in self._counts.items():
                for i, bucket in enumerate(self.buckets):
                    result.append(
                        {
                            "labels": dict(key),
                            "le": bucket if bucket != float("inf") else "+Inf",
                            "count": counts[i],
                        }
                    )
                # +Inf bucket + sum + count
                result.append(
                    {
                        "labels": dict(key),
                        "le": "+Inf",
                        "count": counts[-1],
                    }
                )
            for key, total_sum in self._sums.items():
                result.append(
                    {
                        "labels": dict(key),
                        "_sum": total_sum,
                    }
                )
                result.append(
                    {
                        "labels": dict(key),
                        "_count": self._counts[key][-1],
                    }
                )
            return result


# === Global registry ===


class MetricsRegistry:
    """V1.0 GA：全局 metrics 注册表。"""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, help_text: str, labelnames: tuple[str, ...] = ()) -> Counter:
        """V1.0 GA：注册或获取 Counter。"""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, help_text, labelnames)
            return self._counters[name]

    def gauge(self, name: str, help_text: str, labelnames: tuple[str, ...] = ()) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, help_text, labelnames)
            return self._gauges[name]

    def histogram(
        self, name: str, help_text: str, buckets: tuple[float, ...] | None = None
    ) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                if buckets:
                    self._histograms[name] = Histogram(
                        name=name, help_text=help_text, buckets=buckets
                    )
                else:
                    self._histograms[name] = Histogram(name=name, help_text=help_text)
            return self._histograms[name]

    def export_prometheus(self) -> str:
        """V1.0 GA：导出 Prometheus text format。"""
        lines = []
        with self._lock:
            for name, counter in self._counters.items():
                lines.append(f"# HELP {name} {counter.help_text}")
                lines.append(f"# TYPE {name} counter")
                for labels, value in counter.collect():
                    label_str = self._format_labels(labels) if labels else ""
                    lines.append(f"{name}{label_str} {value}")
            for name, gauge in self._gauges.items():
                lines.append(f"# HELP {name} {gauge.help_text}")
                lines.append(f"# TYPE {name} gauge")
                for labels, value in gauge.collect():
                    label_str = self._format_labels(labels) if labels else ""
                    lines.append(f"{name}{label_str} {value}")
            for name, hist in self._histograms.items():
                lines.append(f"# HELP {name} {hist.help_text}")
                lines.append(f"# TYPE {name} histogram")
                # Buckets
                bucket_data: dict[tuple, list[tuple[str, int]]] = defaultdict(list)
                sums: dict[tuple, float] = {}
                counts: dict[tuple, int] = {}
                for entry in hist.collect():
                    key = tuple(sorted(entry["labels"].items()))
                    if "le" in entry:
                        bucket_data[key].append((entry["le"], entry["count"]))
                    elif "_sum" in entry:
                        sums[key] = entry["_sum"]
                    elif "_count" in entry:
                        counts[key] = entry["_count"]
                for key, buckets in bucket_data.items():
                    label_str = self._format_labels(dict(key)) if key else ""
                    for le, count in buckets:
                        le_label = f'le="{le}"'
                        if label_str:
                            # Insert le at the right place
                            le_label = le_label + (
                                "," if label_str and not label_str.endswith(",") else ""
                            )
                            lines.append(
                                f"{name}_bucket{{{le_label}{label_str.lstrip('{').rstrip('}')}}} {count}"
                            )
                        else:
                            lines.append(f"{name}_bucket{{{le_label}}} {count}")
                    # _sum / _count
                    if key in sums:
                        lines.append(f"{name}_sum{label_str} {sums[key]}")
                    if key in counts:
                        lines.append(f"{name}_count{label_str} {counts[key]}")
        return "\n".join(lines)

    @staticmethod
    def _format_labels(labels: dict[str, str]) -> str:
        """V1.0 GA：格式化为 Prometheus label 字符串。"""
        if not labels:
            return ""
        parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return "{" + parts + "}"


# === Singleton ===

_REGISTRY: MetricsRegistry | None = None


def get_metrics_registry() -> MetricsRegistry:
    """V1.0 GA：获取全局 metrics 注册表（lazy init）。"""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = MetricsRegistry()
        # 注册预定义 metrics
        _REGISTRY.counter(
            "novel2all_llm_calls_total",
            "Total LLM API calls",
            ("model", "task", "status"),
        )
        _REGISTRY.counter(
            "novel2all_cache_operations_total",
            "Total cache operations",
            ("backend", "operation", "result"),
        )
        _REGISTRY.counter(
            "novel2all_chapter_writes_total",
            "Total chapter writes",
            ("verdict",),
        )
        _REGISTRY.counter(
            "novel2all_rollbacks_total",
            "Total critical auto-rollbacks",
            (),
        )
        _REGISTRY.histogram(
            "novel2all_llm_latency_seconds",
            "LLM call latency in seconds",
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, float("inf")),
        )
        _REGISTRY.gauge(
            "novel2all_active_sessions",
            "Number of active user sessions",
            (),
        )
    return _REGISTRY
