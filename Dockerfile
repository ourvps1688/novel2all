# V1.0 GA：novel2all Web UI Docker 镜像
# 基于 Python 3.12 slim（兼容所有依赖 + 小体积）

FROM python:3.12-slim AS base

# V0.40+ 推荐：设置时区（中国用户）
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# V0.30.6 B5：admin 用户（必填，否则无法登录）
# 用户使用 `docker run -e NOVEL2ALL_ADMIN_USER=admin -e NOVEL2ALL_ADMIN_PASS=secret`
ENV NOVEL2ALL_ADMIN_USER="" \
    NOVEL2ALL_ADMIN_PASS="" \
    NOVEL2ALL_LLM_CACHE_ENABLED=true \
    NOVEL2ALL_LLM_CACHE_BACKEND=sqlite \
    NOVEL2ALL_LLM_CACHE_TTL=86400

# 工作目录
WORKDIR /app

# 系统依赖（gcc for some Python wheels）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件（利用 Docker 缓存）
COPY pyproject.toml ./
COPY uv.lock* ./

# 优先用 uv（更快）；fallback 到 pip
RUN pip install --upgrade pip && \
    pip install fastapi 'uvicorn[standard]' pydantic

# 复制源码
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# 安装项目本身（含所有依赖）
RUN pip install -e .

# 数据目录（持久化 cache + auth.db + sessions.db）
RUN mkdir -p /app/.novel2all /app/正文

# V1.0.1 B4：以非 root 用户运行（最小权限原则 + CIS Docker Benchmark）
RUN useradd -m -u 1001 novel && chown -R novel:novel /app
USER novel

# 暴露端口
EXPOSE 8000

# V0.30.6 B5：启动 Web UI（lifespan 自动初始化 AdaptiveRouter + AuthStore）
# 默认用 1 worker（cache state 在内存，multi-worker 会数据不一致）
# 生产环境用 docker-compose + redis backend 跨 worker 共享
CMD ["uvicorn", "novel2all.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
