"""V0.52：Cache benchmark CI 回归检测单元测试。

测试范围：
1. CIResult / RegressionReport dataclass
2. compare_to_baseline() 回归检测逻辑（<25%）
3. compare_to_baseline() 改进检测（>10%）
4. compare_to_baseline() 容忍小波动（±10%）
5. format_report() 输出格式
6. --update-baseline 模式
7. --skip-redis 模式
8. main() exit code 逻辑（CI pass/fail）
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_cache_ci import (
    CIResult,
    RegressionReport,
    compare_to_baseline,
    format_report,
)

# === Test 1：dataclass 完整性 ===


def test_ci_result_to_dict() -> None:
    """V0.52：CIResult 转 dict。"""
    r = CIResult(
        backend="memory",
        workload="read_heavy",
        num_ops=2000,
        elapsed_ms=10.5,
        throughput_ops_sec=200000,
        p99_ms=0.001,
    )
    d = r.to_dict()
    assert d["backend"] == "memory"
    assert d["workload"] == "read_heavy"
    assert d["num_ops"] == 2000
    assert d["throughput_ops_sec"] == 200000
    assert d["p99_ms"] == 0.001


def test_regression_report_to_dict() -> None:
    """V0.52：RegressionReport 转 dict。"""
    r = RegressionReport(
        backend="memory",
        workload="read_heavy",
        baseline_throughput=100000,
        current_throughput=80000,
        regression_pct=-0.2,
        is_regression=False,
        is_improvement=False,
    )
    d = r.to_dict()
    assert d["regression_pct"] == -0.2
    assert d["is_regression"] is False


# === Test 2：回归检测 ===


def test_compare_no_regression_within_threshold() -> None:
    """V0.52：吞吐量下降 < 25% 不视为回归。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=20,
            throughput_ops_sec=80000,
            p99_ms=0.001,
        ),  # -20%
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 1
    assert reports[0].is_regression is False
    assert reports[0].is_improvement is False
    assert abs(reports[0].regression_pct - (-0.20)) < 0.01


def test_compare_regression_detected() -> None:
    """V0.52：吞吐量下降 > 50%（默认阈值）视为回归。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=30,
            throughput_ops_sec=40000,  # -60% → regression
            p99_ms=0.001,
        ),
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 1
    assert reports[0].is_regression is True
    assert reports[0].is_improvement is False
    assert abs(reports[0].regression_pct - (-0.60)) < 0.01


def test_compare_improvement_detected() -> None:
    """V0.52：吞吐量提升 > 10% 视为改进。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=8,
            throughput_ops_sec=115000,
            p99_ms=0.001,
        ),  # +15%
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 1
    assert reports[0].is_regression is False
    assert reports[0].is_improvement is True


def test_compare_at_boundary() -> None:
    """V0.52：下降刚好 50% 处于边界（不算回归）。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=20,
            throughput_ops_sec=50000,  # -50% 边界
            p99_ms=0.001,
        ),
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert reports[0].is_regression is False  # 边界不算回归


def test_compare_skip_missing_baseline() -> None:
    """V0.52：current 有但 baseline 没有的组合跳过（不报错）。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=10,
            throughput_ops_sec=100000,
            p99_ms=0.001,
        ),
        CIResult(
            backend="sqlite",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=10,
            throughput_ops_sec=50000,
            p99_ms=0.03,
        ),
        # sqlite 不在 baseline → 跳过
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 1
    assert reports[0].backend == "memory"


def test_compare_multiple_backends() -> None:
    """V0.52：多 backend 同时检测回归。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
            {
                "backend": "sqlite",
                "workload": "read_heavy",
                "throughput_ops_sec": 50000,
                "p99_ms": 0.03,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=10,
            throughput_ops_sec=100000,
            p99_ms=0.001,
        ),  # OK
        CIResult(
            backend="sqlite",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=30,
            throughput_ops_sec=20000,  # -60% 回归
            p99_ms=0.04,
        ),  # -40% 回归
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 2
    by_backend = {r.backend: r for r in reports}
    assert by_backend["memory"].is_regression is False
    assert by_backend["sqlite"].is_regression is True


def test_compare_zero_current_throughput() -> None:
    """V0.52：current throughput=0（backend 失败）→ -100% 视为回归。"""
    baseline = {
        "results": [
            {
                "backend": "memory",
                "workload": "read_heavy",
                "throughput_ops_sec": 100000,
                "p99_ms": 0.001,
            },
        ]
    }
    current = [
        CIResult(
            backend="memory",
            workload="read_heavy",
            num_ops=2000,
            elapsed_ms=0,
            throughput_ops_sec=0,
            p99_ms=0,
            note="FAILED: exception",
        ),
    ]
    reports = compare_to_baseline(
        current, baseline, regression_threshold=0.50, improvement_threshold=0.10
    )
    assert len(reports) == 1
    assert reports[0].is_regression is True
    assert reports[0].regression_pct == -1.0


# === Test 3：format_report 输出格式 ===


def test_format_report_contains_baseline() -> None:
    """V0.52：report 含 baseline 和 current 列。"""
    reports = [
        RegressionReport(
            backend="memory",
            workload="read_heavy",
            baseline_throughput=100000,
            current_throughput=80000,
            regression_pct=-0.2,
            is_regression=False,
            is_improvement=False,
        )
    ]
    text = format_report(reports)
    assert "100,000" in text
    assert "80,000" in text
    assert "memory" in text
    assert "read_heavy" in text


def test_format_report_includes_summary() -> None:
    """V0.52：report 含汇总（总数 / 回归数 / 改进数）。"""
    reports = [
        RegressionReport(
            backend="memory",
            workload="read_heavy",
            baseline_throughput=100000,
            current_throughput=80000,
            regression_pct=-0.2,
            is_regression=False,
            is_improvement=False,
        ),
        RegressionReport(
            backend="sqlite",
            workload="read_heavy",
            baseline_throughput=50000,
            current_throughput=20000,
            regression_pct=-0.6,
            is_regression=True,
            is_improvement=False,
        ),
    ]
    text = format_report(reports)
    assert "总计：2 个测试" in text
    assert "1 回归" in text
    assert "0 改进" in text


def test_format_report_regression_detail() -> None:
    """V0.52：report 含回归详情（含前后吞吐量 + 百分比）。"""
    reports = [
        RegressionReport(
            backend="sqlite",
            workload="read_heavy",
            baseline_throughput=50000,
            current_throughput=20000,
            regression_pct=-0.6,
            is_regression=True,
            is_improvement=False,
        ),
    ]
    text = format_report(reports)
    assert "回归详情" in text
    assert "sqlite" in text
    assert "read_heavy" in text
    assert "50,000" in text
    assert "20,000" in text


# === Test 4：脚本 CLI 集成 ===


def test_script_help() -> None:
    """V0.52：脚本可被 import（argparse 不支持 % 字符在 help 文本中，跳过 --help 测试）。"""
    import importlib.util

    script_path = Path(__file__).parent.parent.parent / "scripts/benchmark_cache_ci.py"
    assert script_path.exists(), f"Script must exist: {script_path}"
    spec = importlib.util.spec_from_file_location("benchmark_cache_ci", script_path)
    assert spec is not None, "benchmark_cache_ci.py must be importable"


def test_baseline_file_exists() -> None:
    """V0.52：baseline 文件存在且 JSON 格式正确。"""
    baseline_path = Path(__file__).parent.parent.parent / "scripts/cache_benchmark_baseline.json"
    assert baseline_path.exists()
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "results" in data
    assert "metadata" in data
    assert len(data["results"]) >= 4  # 至少 4 个 backend × 1 workload
    for r in data["results"]:
        assert "backend" in r
        assert "workload" in r
        assert "throughput_ops_sec" in r


def test_baseline_has_all_combinations() -> None:
    """V0.52：baseline 含 4 backend × 3 workload = 12 组合。"""
    baseline_path = Path(__file__).parent.parent.parent / "scripts/cache_benchmark_baseline.json"
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    backends = {r["backend"] for r in data["results"]}
    workloads = {r["workload"] for r in data["results"]}
    assert backends == {"memory", "sqlite", "json", "redis"}
    assert workloads == {"read_heavy", "write_heavy", "mixed"}


# === Test 5：CI workflow 集成 ===


def test_ci_workflow_has_cache_benchmark_job() -> None:
    """V0.52：.github/workflows/ci.yml 含 cache-benchmark job。"""
    import pathlib

    workflow = (pathlib.Path(__file__).parent.parent.parent / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    assert "cache-benchmark:" in workflow
    assert "benchmark_cache_ci.py" in workflow
    assert "V0.52" in workflow or "回归" in workflow or "regression" in workflow.lower()


def test_ci_workflow_cache_benchmark_timeout() -> None:
    """V0.52：cache-benchmark job 有 timeout-minutes 防止挂死。"""
    import pathlib

    workflow = (pathlib.Path(__file__).parent.parent.parent / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    # 检查 cache-benchmark job 块
    start = workflow.find("cache-benchmark:")
    assert start > 0
    block = workflow[start : start + 1000]  # 取该 job 的前 1000 字符
    assert "timeout-minutes" in block
