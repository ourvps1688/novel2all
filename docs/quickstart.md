# novel2all Quickstart（15 分钟写出第一章）

> **目标**：从 0 到写出第一章 AI 创作的小说
> **预计时间**：15 分钟
> **前置**：Python 3.12+ + 一个 LLM API key（推荐 DeepSeek，便宜 + 中文强）

---

## Step 1: 安装（2 分钟）

### 方式 A：Docker（推荐）

```bash
# 1. 克隆
git clone https://github.com/ourvps1688/novel2all.git
cd novel2all

# 2. 设置环境变量
export NOVEL2ALL_ADMIN_USER=admin
export NOVEL2ALL_ADMIN_PASS=your_secure_password_here
export DEEPSEEK_API_KEY=sk-xxxxx

# 3. 启动
docker-compose up -d

# 4. 访问 http://localhost:8000
```

### 方式 B：源码

```bash
# 1. 克隆
git clone https://github.com/ourvps1688/novel2all.git
cd novel2all

# 2. 用 uv 装依赖（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-extras --dev

# 或用 pip
pip install -e .

# 3. 设置环境
export NOVEL2ALL_ADMIN_USER=admin
export NOVEL2ALL_ADMIN_PASS=your_secure_password_here
export DEEPSEEK_API_KEY=sk-xxxxx

# 4. 启动 Web UI
uvicorn novel2all.web.app:create_app --factory --reload
# 访问 http://localhost:8000
```

---

## Step 2: 登录（1 分钟）

打开浏览器访问 `http://localhost:8000`，会自动重定向到 `/login`：

1. **用户名**：填你设置的 `NOVEL2ALL_ADMIN_USER`（默认 `admin`）
2. **密码**：填你设置的 `NOVEL2ALL_ADMIN_PASS`
3. 点击「登录」

成功后会自动跳转到首页。

---

## Step 3: 初始化小说项目（3 分钟）

在 Web UI 首页（项目状态 dashboard）：

1. 点击「创建项目」或调用 CLI：
   ```bash
   novel2all setup --name "我的小说" --genre "玄幻" --style "古风古韵"
   ```

2. **设置项目目录**（默认 `./projects/我的小说/`）：
   - `创作设定.md`（必填）— 整体设定
   - `设定/角色/*.md`（必填）— 角色档案
   - `设定/文风.md`（必填）— 文风指南
   - `设定/世界观.md`（可选）— 世界观

3. **Web UI 自动识别**项目目录后，会显示：
   - 角色卡片网格
   - 伏笔面板
   - 章节列表

---

## Step 4: 编辑创作设定（3 分钟）

打开 `创作设定.md`，V0.30.6 自动生成模板：

```markdown
# 我的小说

## 类型
玄幻

## 风格
古风古韵

## 主角
- 林雷：18岁剑客，性格坚毅，目标是成为最强剑客
- 萧炎：20岁配角，林雷的挚友，火系魔法师

## 世界观
- 苍茫大陆：剑道与魔法并存
- 苍茫镇：故事起点，林雷的故乡
- 等级划分：筑基 → 金丹 → 元婴 → 化神 → 渡劫 → 仙人

## 主要矛盾
林雷的家族被仇家灭门，他必须崛起复仇。
```

> **关键**：设定越详细，AI 写出的章节质量越高（V0.23 verifier 会检查一致性）。

---

## Step 5: 编辑章节大纲（2 分钟）

打开 `大纲/细纲_第001章.md`：

```markdown
# 第1章 林雷的觉醒

## 场景
苍茫镇外的荒山，林雷发现一处神秘遗迹。

## 关键情节点
1. 林雷与萧炎在荒山探险
2. 发现被封印的古老剑碑
3. 林雷触碰剑碑，意外觉醒血脉
4. 第一场战斗：击败山贼
5. 结尾：林雷决定离开苍茫镇

## 角色
- 林雷（主角，本章成长：从迷茫少年 → 觉醒者）
- 萧炎（配角，本章作用：见证 + 推动）
- 山贼（次要，本章作用：引出战斗）

## 风格
- 古风古韵（参考《诛仙》《凡人修仙传》）
- 第一人称内心独白 + 第三人称叙事
```

---

## Step 6: 写第一章（4 分钟）

### 方式 A：Web UI（推荐）

1. 点击「写新章节」或访问 `/write/1`
2. 选择 skill：`story-long-write`（长篇，默认）
3. 设置最低字数：2000
4. 点击「开始写作」

实时显示进度（V0.30.6 B3）：

```
✓ 初始化（init）
✓ 写前检查（pre_write_check）— 0 个 critical 问题
▸ 写作中（writing）— 845 / 2000 字（42%）| 字秒: 28
⏳ 保存（save）
⏳ 提取（extract）
⏳ 合并（merge）
⏳ 写后检查（post_write_check）
⏳ 完成（done）
```

### 方式 B：CLI

```bash
novel2all write chapter 1
# 流式输出到 console，写完后自动 extract + merge
```

### 写作完成后

- **自动保存**到 `正文/第001章.md`
- **自动提取**（角色/伏笔/时间线）到 `_tracking-state.json`
- **自动 4-agent 审查**（V0.30.6 B1）
- **如果 verdict=fail** → **自动回滚**（V0.30.6 B2）
- **记录到 AdaptiveRouter**（V0.30.6 C3，下次选历史最佳模型）

---

## Step 7: 查看结果（1 分钟）

### Web UI 仪表盘

| 面板 | 内容 |
|------|------|
| **Cache 状态** | hits / misses / hit_rate / 节省 |
| **Prompt Cache** | sys_hash 复用率 / ¥ 节省 |
| **角色** | 林雷 / 萧炎 卡片（含 description） |
| **伏笔** | 5 个新伏笔（如「剑碑的来源」） |
| **章节** | 第001章 已完成 |

### 导出章节

V0.30.6 B6：导出为 Markdown / TXT / EPUB：

```bash
# Markdown
curl -o chapter1.md http://localhost:8000/api/chapter/1/export?format=md

# EPUB（可在 Kindle 阅读）
curl -o chapter1.epub http://localhost:8000/api/chapter/1/export?format=epub

# TXT
curl -o chapter1.txt http://localhost:8000/api/chapter/1/export?format=txt
```

---

## 下一步

- **第 2 章**：写下一章，AI 会自动用 AdaptiveRouter 选最佳模型
- **批量写**：在 Web UI 点击「批量写」可一次写 5-10 章
- **手动审查**：`POST /api/chapter/{n}/review` 重新跑 4-agent 审查
- **手动回滚**：`POST /api/chapter/{n}/rollback` 恢复到上一次备份

---

## 常见问题

### Q: 写章节时报 401 / 403？

A: 重新登录（Session cookie 7 天过期）。或检查 admin 凭证是否正确：
```bash
# Docker 环境
docker-compose logs web | grep "admin"
```

### Q: 4-agent 审查一直 fail，怎么调整？

A: 编辑 `创作设定.md` 让设定更详细，或调整 `state/style_anchor`。verdict 阈值在 `core/memory/multi_reviewer.py`。

### Q: Docker 启动失败？

A: 检查环境变量：
```bash
docker-compose logs web
# 常见错误：NOVEL2ALL_ADMIN_PASS 未设置
```

---

## 完整文档索引

- **架构总览**：[docs/ARCHITECTURE.md](ARCHITECTURE.md)
- **Docker 部署**：[docs/v1.0-docker-deploy.md](v1.0-docker-deploy.md)
- **Cache 调优**：[docs/cache-tuning-guide.md](cache-tuning-guide.md)
- **V0.30.6 收官报告**：[docs/v0.30.6-summary.md](v0.30.6-summary.md)
- **V1.0 GA 路线图**：[docs/next-steps-roadmap.md](next-steps-roadmap.md)

---

**🎉 恭喜！15 分钟写出第一章！**

继续写更多章节，让 AdaptiveRouter 自动优化你的模型选择。
