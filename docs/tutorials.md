# novel2all Tutorials 索引

> **适用版本**：V1.0 GA
> **更新**：2026-09-14

novel2all 提供从入门到高级的完整教程路径。

---

## 🎓 入门（5 分钟读完）

### [quickstart.md](quickstart.md)

**15 分钟写出第一章**

从安装到导出第一章的完整流程：
- Step 1: 安装（Docker / 源码）
- Step 2: 登录
- Step 3: 初始化小说项目
- Step 4: 编辑创作设定
- Step 5: 编辑章节大纲
- Step 6: 写第一章
- Step 7: 查看结果 + 导出

---

## 🚀 进阶（30 分钟）

### [tutorial-cli.md](tutorial-cli.md)

**CLI 高级用法**

适合开发者 / Power User：
- 全部 CLI 命令（setup / write / review / rollback / export / cache / user / routing）
- 4 个实战案例（玄幻/短篇/拆文/去 AI 味）
- 配置文件（`.env`、`novel2all.toml`）
- 故障排查（写作失败/cache 不工作/4-agent 审查全 fail）
- Git 集成 + 自定义 skill

---

## 📚 概念理解

### [v0.30.6-summary.md](v0.30.6-summary.md)

**V0.30.6 收官报告**

理解项目当前的核心特性：
- **V0.30.6 B3** 实时进度条
- **V0.30.6 B6** 章节导出
- **V0.30.6 C1** Prompt prefix cache（节省 27%）
- **V0.30.6 B1** 4-agent 并行审查
- **V0.30.6 B2** 自动回滚
- **V0.30.6 B5** 多用户基础
- **V0.30.6 C3** 自适应路由

### [cache-tuning-guide.md](cache-tuning-guide.md)

**Cache 调优指南**

11 节生产部署调优：
- 4 backend 选择（memory/sqlite/redis/json）
- TTL 推荐（角色卡 0 / 细纲 24h / 完整章节 7 天）
- max_size 推荐（小调试 256 / 单本小说 1024 / 长期运行 4096）
- 性能基准（V0.47 4 backend benchmark）

### [next-steps-roadmap.md](next-steps-roadmap.md)

**路线图**

4 周冲刺 + 中期 + V1.0 + V2.0 路线。

---

## 🚢 部署

### [v1.0-docker-deploy.md](v1.0-docker-deploy.md)

**Docker 部署指南**

5 分钟 Docker 部署：
- 前置要求 + 快速部署
- 架构图（含 nginx + 反向代理）
- 环境变量表
- 持久化数据备份/恢复
- 升级流程
- 监控（健康检查 + 关键指标 + 日志）
- 安全清单 + 故障排查
- 卸载 + 反向代理示例

---

## 🔧 API 参考

启动 Web UI 后访问 `http://localhost:8000/docs`（FastAPI 自动生成 OpenAPI）。

### 主要端点

| 端点 | 用途 | 文档 |
|------|------|------|
| `POST /api/auth/login` | 登录 | V0.30.6 B5 |
| `POST /api/auth/logout` | 注销 | V0.30.6 B5 |
| `GET /api/auth/me` | 当前用户 | V0.30.6 B5 |
| `POST /api/write/stream` | 写章节（SSE） | V0.31 |
| `POST /api/write/cancel/{task_id}` | 取消写章节 | V0.31 |
| `GET /api/chapter/{n}/export?format=md\|txt\|epub` | 导出章节 | V0.30.6 B6 |
| `POST /api/chapter/{n}/review` | 4-agent 审查 | V0.30.6 B1 |
| `POST /api/chapter/{n}/rollback` | 手动回滚 | V0.30.6 B2 |
| `GET /api/cache/stats` | Cache 统计 | V0.30 |
| `GET /api/cache/recommend` | Cache 智能推荐 | V0.51 |
| `GET /api/cache/prompt-stats` | Prompt prefix cache | V0.30.6 C1 |

---

## 🏗️ 架构

### [ARCHITECTURE.md](ARCHITECTURE.md)

项目架构（待 V1.0 GA 后完善）。

---

## 📝 其他

### [DECISIONS.md](DECISIONS.md)

技术决策记录（ADR 风格）。

### [ROADMAP.md](ROADMAP.md)

历史路线图（含早期版本）。

### [CI-INTEGRATION.md](CI-INTEGRATION.md)

CI 集成指南。

---

## 🎯 按角色推荐路径

### 新用户（第一次用）
1. [quickstart.md](quickstart.md) — 15 分钟跑通
2. 创作 1-2 本小说
3. 遇到问题查 [tutorial-cli.md 第 5 节](tutorial-cli.md#5-故障排查)

### 开发者（想贡献代码）
1. [quickstart.md](quickstart.md) — 了解整体流程
2. [v0.30.6-summary.md](v0.30.6-summary.md) — 了解当前架构
3. [ARCHITECTURE.md](ARCHITECTURE.md) — 深入架构
4. [next-steps-roadmap.md](next-steps-roadmap.md) — 看未来方向

### 运维（要部署生产环境）
1. [v1.0-docker-deploy.md](v1.0-docker-deploy.md) — 5 分钟部署
2. [cache-tuning-guide.md](cache-tuning-guide.md) — Cache 调优
3. [tutorial-cli.md 第 5 节](tutorial-cli.md#5-故障排查) — 故障排查

### 产品经理（想了解功能）
1. [v0.30.6-summary.md](v0.30.6-summary.md) — 当前特性
2. [next-steps-roadmap.md](next-steps-roadmap.md) — 路线图
3. [v1.0-docker-deploy.md](v1.0-docker-deploy.md) — 部署清单

---

## 📚 推荐阅读顺序

```
quickstart.md (15 分钟)
   ↓
v0.30.6-summary.md (30 分钟) — 了解核心特性
   ↓
cache-tuning-guide.md (15 分钟) — 性能调优
   ↓
tutorial-cli.md (30 分钟) — 进阶用法
   ↓
v1.0-docker-deploy.md (15 分钟) — 生产部署
   ↓
ARCHITECTURE.md (60 分钟) — 深入架构
```

总阅读时间约 3 小时，足够深入理解 novel2all。

---

## 📞 获取帮助

- **GitHub Issues**：https://github.com/ourvps1688/novel2all/issues
- **Email**：ourvps1688@example.com
- **Web UI Docs**：http://localhost:8000/docs
