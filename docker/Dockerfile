# syntax=docker/dockerfile:1.7
# novel2all 0.20 Docker image

FROM python:3.12-slim AS base

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 工作目录
WORKDIR /app

# 先拷贝 lockfile 缓存依赖层
COPY pyproject.toml ./
COPY src ./src

# 用 uv 安装（生产模式，禁用 dev 依赖）
RUN uv pip install --system --no-cache .

# 入口
ENTRYPOINT ["python", "-m", "novel2all.cli.main"]
CMD ["version"]
