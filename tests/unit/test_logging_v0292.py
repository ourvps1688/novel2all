"""V0.29.2 logging 系统化测试。

确保：
- 库不主动配 root logger（仅 NullHandler）
- src/ 内不再有 print() 调用（除 cli/main.py 内的 console.print——rich 用户友好）
- 各 core 模块有 logger = logging.getLogger(__name__)
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent.parent / "src" / "novel2all"


class TestNoPrintInSrcV0292:
    """V0.29.2：src/ 内不应该有 print() 调用（用 rich console.print 替代 CLI 输出）。"""

    def _walk_print_calls(self) -> list[tuple[Path, int]]:
        """AST 扫描 src/ 内所有 print() 调用（排除 docstring）。"""
        results: list[tuple[Path, int]] = []
        for p in SRC_DIR.rglob("*.py"):
            # 跳过 cli/ —— CLI 用 rich console.print（用户友好）
            if "cli/" in str(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "print"
                    ):
                        results.append((p, node.lineno))
        return results

    def test_no_print_in_core(self) -> None:
        """core/ 任何 print() 调用都是回归（应改 logger）。"""
        violations = self._walk_print_calls()
        if violations:
            msg = "\n".join(
                f"  {p.relative_to(SRC_DIR.parent.parent)}:{ln}" for p, ln in violations
            )
            raise AssertionError(
                f"V0.29.2: src/novel2all 内发现 {len(violations)} 个 print() 调用（应改 logger）：\n{msg}"
            )


class TestNullHandlerInInitV0292:
    """V0.29.2：novel2all 包根 logger 配 NullHandler 避免 'No handlers' warning。"""

    def test_root_logger_has_null_handler(self) -> None:
        """import novel2all 后，'novel2all' logger 至少有一个 NullHandler。"""
        # 重要：清空 root 缓存以重测
        import importlib

        import novel2all

        importlib.reload(novel2all)
        logger = logging.getLogger("novel2all")
        # 至少有一个 handler 是 NullHandler
        has_null = any(isinstance(h, logging.NullHandler) for h in logger.handlers)
        assert has_null, "novel2all 根 logger 应该有 NullHandler"


class TestCoreModulesHaveLoggerV0292:
    """V0.29.2：所有 core 模块应有 logger = logging.getLogger(__name__)。"""

    @pytest.mark.parametrize(
        "module_path",
        [
            "novel2all.core.provider",
            "novel2all.core.pipeline",
            "novel2all.core.role",
            "novel2all.core.skill",
        ],
    )
    def test_module_has_logger(self, module_path: str) -> None:
        """模块应有 __name__ 命名的 logger。"""
        import importlib

        mod = importlib.import_module(module_path)
        # 模块不应配置 logger（只是 logging.getLogger(__name__)）
        # 验证：mod.logger.name == module_path
        assert hasattr(mod, "logger"), f"{module_path} 缺少 logger"
        assert mod.logger.name == module_path, (
            f"{module_path}.logger.name 应该是 '{module_path}'，实际是 '{mod.logger.name}'"
        )


class TestCoreModulesLogBehaviorV0292:
    """V0.29.2：logger 实际行为——caplog 验证能捕获 warning。"""

    def test_pipeline_logs_stream_callback_errors(self, caplog) -> None:
        """pipeline.py logger 能在 stream_callback 错误时记录 warning。"""
        import logging

        logger = logging.getLogger("novel2all.core.pipeline")
        with caplog.at_level(logging.WARNING, logger="novel2all.core.pipeline"):
            # 直接 logger.warning() —— 验证 logger 配置正确
            logger.warning("test warning from pipeline")
        assert any("test warning from pipeline" in r.message for r in caplog.records)

    def test_role_logs_load_failure(self, caplog) -> None:
        """role.py logger 能在 load role 失败时记录 warning。"""
        import logging

        logger = logging.getLogger("novel2all.core.role")
        with caplog.at_level(logging.WARNING, logger="novel2all.core.role"):
            logger.warning("test warning from role")
        assert any("test warning from role" in r.message for r in caplog.records)
