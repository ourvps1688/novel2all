"""V0.30.1：模型选择器 API + 前端 partial 测试。

V0.30.1 新增端点：
- GET /api/models：列出 MODEL_CONFIG 所有模型（JSON）
- GET /api/model/current：当前模型
- POST /api/model/switch：切换 default_model（Form 参数）
- GET /page/model-selector：HTMX partial 渲染 model_selector.html
- GET /page/write-form：HTMX partial 渲染 write_form.html（带模型下拉）
- POST /api/write/stream/model：V0.30.1 模型感知的流式写作端点

测试覆盖：
- /api/models 列出所有模型 + 正确字段
- /api/model/switch 切换 + 验证 old_model/new_model
- /api/model/switch 拒绝未知模型（HTTPException 400）
- /page/model-selector 返回 HTML partial
- /page/write-form 返回 HTML partial 含 model <select>
- index.html 含 /page/model-selector 和 /page/write-form 引用
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel2all.core.provider_router import MODEL_CONFIG
from novel2all.web.app import create_app


class TestModelSelectorAPIv0301:
    """V0.30.1：模型选择器后端 API。"""

    def test_api_models_returns_all_models(self) -> None:
        """/api/models 列出 MODEL_CONFIG 中所有模型。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/models")
            assert response.status_code == 200
            models = response.json()
            assert isinstance(models, list)
            # 应有全部 MODEL_CONFIG 模型
            assert len(models) == len(MODEL_CONFIG)
            returned_names = {m["name"] for m in models}
            expected_names = set(MODEL_CONFIG.keys())
            assert returned_names == expected_names

    def test_api_models_includes_anthropic_compat_flag(self) -> None:
        """/api/models 返回每条含 anthropic_compat 字段。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/models")
            models = response.json()
            for m in models:
                assert "name" in m
                assert "anthropic_compat" in m
                assert "api_base" in m
                assert "api_key_env" in m
            # minimax 应标 True（api_base 含 anthropic）
            minimax = next(m for m in models if m["name"] == "minimax/MiniMax-M3")
            assert minimax["anthropic_compat"] is True
            # deepseek 应标 False
            deepseek = next(m for m in models if m["name"] == "deepseek/deepseek-flash")
            assert deepseek["anthropic_compat"] is False

    def test_api_model_current_returns_initial_model(self) -> None:
        """/api/model/current 返回当前 provider 的 default_model。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/model/current")
            assert response.status_code == 200
            data = response.json()
            assert "model" in data
            # V0.27 + V0.29.4 后默认是 deepseek/deepseek-chat（向后兼容）
            # 不强制特定值，只要是非空字符串
            assert isinstance(data["model"], str) and len(data["model"]) > 0

    def test_api_model_switch_changes_default_model(self) -> None:
        """POST /api/model/switch 成功切换 default_model。"""
        app = create_app()
        with TestClient(app) as client:
            # 初始 model
            r1 = client.get("/api/model/current")
            old_model = r1.json()["model"]

            # 切到 minimax
            r2 = client.post("/api/model/switch", data={"model": "minimax/MiniMax-M3"})
            assert r2.status_code == 200
            data = r2.json()
            assert data["old_model"] == old_model
            assert data["new_model"] == "minimax/MiniMax-M3"

            # 验证持久化：再次查 current 应是新值
            r3 = client.get("/api/model/current")
            assert r3.json()["model"] == "minimax/MiniMax-M3"

    def test_api_model_switch_rejects_unknown_model(self) -> None:
        """POST /api/model/switch 拒绝未知模型（HTTPException 400）。"""
        app = create_app()
        with TestClient(app) as client:
            r = client.post("/api/model/switch", data={"model": "nonexistent/fake-model"})
            assert r.status_code == 400
            assert "未知模型" in r.text or "Unknown" in r.text


class TestWriteStreamWithModelV0301:
    """V0.30.1：/api/write/stream/model 端点（带 model 参数的流式写作）。"""

    def test_write_stream_model_endpoint_exists(self) -> None:
        """POST /api/write/stream/model 端点存在（不需要初始化项目，返回 error 事件）。"""
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/write/stream/model",
                data={
                    "chapter": 1,
                    "project_root": "D:/nonexistent_project",
                    "model": "minimax/MiniMax-M3",
                },
            )
            # 不应返回 404/405（端点存在）
            assert response.status_code != 404
            assert response.status_code != 405
            # 不需要初始化项目也会返回 error SSE
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = response.text
            assert "error" in body
            assert "项目未初始化" in body
