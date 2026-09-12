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
from novel2all.core.provider_router import TaskType


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

    def test_writing_task_picks_v4_pro(self) -> None:
        """task=WRITING → 路由到 deepseek/deepseek-v4-pro。"""
        from novel2all.core.provider_router import ModelRouter

        config = LLMConfig()
        router = ModelRouter(config)
        provider = LLMProvider(config)

        # 直接模拟 provider._resolve_model 行为
        model = provider._resolve_model(task=TaskType.WRITING)
        assert model == "deepseek/deepseek-v4-pro"
        assert router.select(TaskType.WRITING) == model

    def test_extraction_task_picks_flash(self) -> None:
        """task=EXTRACTION → 路由到 deepseek/deepseek-flash。"""
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

    def test_thinking_control_applied_for_v4_pro(self) -> None:
        """task=WRITING → 模型 v4-pro → 自动禁用 thinking。"""
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
    """验证 5 个 TaskType 都能正确解析到 DeepSeek 模型（V0.23 路由策略）。"""

    @pytest.mark.parametrize(
        "task,expected_model",
        [
            (TaskType.WRITING, "deepseek/deepseek-v4-pro"),
            (TaskType.CONSISTENCY, "deepseek/deepseek-flash"),
            (TaskType.EXTRACTION, "deepseek/deepseek-flash"),
            (TaskType.SUMMARIZATION, "deepseek/deepseek-flash"),
            (TaskType.COVER, "deepseek/deepseek-flash"),
        ],
    )
    def test_task_to_model_mapping(self, task: TaskType, expected_model: str) -> None:
        """所有 5 个 TaskType 都映射到 V0.23 路由策略对应的模型。"""
        config = LLMConfig()
        provider = LLMProvider(config)

        model = provider._resolve_model(task=task)
        assert model == expected_model

        # 同时 thinking control 应被应用
        body = provider._get_extra_body(model)
        assert body is not None
        assert body["thinking"]["type"] == "disabled"
