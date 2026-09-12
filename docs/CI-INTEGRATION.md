# CI 状态集成（让 AI 助手自动获取 CI workflow 信息）

> 本文说明如何让 **WorkBuddy / Claude Code / Cursor / Cline 等 AI 助手** 自动获取 GitHub Actions workflow 的运行状态、失败原因、修复建议。

---

## 1. 为什么需要这个？

AI 助手（WorkBuddy）默认**不知道** GitHub Actions 的运行结果。当用户说"CI 挂了帮我看看"时，AI 必须能：

| 能力 | 实现 |
|---|---|
| 查最近 workflow run 状态 | GitHub REST API |
| 看失败的 job 日志 | API 或本地缓存 |
| 知道是哪个 commit 失败 | API 返回 `head_sha` |
| 拉本地代码 + 看 diff | `git` CLI |
| 修代码 + push 修复 | `git` CLI + push |
| 重跑 CI | GitHub API |

我们提供 3 个工具让 AI 助手能做这些事。

---

## 2. 三个工具

### 2.1 `scripts/ci_status.py` — 一次性查询

```bash
# 公共仓库（无需 token）
python scripts/ci_status.py

# private 仓库
export GITHUB_TOKEN=ghp_xxxxx
python scripts/ci_status.py

# 看特定 run 详情
python scripts/ci_status.py --run-id 12345

# 输出 JSON（让 AI 助手解析）
python scripts/ci_status.py --json
```

**典型输出**：

```
📦 novel2all CI 状态 — zenstory-ai/novel2all

STATUS   NAME                          BRANCH         COMMIT   DURATION   WHEN
─────────────────────────────────────────────────────────────────────────────────────────────
✅       CI                            main           a3f2b1c  142s      2026-09-12 09:15:00
✅       Release                       v0.20.0        8e4d2f1  87s       2026-09-12 09:00:00
❌       CI                            feat/my-fix    5c1d2e3  203s      2026-09-12 08:30:00
⏳       CI                            main           9f8b2a4  -         2026-09-12 09:28:00

[hint] 加 --watch 轮询；加 --json 让 AI 助手解析
```

### 2.2 `scripts/ci_watch.py` — 守护进程（写到文件）

```bash
# 前台跑
python scripts/ci_watch.py

# 后台跑
python scripts/ci_watch.py &
echo $! > .ci_watch.pid

# 写到自定义路径
python scripts/ci_watch.py --output /tmp/ci-status.json

# 间隔 30 秒
python scripts/ci_watch.py --interval 30
```

**输出文件** `.novel2all/ci-status.json`：

```json
{
  "last_updated": "2026-09-12T09:30:00Z",
  "repo": "zenstory-ai/novel2all",
  "summary": {
    "total": 10,
    "success": 8,
    "failure": 1,
    "in_progress": 1,
    "queued": 0,
    "cancelled": 0
  },
  "latest_failure": {
    "id": 12345,
    "name": "CI",
    "branch": "feat/my-fix",
    "commit_sha": "5c1d2e3...",
    "url": "https://github.com/..."
  },
  "latest_in_progress": {...},
  "runs": [...]
}
```

**AI 助手能读这个文件** 知道 CI 状态，无需联网。

### 2.3 `scripts/ci_notify.py` — 失败通知

```bash
python scripts/ci_notify.py
# 输出到 .novel2all/ci-alerts.json
# 只有新失败会被标记（去重）
```

适合：CI watch 守护进程每隔几分钟调一次，发现新失败就写到 `ci-alerts.json`。

---

## 3. 配置 GitHub Personal Access Token

### 3.1 公共仓库

**不需要 token**。任何工具都能查公共仓库的 workflow run 状态。

### 3.2 Private 仓库

1. 访问 https://github.com/settings/tokens/new
2. Note: `novel2all-ci-status`
3. Expiration: 90 days（可设短一点更安全）
4. Scopes: 只需 `repo:status`（只读 status），或 `actions:read`
5. Generate token
6. 复制 `ghp_xxx...`

### 3.3 设置环境变量

**Windows PowerShell**：
```powershell
$env:GITHUB_TOKEN = "ghp_xxxxx"
$env:NOVEL2ALL_REPO = "your-org/novel2all"
```

**Linux / macOS**：
```bash
export GITHUB_TOKEN="ghp_xxxxx"
export NOVEL2ALL_REPO="your-org/novel2all"
```

**永久化**（写进 .env）：
```bash
# .env (已在 .gitignore)
GITHUB_TOKEN=ghp_xxxxx
NOVEL2ALL_REPO=your-org/novel2all
```

---

## 4. AI 助手集成方案

### 4.1 方案 A：本地读文件（最简）

AI 助手只需要读 `.novel2all/ci-status.json` 文件。

```python
# AI 助手的伪代码
status = read_file(".novel2all/ci-status.json")
if status["summary"]["failure"] > 0:
    failure = status["latest_failure"]
    print(f"❌ CI 挂了：{failure['name']} on {failure['branch']}")
    print(f"   URL: {failure['url']}")
```

**你需要的**：
- 后台跑 `python scripts/ci_watch.py &`
- AI 助手能读 `.novel2all/ci-status.json`

### 4.2 方案 B：AI 助手主动调用脚本（推荐）

AI 助手用 Bash 工具跑 `ci_status.py`：

```python
# AI 助手伪代码
result = bash("cd /path/to/novel2all && python scripts/ci_status.py --json")
status = json.loads(result)
```

**你需要的**：
- AI 助手能调 Bash / Shell
- `GITHUB_TOKEN` 环境变量已设

### 4.3 方案 C：AI 助手直接 WebFetch（无需本地工具）

AI 助手用 WebFetch 直接调 GitHub API：

```python
# AI 助手伪代码
result = webfetch(
    "https://api.github.com/repos/your-org/novel2all/actions/runs?per_page=5",
    headers={"Authorization": "Bearer ghp_xxx"}
)
```

**你需要的**：
- AI 助手能 WebFetch
- 接受暴露 token 的风险

### 4.4 方案 D：CI 失败自动启动 AI 修复（高级）

```bash
# 配合 GitHub Webhook：
# 1. CI 失败 → webhook 触发本地服务
# 2. 本地服务调 AI 助手（WorkBuddy MCP / 自动化）
# 3. AI 助手读日志 → 改代码 → push 修复
```

需要 WorkBuddy / 自动化平台支持 webhook 集成。

---

## 5. 典型使用场景

### 场景 A：CI 挂了，用户让 WorkBuddy 看

```
用户：CI 挂了帮我看看

WorkBuddy：
  1. 跑：python scripts/ci_status.py --json
  2. 解析 → 发现 feat/my-fix 分支上 CI 失败
  3. 跑：python scripts/ci_status.py --run-id 12345
  4. 看 commit message 是 "feat: add xxx"
  5. git log -p 查看改动
  6. 修复 → git commit --amend + git push --force-with-lease
```

### 场景 B：用户想看最近 10 次 CI 状态

```
用户：最近 CI 状态怎么样

WorkBuddy：
  1. 跑：python scripts/ci_status.py
  2. 打印表格 → 显示 9 成功 / 1 失败
  3. 总结：最后一次失败是 feat/my-fix 分支，已修复
```

### 场景 C：CI 一直在跑，用户等结果

```
用户：CI 跑完没

WorkBuddy：
  1. 读 .novel2all/ci-status.json（如有 ci_watch 守护进程）
  2. 或跑：python scripts/ci_status.py
  3. 报告：⏳ 还在跑 / ✅ 跑通了 / ❌ 失败了
```

### 场景 D：用户要发新版

```
用户：发 v0.21.0

WorkBuddy：
  1. 跑：make verify-ci（确保本地 lint + test 通过）
  2. 跑：python scripts/ci_status.py（确认 main 分支 CI 绿）
  3. git tag v0.21.0 && git push --tags
  4. 监控 Release workflow：python scripts/ci_watch.py --interval 10
  5. 等 release workflow 跑完，确认 GitHub Release + PyPI + Docker 都发布
```

---

## 6. 快速启动

### 一次性查询

```bash
# 测试是否能连 GitHub
python scripts/ci_status.py

# 配 token 后再试
export GITHUB_TOKEN=ghp_xxx
python scripts/ci_status.py
```

### 后台守护进程（推荐）

```bash
# 启动（Windows PowerShell）
Start-Process -FilePath python -ArgumentList "scripts/ci_watch.py" -WindowStyle Hidden
Get-Process python | Where-Object { $_.MainWindowTitle -eq "" }

# 启动（Linux / macOS）
nohup python scripts/ci_watch.py > .ci_watch.log 2>&1 &
echo $! > .ci_watch.pid
```

### 配置到 Makefile（已加）

```bash
make ci-status        # 一次性查询
make ci-watch         # 后台守护进程
make ci-watch-stop    # 停守护进程
```

---

## 7. 故障排查

### 401 Unauthorized

```
[ERR] 401 Unauthorized — 需要 GITHUB_TOKEN（private 仓库）
```

解决：设置 `GITHUB_TOKEN` 环境变量。

### 404 Not Found

```
[ERR] 404 Not Found — 仓库 zenstory-ai/novel2all 不存在或 workflow 未启用
```

解决：
- 检查 `NOVEL2ALL_REPO` 设置是否正确
- 仓库确实启用了 GitHub Actions
- 仓库名 owner/repo 拼写正确

### Rate limit

GitHub API 限制：未认证 60 次/小时，认证 5000 次/小时。

`ci_watch.py` 默认 60 秒一次 = 60 次/小时（未认证刚好用满）。

解决：
- 设 `GITHUB_TOKEN` 提高配额
- 把 `--interval` 调大（如 300 秒 = 12 次/小时）

### Permission denied on Windows

```
PermissionError: [Errno 13] Permission denied: '.novel2all\\ci-status.json.tmp'
```

解决：CI watch 用 atomic rename（写 .tmp 再 rename）。如果还是有问题：
- 检查目录权限
- 关闭杀毒软件对 `.novel2all/` 的实时扫描

---

## 8. 安全建议

- ✅ PAT 设置过期时间（≤ 90 天）
- ✅ 只给 `actions:read` scope（不要给全权限）
- ✅ 用环境变量，不写进文件
- ✅ .gitignore 已覆盖 `.env` / `.env.local`
- ✅ 在 github 设置 token 撤销列表
- ⚠️ 不要把 token 贴进 issue / PR 描述
- ⚠️ private 仓库不要把 `ci-status.json` 提交进 git

---

## 9. 进阶：CI 失败自动修复

如果你想让 AI 助手**自动**修 CI 失败，可以这样做：

```bash
# 1. 安装 cron / scheduled task（每 5 分钟跑一次）
*/5 * * * * cd /path/to/novel2all && python scripts/ci_notify.py && python scripts/ai-fix-ci.py

# 2. ai-fix-ci.py 伪代码：
#    - 读 .novel2all/ci-alerts.json
#    - 如果有新失败：
#        - 用 WorkBuddy API 调 AI 分析失败日志
#        - AI 修改代码
#        - commit + push
#    - 把修复结果写到 .novel2all/fix-log.json
```

需要：
- WorkBuddy MCP 集成（或类似 AI 助手 API）
- 足够权限让 AI 改代码 + push
- 风险控制：不是所有失败都值得 AI 自动修

---

## 10. 相关资源

- GitHub Actions API: https://docs.github.com/en/rest/actions
- Personal Access Token: https://github.com/settings/tokens
- novel2all CI 配置: `.github/workflows/ci.yml`
- novel2all Release 配置: `.github/workflows/release.yml`
- novel2all DEPLOY: `docs/DEPLOY.md`
