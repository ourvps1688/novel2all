"""V0.23 task 路由集成测试。

验证现有模块（pipeline / extractor / verifier）的 LLM 调用确实传了 task= 参数，
让 ModelRouter 能正确选择模型 + thinking control 自动应用。

测试策略：
- 用 MockLLM 记录所有调用（method, kwargs）
- 调用 pipeline/extractor/verifier 的方法
- 验证 task= 参数被正确传递
- 验证 _resolve_model + _get_extra_body 都基于 task 选择

不调真实 LLM（mock 完全控制返回）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novel2all.core.memory import (
    Tracker,
    Verifier,
)
from novel2all.core.memory.extractor import (
    ExtractedChapterInfo,
    Extractor,
)
from novel2all.core.provider import LLMConfig, LLMProvider
from novel2all.core.provider_router import ModelRouter, TaskType


class MockLLM:
    """记录所有调用的 mock LLM。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stream_response = "第一章的内容..."

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """记录调用并返回 mock 结果。"""
        self.calls.append({"method": "complete", "prompt": prompt, **kwargs})
        return "{}"

    async def complete_structured(self, prompt: str, **kwargs: Any) -> Any:
        """记录调用并返回 mock ExtractedChapterInfo（或 list[ConsistencyIssue]）。"""
        self.calls.append({"method": "complete_structured", "prompt": prompt, **kwargs})
        response_model = kwargs.get("response_model")
        if response_model is list or (
            hasattr(response_model, "__origin__") and response_model.__origin__ is list
        ):
            return []
        if response_model is ExtractedChapterInfo:
            return ExtractedChapterInfo(chapter=1)
        return (
            response_model.model_construct() if hasattr(response_model, "model_construct") else None
        )

    async def stream(self, prompt: str, **kwargs: Any) -> Any:
        """记录调用并返回 mock async iterator。"""
        self.calls.append({"method": "stream", "prompt": prompt, **kwargs})

        async def _gen() -> Any:
            for chunk in self._stream_response:
                yield chunk

        return _gen()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """临时项目根目录。"""
    (tmp_path / "设定").mkdir()
    (tmp_path / "大纲").mkdir()
    (tmp_path / "正文").mkdir()
    return tmp_path


@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


# === Extractor 集成测试 ===


class TestExtractorTaskRouting:
    @pytest.mark.asyncio
    async def test_extractor_uses_extraction_task(
        self, mock_llm: MockLLM, tmp_project: Path
    ) -> None:
        """Extractor 应传 task=TaskType.EXTRACTION。"""
        tracker = Tracker(tmp_project / "_tracking-state.json")
        tracker.init(project_name="测试", total_chapters_target=50)
        state = tracker.read()

        extractor = Extractor(llm=mock_llm)  # type: ignore[arg-type]
        await extractor.extract(
            chapter=1,
            previous_state=state,
            content="测试章节内容",
        )
        assert len(mock_llm.calls) == 1
        call = mock_llm.calls[0]
        assert call["method"] == "complete_structured"
        assert call["task"] == TaskType.EXTRACTION

    @pytest.mark.asyncio
    async def test_extractor_failure_does_not_crash(self, tmp_project: Path) -> None:
        """Extractor 失败时返回兜底结果（不传 task= 参数）。"""

        class FailingMockLLM:
            async def complete_structured(self, prompt: str, **kwargs: Any) -> Any:
                raise RuntimeError("mock failure")

        tracker = Tracker(tmp_project / "_tracking-state.json")
        tracker.init(project_name="测试", total_chapters_target=50)
        state = tracker.read()

        extractor = Extractor(llm=FailingMockLLM())  # type: ignore[arg-type]
        result = await extractor.extract(
            chapter=1,
            previous_state=state,
            content="x",
        )
        # 应该返回兜底（continuity_issues 含失败信息）
        assert result.chapter == 1
        assert len(result.continuity_issues) >= 1


# === Verifier 集成测试 ===


class TestVerifierTaskRouting:
    @pytest.mark.asyncio
    async def test_pre_write_uses_consistency_task(
        self, mock_llm: MockLLM, tmp_project: Path
    ) -> None:
        """Verifier.pre_write_check 应传 task=TaskType.CONSISTENCY。"""
        tracker = Tracker(tmp_project / "_tracking-state.json")
        tracker.init(project_name="测试", total_chapters_target=50)
        state = tracker.read()

        verifier = Verifier(llm=mock_llm)  # type: ignore[arg-type]
        await verifier.pre_write_check(state=state, outline="第1章大纲")

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["method"] == "complete_structured"
        assert mock_llm.calls[0]["task"] == TaskType.CONSISTENCY

    @pytest.mark.asyncio
    async def test_post_write_uses_consistency_task(
        self, mock_llm: MockLLM, tmp_project: Path
    ) -> None:
        """Verifier.post_write_check 应传 task=TaskType.CONSISTENCY。"""
        tracker = Tracker(tmp_project / "_tracking-state.json")
        tracker.init(project_name="测试", total_chapters_target=50)
        state = tracker.read()

        verifier = Verifier(llm=mock_llm)  # type: ignore[arg-type]
        await verifier.post_write_check(state=state, content="第1章内容")

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["method"] == "complete_structured"
        assert mock_llm.calls[0]["task"] == TaskType.CONSISTENCY


# === LLMProvider._resolve_model 集成测试（验证 task 真影响路由）===


class TestTaskAffectsRouting:
    """验证 task= 参数影响真实路由（不只传过去）。"""

    def test_writing_task_picks_flash_v036(self) -> None:
        """V0.36：task=WRITING → 路由到 deepseek/deepseek-flash（V0.35 benchmark 验证 flash 与 minimax 字数持平，便宜 2.5x）。

        历史：
        - V0.23: task=WRITING → deepseek-v4-pro
        - V0.27: task=WRITING → minimax-M3
        - V0.36: task=WRITING → deepseek-flash（V0.35 16 真实调用验证）
        """
        from novel2all.core.provider_router import ModelRouter

        config = LLMConfig()
        router = ModelRouter(config)
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.WRITING)
        assert model == "deepseek/deepseek-flash"
        assert router.select(TaskType.WRITING) == model

    def test_extraction_task_picks_flash(self) -> None:
        """task=EXTRACTION → 路由到 deepseek/deepseek-flash（V0.26 minimax 失败回退）。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.EXTRACTION)
        assert model == "deepseek/deepseek-flash"

    def test_consistency_task_picks_flash(self) -> None:
        """task=CONSISTENCY → 路由到 deepseek/deepseek-flash。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.CONSISTENCY)
        assert model == "deepseek/deepseek-flash"

    def test_summarization_task_picks_flash(self) -> None:
        """task=SUMMARIZATION → 路由到 deepseek/deepseek-flash。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.SUMMARIZATION)
        assert model == "deepseek/deepseek-flash"

    def test_thinking_control_applied_for_flash_v036(self) -> None:
        """V0.36：task=WRITING → 模型 deepseek-flash → 自动禁用 thinking（V0.23 设计的 thinking 控制）。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.WRITING)
        body = provider._get_extra_body(model)
        assert body is not None
        assert body["thinking"]["type"] == "disabled"

    def test_thinking_control_applied_for_flash(self) -> None:
        """task=EXTRACTION → 模型 flash → 自动禁用 thinking。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=TaskType.EXTRACTION)
        body = provider._get_extra_body(model)
        assert body is not None
        assert body["thinking"]["type"] == "disabled"

    def test_explicit_model_overrides_task(self) -> None:
        """显式 model= 参数优先于 task。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        # 即使 task=WRITING，explicit model= 也会覆盖
        model = provider._resolve_model(task=TaskType.WRITING, explicit_model="openai/gpt-4o")
        assert model == "openai/gpt-4o"
        # 但 _get_extra_body 用 explicit model 来查（未知模型返回 None）
        body = provider._get_extra_body(model)
        assert body is None  # openai/gpt-4o 不在 THINKING_CONTROL


# === Pipeline 集成测试（最复杂，跳过部分 mock）===


class TestPipelineTaskRouting:
    def test_pipeline_imports_task_type(self) -> None:
        """WritingPipeline 源码应 import TaskType。"""
        import inspect

        from novel2all.core import pipeline as pipeline_mod

        source = inspect.getsource(pipeline_mod)
        assert "TaskType" in source
        assert "TaskType.WRITING" in source

    def test_extractor_imports_task_type(self) -> None:
        """Extractor 源码应 import TaskType。"""
        import inspect

        from novel2all.core.memory import extractor as extractor_mod

        source = inspect.getsource(extractor_mod)
        assert "TaskType" in source
        assert "TaskType.EXTRACTION" in source

    def test_verifier_imports_task_type(self) -> None:
        """Verifier 源码应 import TaskType。"""
        import inspect

        from novel2all.core.memory import verifier as verifier_mod

        source = inspect.getsource(verifier_mod)
        assert "TaskType" in source
        assert "TaskType.CONSISTENCY" in source


# === 完整链路测试：所有 task 路由都正确（无 mock）===


class TestAllTasksRouteCorrectly:
    """验证 5 个 TaskType 都能正确解析到对应模型（V0.36 路由策略）。

    V0.36 关键变化：WRITING 从 minimax-M3 切回 deepseek-flash
    （V0.35 真实 benchmark 验证字数持平，便宜 2.5 倍）。
    所有 5 个 task 现在统一走 deepseek-flash（fallback 仍为 v4-pro）。
    """

    @pytest.mark.parametrize(
        "task,expected_model",
        [
            # V0.36: WRITING 切回 deepseek-flash（V0.35 benchmark 验证）
            (TaskType.WRITING, "deepseek/deepseek-flash"),
            (TaskType.CONSISTENCY, "deepseek/deepseek-flash"),
            (TaskType.EXTRACTION, "deepseek/deepseek-flash"),
            (TaskType.SUMMARIZATION, "deepseek/deepseek-flash"),
            (TaskType.COVER, "deepseek/deepseek-flash"),
        ],
    )
    def test_task_to_model_mapping(self, task: TaskType, expected_model: str) -> None:
        """所有 5 个 TaskType 都映射到 V0.36 路由策略对应的模型。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=task)
        assert model == expected_model

        # 同时 thinking control 应被应用
        body = provider._get_extra_body(model)
        assert body is not None
        assert body["thinking"]["type"] == "disabled"


# === V0.26 minimax 端到端测试（验证 MODEL_CONFIG 自动应用）===


class TestMinimaxIntegrationV027:
    """V0.27：minimax-M3 接入默认 WRITING 路由（基于实测质量优势）。

    关键发现：
    - minimax 实测 845 字 vs DeepSeek flash 550 字（不是空话：剧情推进 + 角色独白 + 伏笔）
    - minimax 强制用 Anthropic 兼容路径（api_base=https://api.minimax.cn/anthropic）
    - V0.27 transparent 分流：_is_anthropic_compat → _call_anthropic_compat（httpx）
    - complete_structured() 不支持 minimax（Anthropic Messages API 不兼容 instructor）
    """

    def test_minimax_in_writing_route(self) -> None:
        """V0.36：WRITING 默认路由到 deepseek-flash（V0.35 benchmark 验证 flash 与 minimax 字数持平，便宜 2.5x）。

        注意：minimax 仍然注册在 MODEL_CONFIG（可被显式 model="minimax/MiniMax-M3" 调用），
        但不再是默认 WRITING 路由。V0.36 fallback 是 v4-pro（高质但慢）。
        """
        config = LLMConfig()
        router = ModelRouter(config)
        assert router.select(TaskType.WRITING) == "deepseek/deepseek-flash"

    def test_minimax_NOT_in_other_task_routes(self) -> None:
        """V0.27：其他 4 个 task 不路由到 minimax（保持 deepseek-flash）。"""
        config = LLMConfig()
        router = ModelRouter(config)
        for task in (
            TaskType.CONSISTENCY,
            TaskType.EXTRACTION,
            TaskType.SUMMARIZATION,
            TaskType.COVER,
        ):
            assert router.select(task) != "minimax/MiniMax-M3", (
                f"{task.value} 不应该默认路由到 minimax"
            )

    def test_minimax_config_still_available(self) -> None:
        """minimax MODEL_CONFIG 仍可用（benchmark + 流式调用）。"""
        from novel2all.core.provider_router import get_model_config

        cfg = get_model_config("minimax/MiniMax-M3")
        assert cfg.api_base == "https://api.minimax.cn/anthropic"
        assert cfg.extra_body == {"thinking": {"type": "disabled"}}

    def test_minimax_complete_applies_api_base(self) -> None:
        """V0.27 transparent 分流：LLMProvider.complete 调用 minimax 时走 httpx 分支。

        V0.27 关键改动：minimax-M3 必须用 Anthropic Messages API（国内端点
        api.minimax.cn/anthropic），litellm 默认拼 /v1/chat/completions → 404。
        LLMProvider._is_anthropic_compat() 检测 api_base 含 "anthropic" 时，
        绕过 litellm，直接 httpx POST /v1/messages。
        """
        import asyncio
        import os
        from unittest.mock import AsyncMock, patch

        # 确保有 API key（mock httpx 不真发请求，但 _anthropic_api_key_for 需读到 key）
        os.environ["MINIMAX_API_KEY"] = "test-key-v027"

        config = LLMConfig()
        provider = LLMProvider(config)

        from novel2all.core import provider as provider_mod

        # 直接 patch _call_anthropic_compat（端到端 mock）— 验证调用链 + 返回内容
        with patch.object(
            provider_mod.LLMProvider,
            "_call_anthropic_compat",
            new_callable=AsyncMock,
        ) as mock_call:
            mock_call.return_value = "MOCK_RESPONSE"

            result = asyncio.run(provider.complete(prompt="hello", model="minimax/MiniMax-M3"))

            # 1. httpx 分支被调用（不是 litellm）
            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args.kwargs
            assert call_kwargs["model_name"] == "minimax/MiniMax-M3"
            assert call_kwargs["api_base"] == "https://api.minimax.cn/anthropic"
            assert call_kwargs["api_key"] == "test-key-v027"
            assert call_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}

            # 2. 返回的内容正确传递
            assert result == "MOCK_RESPONSE"

    def test_minimax_cache_key_uses_correct_endpoint(self) -> None:
        """V0.26: minimax cache key 应包含正确的 model name。"""
        from novel2all.core.provider import LLMProvider

        config = LLMConfig(cache_enabled=True, default_model="minimax/MiniMax-M3")
        provider = LLMProvider(config)
        key = provider._make_cache_key("minimax/MiniMax-M3", "sys", "user", 0.7)
        assert key[0] == "minimax/MiniMax-M3"
