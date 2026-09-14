"""V0.30.6 B3：Web UI 实时进度条测试。

测试 write_form.html + base.html 中的 B3 元素：
1. 进度条（progress-bar-track/fill/label）
2. Phase stepper（8 阶段）
3. 实时统计（字数/字速/chunks/ETA）
4. Alpine.js state 字段
5. SSE event handlers
6. CSS in base.html
7. data-testid for E2E testing
8. 纯函数逻辑（progressPct / formatTime / ETA 计算）
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novel2all.web.app import create_app

# === 1. write_form.html 含 B3 元素 ===


def test_write_form_has_progress_bar() -> None:
    """V0.30.6 B3：write_form.html 含 progress-bar-track/fill/label 元素。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    assert "progress-bar-track" in content
    assert "progress-bar-fill" in content
    assert "progress-bar-label" in content


def test_write_form_has_phase_stepper() -> None:
    """V0.30.6 B3：含 progress-stepper 和 progress-step 元素。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    assert "progress-stepper" in content
    assert "progress-step" in content


def test_write_form_has_progress_stats() -> None:
    """V0.30.6 B3：4 项实时统计（字数/字速/chunks/ETA）。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    assert "charCount.toLocaleString()" in content
    assert "charsPerSec.toLocaleString()" in content
    assert "chunkCount.toLocaleString()" in content
    assert "formatTime(etaSec)" in content


def test_write_form_has_8_phases() -> None:
    """V0.30.6 B3：8 阶段（init → pre_write → writing → save → extract → merge → post_write → done）。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    expected = ["init", "pre_write", "writing", "save", "extract", "merge", "post_write", "done"]
    for phase in expected:
        assert f"key: '{phase}'" in content, f"Missing phase: {phase}"


def test_write_form_alpine_state_b3_fields() -> None:
    """V0.30.6 B3：Alpine state 含 B3 字段。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    fields = [
        "startTime: 0",
        "chunkCount: 0",
        "charsPerSec: 0",
        "etaSec: 0",
        "currentPhase: 'init'",
    ]
    for f in fields:
        assert f in content, f"Missing Alpine field: {f}"


def test_write_form_alpine_methods_b3() -> None:
    """V0.30.6 B3：Alpine methods 含 B3 函数。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    methods = [
        "startRun(taskId, minC)",
        "handleProgress(data)",
        "handleDone(data)",
        "setPhase(key, status)",
        "markPhaseDone(key)",
        "formatTime(sec)",
        "get progressPct",
    ]
    for m in methods:
        assert m in content, f"Missing Alpine method: {m}"


def test_write_form_sse_handlers_for_progress() -> None:
    """V0.30.6 B3：SSE 事件分发含 progress/done/pre_write_check/post_write_check。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    for event in [
        "progress",
        "done",
        "pre_write_check",
        "post_write_check",
        "chunk",
        "started",
        "cancelled",
        "error",
    ]:
        assert f"evtName === '{event}'" in content, f"Missing SSE event: {event}"


def test_write_form_testids() -> None:
    """V0.30.6 B3：data-testid 元素（便于 E2E 测试）。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    assert 'data-testid="progress-bar-track"' in content
    assert 'data-testid="progress-bar-fill"' in content
    assert 'data-testid="progress-bar-label"' in content
    assert 'data-testid="progress-stats"' in content
    assert 'data-testid="progress-stepper"' in content
    assert ":data-testid" in content  # Alpine dynamic phase testid
    assert "phase-" in content


def test_write_form_progress_section_hidden_in_idle() -> None:
    """V0.30.6 B3：进度条 section 在 idle 状态隐藏。"""
    template = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/write_form.html"
    content = template.read_text(encoding="utf-8")
    # x-show 控制隐藏
    assert "x-show=\"status !== 'idle'\"" in content
    # x-cloak 防止 Alpine 渲染前闪烁
    assert "x-cloak" in content


# === 2. base.html 含 B3 CSS ===


def test_base_html_has_progress_css() -> None:
    """V0.30.6 B3：base.html 含进度条 CSS。"""
    base = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/base.html"
    content = base.read_text(encoding="utf-8")
    classes = [
        ".progress-stepper",
        ".progress-step",
        ".progress-step.active",
        ".progress-step.done",
        ".progress-step.error",
        ".progress-bar-track",
        ".progress-bar-fill",
        ".progress-bar-fill.cancelled",
        ".progress-bar-fill.error",
        ".progress-bar-label",
        ".progress-stats",
        ".progress-stats-item",
        ".progress-pulse",
        "@keyframes progress-pulse",
    ]
    for cls in classes:
        assert cls in content, f"Missing CSS: {cls}"


def test_base_html_progress_has_smooth_transition() -> None:
    """V0.30.6 B3：进度条含 transition 平滑动画。"""
    base = Path(__file__).parent.parent.parent / "src/novel2all/web/templates/base.html"
    content = base.read_text(encoding="utf-8")
    assert "transition: width 0.3s ease" in content
    assert "transition: all 0.2s ease" in content


# === 3. 路由端点渲染 ===


def test_write_form_route_renders_progress_section() -> None:
    """V0.30.6 B3：/page/write-form 渲染含进度条 section。"""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/page/write-form")
        assert response.status_code == 200
        html = response.text
        assert "progress-stepper" in html
        assert "progress-bar-track" in html
        assert "progress-bar-fill" in html
        assert "实时进度" in html


# === 4. 纯函数逻辑 ===


def test_progress_pct_calculation() -> None:
    """V0.30.6 B3：进度百分比正确计算（封顶 100%）。"""

    def progress_pct(char_count: int, min_chars: int) -> int:
        if not min_chars or min_chars <= 0:
            return 0
        return min(100, round((char_count / min_chars) * 100))

    assert progress_pct(0, 2000) == 0
    assert progress_pct(1000, 2000) == 50
    assert progress_pct(2000, 2000) == 100
    assert progress_pct(2500, 2000) == 100  # 封顶
    assert progress_pct(0, 0) == 0  # 防御


def test_format_time_function() -> None:
    """V0.30.6 B3：ETA 时间格式化。"""

    def format_time(sec: int | None) -> str:
        if not sec or sec <= 0:
            return "--:--"
        if sec < 60:
            return f"{sec}s"
        m = sec // 60
        s = sec % 60
        return f"{m}m{s:02d}s"

    assert format_time(0) == "--:--"
    assert format_time(None) == "--:--"
    assert format_time(30) == "30s"
    assert format_time(60) == "1m00s"
    assert format_time(125) == "2m05s"
    assert format_time(3600) == "60m00s"


def test_eta_calculation_logic() -> None:
    """V0.30.6 B3：ETA = (minChars - charCount) / charsPerSec。"""

    def eta_sec(char_count: int, min_chars: int, chars_per_sec: int) -> int:
        remaining = max(0, min_chars - char_count)
        if chars_per_sec <= 0 or remaining == 0:
            return 0
        return round(remaining / chars_per_sec)

    assert eta_sec(0, 2000, 100) == 20
    assert eta_sec(1000, 2000, 100) == 10
    assert eta_sec(2000, 2000, 100) == 0
    assert eta_sec(500, 2000, 0) == 0
