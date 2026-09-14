# novel2all CLI 教程（高级用户）

> **目标**：用 novel2all CLI 完成完整创作流（初始化 → 写 → 审查 → 导出）
> **预计时间**：30 分钟
> **前置**：Quickstart 完成 + 已写至少 1 章

---

## 1. CLI 安装

```bash
# 方式 A：源码安装（推荐，dev 模式）
uv sync --all-extras --dev
uv run novel2all --help

# 方式 B：Docker exec（生产）
docker-compose exec web novel2all --help
```

---

## 2. 核心命令

### 2.1 项目管理

```bash
# 初始化项目
novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"

# 查看项目信息
novel2all status

# 项目列表
novel2all projects list
```

### 2.2 写作

```bash
# 写第 1 章（流式输出）
novel2all write chapter 1

# 指定 skill
novel2all write chapter 1 --skill story-long-write

# 指定最低字数
novel2all write chapter 1 --min-chars 3000

# 跳过 pre-write check（速度优先）
novel2all write chapter 1 --skip-pre-write

# 批量写（第 1-5 章）
novel2all write chapters 1-5 --interval 30  # 每章间隔 30 秒（避免 rate limit）
```

### 2.3 审查与回滚

```bash
# 4-agent 审查（第 N 章）
novel2all review chapter 5

# 仅显示 critical issues
novel2all review chapter 5 --severity critical

# 输出 JSON 格式
novel2all review chapter 5 --json

# 手动回滚
novel2all rollback chapter 5 --reason "用户手动撤回"
```

### 2.4 导出

```bash
# 导出单章节
novel2all export chapter 1 --format md     # Markdown
novel2all export chapter 1 --format txt    # TXT
novel2all export chapter 1 --format epub   # EPUB 3.0

# 导出整本书
novel2all export book --format epub --title "我的小说" --author "我"

# 批量导出到目录
novel2all export book --format md --output ./exports/
```

### 2.5 Cache 管理

```bash
# 查看 Cache 状态
novel2all cache stats

# Cache 智能推荐
novel2all cache recommend

# 清理 7 天前的 .bak 备份
novel2all cache cleanup

# 清空 Cache（危险！不可恢复）
novel2all cache clear --confirm
```

### 2.6 用户管理（B5 多用户）

```bash
# 创建新用户
novel2all user create --username alice --password alice123 --role editor

# 列所有用户
novel2all user list

# 删除用户
novel2all user delete alice

# 授权项目访问
novel2all user grant --user alice --project /path/to/proj --role editor

# 撤销项目访问
novel2all user revoke --user alice --project /path/to/proj
```

### 2.7 AdaptiveRouter 数据

```bash
# 查看所有 task 的模型统计
novel2all routing stats

# 查看特定 task 的模型
novel2all routing show --task writing

# 清空历史数据（reset）
novel2all routing clear --confirm
```

---

## 3. 实战案例

### 案例 1：从零写玄幻小说

```bash
# Step 1: 初始化
cd ~/my-novels
novel2all setup --name "苍茫纪" --genre "玄幻" --style "古风古韵"

# Step 2: 编辑设定（手动）
vim 苍茫纪/创作设定.md  # 写主角/世界观/矛盾
vim 苍茫纪/设定/角色/林雷.md  # 写主角详细设定
vim 苍茫纪/设定/文风.md  # 写文风指南

# Step 3: 写大纲
vim 苍茫纪/大纲/细纲_第001章.md  # 第1章细纲
vim 苍茫纪/大纲/细纲_第002章.md  # 第2章细纲
...  # 至少 5 章

# Step 4: 批量写
cd 苍茫纪
novel2all write chapters 1-5 --min-chars 2500

# Step 5: 审查（自动 + 手动）
novel2all review chapter 5  # 看 4-agent 审查结果

# Step 6: 导出
novel2all export book --format epub --title "苍茫纪 第一卷" --author "我"
```

### 案例 2: 短篇创作

```bash
# 短篇 skill（不同 prompt）
novel2all setup --name "短篇集" --genre "都市" --style "现实主义"
novel2all write chapter 1 --skill story-short-write --min-chars 800

# 短篇通常 1-3 章
novel2all write chapters 1-3 --skill story-short-write
```

### 案例 3: 已有小说分析

```bash
# 用 analyze skill 拆文（角色/情节/风格）
novel2all analyze chapter 1 --skill story-long-analyze

# 输出角色卡 + 伏笔列表
novel2all analyze chapter 1 --output ./analysis/
```

### 案例 4: 去 AI 味（V0.30.6 + V0.21 story-deslop skill）

```bash
# 用 deslop skill 重新写章节（更自然）
novel2all deslop chapter 5
# → 输出 .deslopped/第005章.md
```

---

## 4. 配置文件

### 4.1 `.env`

```bash
# 必填
NOVEL2ALL_ADMIN_USER=admin
NOVEL2ALL_ADMIN_PASS=secret
DEEPSEEK_API_KEY=sk-xxxxx

# 可选
NOVEL2ALL_MODEL=deepseek/deepseek-flash       # 默认模型
NOVEL2ALL_LLM_CACHE_ENABLED=true
NOVEL2ALL_LLM_CACHE_BACKEND=sqlite           # memory/sqlite/redis/json
NOVEL2ALL_LLM_CACHE_TTL=86400                # 24 小时
NOVEL2ALL_LLM_CACHE_MAX_SIZE=1024
```

### 4.2 项目配置 `novel2all.toml`（可选）

```toml
[project]
name = "我的小说"
genre = "玄幻"
style = "古风古韵"
min_chars_per_chapter = 2000

[llm]
default_model = "deepseek/deepseek-flash"
fallback_model = "deepseek/deepseek-chat"
auto_review = true  # V0.30.6 B1 自动 4-agent 审查
auto_rollback = true  # V0.30.6 B2 verdict=fail 自动回滚

[cache]
backend = "redis"
ttl = 86400

[routing]  # V0.30.6 C3 自适应路由
strategy = "best_avg"  # best_avg/best_quality/best_speed/best_success
min_samples = 5
```

---

## 5. 故障排查

### 5.1 写作失败

```bash
# 查看错误日志
novel2all logs tail --lines 100

# 启用 debug 日志
NOVEL2ALL_LOG_LEVEL=DEBUG novel2all write chapter 1

# 检查 LLM API key
echo $DEEPSEEK_API_KEY | head -c 10
```

### 5.2 Cache 不工作

```bash
# 验证 cache 状态
novel2all cache stats

# 重新生成推荐
novel2all cache recommend

# 切换 backend
NOVEL2ALL_LLM_CACHE_BACKEND=sqlite novel2all web
```

### 5.3 4-agent 审查全 fail

```bash
# 查看具体 issues
novel2all review chapter 5 --severity critical --verbose

# 调整设定（增加角色 description / 风格 anchor）
vim 设定/角色/林雷.md  # 让 description 更详细
```

---

## 6. 进阶

### 6.1 完整小说生成（自动化）

```bash
# 自动生成 50 章（实验性，可能需要手动调整）
for i in $(seq 1 50); do
    novel2all write chapter $i --min-chars 2500
    sleep 60  # 避免 rate limit
done

# 导出整本书
novel2all export book --format epub --output ./book.epub
```

### 6.2 与 Git 集成

```bash
# 写完一章后自动 commit
cat > .git/hooks/post-write.sh << 'EOF'
#!/bin/bash
git add 正文/ 大纲/ _tracking-state.json
git commit -m "write: $1 - $(date +%Y%m%d)"
EOF
chmod +x .git/hooks/post-write.sh
```

### 6.3 自定义 Skill

参考 `src/novel2all/skills/` 目录结构创建自己的 skill：

```
my_skill/
├── SKILL.md           # 元信息 + 用途
├── prompt.md          # prompt 模板
└── examples/          # few-shot examples
```

---

## 7. 参考

- **Web UI 教程**：[docs/quickstart.md](quickstart.md)
- **Docker 部署**：[docs/v1.0-docker-deploy.md](v1.0-docker-deploy.md)
- **API 参考**：访问 Web UI 后看 http://localhost:8000/docs
- **V0.30.6 收官报告**：[docs/v0.30.6-summary.md](v0.30.6-summary.md)
