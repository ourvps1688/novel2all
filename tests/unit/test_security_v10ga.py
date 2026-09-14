"""V1.0 GA Day 11-15：安全 + 监控测试。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from novel2all.core.audit import AuditStore
from novel2all.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics_registry,
)
from novel2all.core.security_headers import (
    DEFAULT_SECURITY_HEADERS,
    SecurityHeadersMiddleware,
    with_security_headers,
)
from novel2all.core.tracing import Tracer, get_tracer

# === Test 1: Audit Store ===


class TestAuditStore:
    """V1.0 GA：审计日志。"""

    def test_record_event(self, tmp_path: Path) -> None:
        """V1.0 GA：记录单个事件。"""
        store = AuditStore(db_path=tmp_path / "audit.db")
        store.record("login", user_id=1, username="alice", ip="127.0.0.1", success=True)
        events = store.query()
        assert len(events) == 1
        assert events[0]["event_type"] == "login"
        assert events[0]["username"] == "alice"

    def test_record_failure_event(self, tmp_path: Path) -> None:
        """V1.0 GA：记录失败事件。"""
        store = AuditStore(db_path=tmp_path / "audit.db")
        store.record(
            "login_failed", username="bob", ip="1.2.3.4", success=False, detail="Invalid password"
        )
        events = store.query()
        assert len(events) == 1
        assert events[0]["success"] is False
        assert events[0]["detail"] == "Invalid password"

    def test_query_by_event_type(self, tmp_path: Path) -> None:
        """V1.0 GA：按 event_type 过滤。"""
        store = AuditStore(db_path=tmp_path / "audit.db")
        store.record("login", user_id=1, success=True)
        store.record("logout", user_id=1, success=True)
        store.record("login_failed", username="x", success=False)

        login_events = store.query(event_type="login")
        assert len(login_events) == 1
        assert login_events[0]["event_type"] == "login"

    def test_query_by_user(self, tmp_path: Path) -> None:
        """V1.0 GA：按 user_id 过滤。"""
        store = AuditStore(db_path=tmp_path / "audit.db")
        store.record("login", user_id=1, success=True)
        store.record("login", user_id=2, success=True)
        store.record("login", user_id=3, success=True)

        events = store.query(user_id=2)
        assert len(events) == 1
        assert events[0]["user_id"] == 2

    def test_cleanup_old(self, tmp_path: Path) -> None:
        """V1.0 GA：清理 90 天前事件。"""
        import sqlite3

        store = AuditStore(db_path=tmp_path / "audit.db")
        store.record("login", user_id=1, success=True)
        # 手动改时间戳为 100 天前
        with sqlite3.connect(str(tmp_path / "audit.db")) as conn:
            conn.execute("UPDATE audit_events SET timestamp = ?", (time.time() - 100 * 86400,))
        deleted = store.cleanup_old(max_age_seconds=90 * 86400)
        assert deleted == 1

    def test_record_thread_safe(self, tmp_path: Path) -> None:
        """V1.0 GA：threading.Lock 保护并发写。"""
        import threading

        store = AuditStore(db_path=tmp_path / "audit.db")

        def record(i: int) -> None:
            for _ in range(10):
                store.record("login", user_id=i, success=True)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 5 * 10 = 50 events
        events = store.query(limit=100)
        assert len(events) == 50


# === Test 2: Tracing ===


class TestTracing:
    """V1.0 GA：轻量 tracing。"""

    def test_span_basic(self, tmp_path: Path) -> None:
        """V1.0 GA：基础 span 创建。"""
        tracer = Tracer(log_path=tmp_path / "traces.jsonl")
        with tracer.span("test_op", key="value") as span:
            span.attributes["custom"] = "data"
        # Span 已结束
        assert span.end_time_ns > 0
        assert span.duration_ms >= 0
        assert span.status == "ok"

    def test_span_records_exception(self, tmp_path: Path) -> None:
        """V1.0 GA：异常 span status=error。"""
        tracer = Tracer(log_path=tmp_path / "traces.jsonl")
        with pytest.raises(ValueError):
            with tracer.span("failing_op") as span:
                raise ValueError("test error")
        assert span.status == "error"
        assert "test error" in span.attributes["error"]

    def test_span_nested(self, tmp_path: Path) -> None:
        """V1.0 GA：嵌套 span（parent_span_id 正确）。"""
        tracer = Tracer(log_path=tmp_path / "traces.jsonl")
        with tracer.span("parent") as parent:
            with tracer.span("child") as child:
                pass
        assert child.parent_span_id == parent.span_id
        assert child.trace_id == parent.trace_id

    def test_span_persisted_to_file(self, tmp_path: Path) -> None:
        """V1.0 GA：span 持久化到 JSONL 文件。"""
        log_path = tmp_path / "traces.jsonl"
        tracer = Tracer(log_path=log_path)
        with tracer.span("test") as span:
            span.attributes["foo"] = "bar"
        content = log_path.read_text(encoding="utf-8")
        assert "test" in content
        assert "foo" in content
        assert "bar" in content

    def test_get_recent_spans(self, tmp_path: Path) -> None:
        """V1.0 GA：获取最近 spans。"""
        tracer = Tracer(log_path=tmp_path / "traces.jsonl")
        for i in range(5):
            with tracer.span(f"op_{i}"):
                pass
        recent = tracer.get_recent_spans(limit=3)
        assert len(recent) == 3

    def test_get_stats(self, tmp_path: Path) -> None:
        """V1.0 GA：tracer 统计（按 name 分组）。"""
        tracer = Tracer(log_path=tmp_path / "traces.jsonl")
        for _ in range(3):
            with tracer.span("op1"):
                pass
        with pytest.raises(ValueError):
            with tracer.span("op2"):
                raise ValueError("err")
        stats = tracer.get_stats()
        assert stats["total_spans"] == 4
        assert stats["by_name"]["op1"]["count"] == 3
        assert stats["by_name"]["op2"]["errors"] == 1

    def test_singleton_tracer(self) -> None:
        """V1.0 GA：get_tracer 返回 singleton。"""
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2


# === Test 3: Security Headers ===


class TestSecurityHeaders:
    """V1.0 GA：安全 headers。"""

    def test_default_headers_complete(self) -> None:
        """V1.0 GA：默认 headers 包含所有 OWASP 关键项。"""
        assert "X-Content-Type-Options" in DEFAULT_SECURITY_HEADERS
        assert "X-Frame-Options" in DEFAULT_SECURITY_HEADERS
        assert "Referrer-Policy" in DEFAULT_SECURITY_HEADERS
        assert "Permissions-Policy" in DEFAULT_SECURITY_HEADERS
        assert "Content-Security-Policy" in DEFAULT_SECURITY_HEADERS

    def test_csp_includes_self(self) -> None:
        """V1.0 GA：CSP default-src 'self'。"""
        csp = DEFAULT_SECURITY_HEADERS["Content-Security-Policy"]
        assert "default-src 'self'" in csp

    def test_csp_blocks_inline_scripts(self) -> None:
        """V1.0 GA：CSP script-src 'self'（无 unsafe-inline）。"""
        csp = DEFAULT_SECURITY_HEADERS["Content-Security-Policy"]
        assert "script-src 'self'" in csp
        # 但允许 Alpine.js inline styles
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_with_security_headers(self) -> None:
        """V1.0 GA：直接添加 headers 到 Response。"""
        from starlette.responses import JSONResponse

        response = JSONResponse({"ok": True})
        with_security_headers(response)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_middleware_class_instantiation(self) -> None:
        """V1.0 GA：SecurityHeadersMiddleware 可实例化。"""
        from starlette.applications import Starlette

        app = Starlette()
        mw = SecurityHeadersMiddleware(app)
        assert mw is not None


# === Test 4: Metrics ===


class TestMetrics:
    """V1.0 GA：Prometheus 风格 metrics。"""

    def test_counter_increment(self) -> None:
        """V1.0 GA：Counter 递增。"""
        c = Counter("test", "test counter", ("model",))
        c.inc(model="m1")
        c.inc(amount=5, model="m1")
        results = c.collect()
        assert len(results) == 1
        assert results[0][1] == 6.0

    def test_counter_with_multiple_labels(self) -> None:
        """V1.0 GA：Counter 多 label 组合。"""
        c = Counter("test", "", ("model", "status"))
        c.inc(model="m1", status="ok")
        c.inc(model="m1", status="ok")
        c.inc(model="m2", status="error")
        results = c.collect()
        assert len(results) == 2

    def test_gauge_set_inc_dec(self) -> None:
        """V1.0 GA：Gauge set / inc / dec。"""
        g = Gauge("active", "")
        g.set(10)
        assert g.collect()[0][1] == 10
        g.inc(5)
        assert g.collect()[0][1] == 15
        g.dec(3)
        assert g.collect()[0][1] == 12

    def test_histogram_observe(self) -> None:
        """V1.0 GA：Histogram 观测。"""
        h = Histogram("latency", "", buckets=(0.1, 0.5, 1.0, float("inf")))
        h.observe(0.05)
        h.observe(0.3)
        h.observe(2.0)
        results = h.collect()
        # Should have bucket counts + sum + count
        assert any("le" in r for r in results)

    def test_registry_export_prometheus(self) -> None:
        """V1.0 GA：导出 Prometheus 格式。"""
        reg = MetricsRegistry()
        c = reg.counter("my_counter", "test counter")
        c.inc(amount=3)
        output = reg.export_prometheus()
        assert "# HELP my_counter test counter" in output
        assert "# TYPE my_counter counter" in output
        assert "my_counter 3.0" in output

    def test_registry_export_with_labels(self) -> None:
        """V1.0 GA：带 label 导出。"""
        reg = MetricsRegistry()
        c = reg.counter("labeled", "test", ("model",))
        c.inc(model="deepseek-flash")
        c.inc(model="gpt-4")
        output = reg.export_prometheus()
        assert 'model="deepseek-flash"' in output
        assert 'model="gpt-4"' in output

    def test_global_registry_has_preset_metrics(self) -> None:
        """V1.0 GA：全局注册表有预定义 metrics。"""
        reg = get_metrics_registry()
        assert "novel2all_llm_calls_total" in reg._counters
        assert "novel2all_cache_operations_total" in reg._counters
        assert "novel2all_chapter_writes_total" in reg._counters
        assert "novel2all_rollbacks_total" in reg._counters
        assert "novel2all_llm_latency_seconds" in reg._histograms
        assert "novel2all_active_sessions" in reg._gauges

    def test_metrics_registry_singleton(self) -> None:
        """V1.0 GA：get_metrics_registry 返回同一实例。"""
        r1 = get_metrics_registry()
        r2 = get_metrics_registry()
        assert r1 is r2


# === Test 5: Integration（DB 调优应用到 audit） ===


class TestAuditDbTuning:
    """V1.0 GA：AuditStore SQLite 应用 PRAGMA 调优。"""

    def test_audit_db_uses_wal(self, tmp_path: Path) -> None:
        """V1.0 GA：AuditStore 用 WAL 模式。"""
        AuditStore(db_path=tmp_path / "audit.db")
        import sqlite3

        with sqlite3.connect(str(tmp_path / "audit.db")) as conn:
            cur = conn.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
            assert mode == "wal"
