# novel2all 部署指南

本文档说明如何把 novel2all 推到 GitHub + 触发 CI workflows + 团队成员拉取。

## 1. 准备 GitHub 仓库

### 1.1 在 GitHub 创建仓库

1. 访问 https://github.com/new
2. 仓库名：`novel2all`（或 `novel2all-team-internal`）
3. 可见性：Private（团队版）或 Public（开源）
4. **不要**勾选 "Initialize this repository with a README"
5. 点 Create repository

### 1.2 在本地初始化 git + 推送

```bash
cd D:\OHMYSTORY\novel2all

# 初始化 git
git init
git add -A

# 配置 .gitignore 已经覆盖了：
# - .env / .env.local（secrets）
# - __pycache__ / .pytest_cache / .ruff_cache
# - dist / build（构建产物）
# - backups（备份）

# 首次提交
git commit -m "feat(v0.20): initial release

- 5 层长记忆系统 (L1-L5)
- 13 个 Skill (从 claudecode 0.7.10 fork)
- 7 个 Role
- CLI (Typer) + Web UI (FastAPI)
- 36 unit tests + 4 e2e tests, all passing
- GitHub workflows (CI / release / codeql / dependabot)
- 完整文档 (README / ARCHITECTURE / ROADMAP / DECISIONS)"

# 加 remote（替换 YOUR_ORG 为你的 GitHub 用户名或组织名）
git remote add origin https://github.com/YOUR_ORG/novel2all.git

# 推 main 分支
git branch -M main
git push -u origin main
```

### 1.3 验证推送

```bash
git log --oneline
# 应该看到你刚 commit 的 initial release

git remote -v
# 应该显示 origin https://github.com/YOUR_ORG/novel2all.git
```

## 2. GitHub Actions 自动触发

推送后，GitHub Actions 会自动跑 4 个 workflow：

| Workflow | 触发条件 | 用途 |
|---|---|---|
| **CI** | push / PR | 跑测试 + lint + typecheck + build |
| **CodeQL** | push / PR / 每周一 | 安全扫描 |
| **Dependabot** | 每周一 | 自动 PR 更新依赖 |
| **Release** | push tag `v*` | 发 GitHub Release + PyPI |

### 2.1 验证 CI 跑通

1. 打开 GitHub 仓库 → Actions 标签
2. 点 CI workflow
3. 看每个 job 的状态：
   - ✅ Test (ubuntu-latest / py3.12)
   - ✅ Test (ubuntu-latest / py3.13)
   - ✅ Test (windows-latest / py3.12)
   - ✅ Test (macos-latest / py3.12)
   - ✅ Lint (ruff)
   - ✅ Type check (mypy)
   - ✅ Skills + Roles manifest
   - ✅ License headers
   - ✅ Build package

### 2.2 跑测试矩阵

CI 在 3 OS × 2 Python 版本 = 6 个组合上跑测试：

- ubuntu-latest + Python 3.12
- ubuntu-latest + Python 3.13
- windows-latest + Python 3.12
- windows-latest + Python 3.13
- macos-latest + Python 3.12
- macos-latest + Python 3.13

## 3. 配置 PyPI 发布（可选）

如果想发到 PyPI（让 `pip install novel2all` 能装），需要配置 Trusted Publishing：

1. 去 https://pypi.org/manage/account/publishing/
2. 添加 pending publisher：
   - Project: `novel2all`
   - Owner: `<your-username>`
   - Repository: `novel2all`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. 在 GitHub 仓库设置 → Environments → New environment → 命名 `pypi`
4. （可选）加 protection rules

之后 `git tag v0.20.0 && git push --tags` 就会自动发到 PyPI。

## 4. 配置 Docker 镜像发布（可选）

如果要让 GitHub Container Registry 自动 build Docker 镜像：

1. 在 GitHub 仓库设置 → General → Features
2. 确保 "Packages" 启用
3. `git tag v0.20.0 && git push --tags` 触发 release workflow
4. 镜像会自动推到 `ghcr.io/<your-org>/novel2all:0.20.0`

## 5. 团队成员拉取

### 5.1 克隆 + 装依赖

```bash
git clone https://github.com/YOUR_ORG/novel2all.git
cd novel2all

# 用 uv（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 或者用 pip
python -m pip install -e .[dev]
```

### 5.2 配置 API Key

```bash
# Claude (推荐)
export ANTHROPIC_API_KEY=sk-ant-...

# 或 OpenAI / DeepSeek
export OPENAI_API_KEY=sk-...
export DEEPSEEK_API_KEY=sk-...
```

### 5.3 验证

```bash
# 跑测试
make test

# 启动 CLI
make cli

# 启动 Web UI
make serve
# -> http://127.0.0.1:8765
```

## 6. 日常开发流程

```bash
# 1. 创建分支
git checkout -b feat/my-feature

# 2. 改代码

# 3. 跑测试 + lint
make verify-ci

# 4. 提交
git add -A
git commit -m "feat: add xxx"

# 5. push + PR
git push -u origin feat/my-feature

# 6. GitHub 上开 PR → CI 自动跑 → merge
```

## 7. 发布新版本

```bash
# 1. 更新版本号
# 编辑 pyproject.toml: version = "0.20.0" → "0.21.0"
# 编辑 src/novel2all/__init__.py: __version__ = "0.20.0" → "0.21.0"

# 2. 更新 CHANGELOG.md

# 3. 提交
git add -A
git commit -m "chore(release): v0.21.0"

# 4. 打 tag + push
git tag v0.21.0
git push --tags

# 5. CI 自动跑 release workflow：
#    - Build sdist + wheel
#    - 发 PyPI（如已配置）
#    - 发 GitHub Release
#    - Build Docker 镜像（如已配置）
```

## 8. 故障排查

### CI 跑不通

1. 看 GitHub Actions 日志 → 找失败 job → 看错误信息
2. 本地复现：`make verify-ci`（跑 lint + test + typecheck）
3. 修复后 push，CI 重跑

### Windows 测试失败但 Linux 通过

可能是路径处理差异。看 pytest 输出里的路径分隔符。

### Docker build 失败

1. 看 release workflow 日志
2. 本地试：`docker build -f docker/Dockerfile -t novel2all:test .`

### PyPI 发布失败

1. 检查 Trusted Publishing 设置是否正确
2. 检查 tag 格式（必须是 `v*`）
3. 检查 version 是否已存在（PyPI 不允许覆盖）

## 9. 安全建议

- ✅ 启用 GitHub Dependabot 自动 PR 依赖更新
- ✅ 启用 CodeQL 安全扫描
- ✅ 启用 branch protection（main 分支必须 PR + 1 review）
- ✅ 启用 secret scanning
- ⚠️ 不要把 `.env` 提交（已在 .gitignore）
- ⚠️ 不要在 PR 描述里贴 API Key
