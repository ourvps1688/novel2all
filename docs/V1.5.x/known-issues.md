# V1.5.x 已知问题跟踪

> **用途**：跟踪 V1.5.x React SPA 前端 + 后端的已知问题、临时解决方案、Sprint 归属。
>
> **维护**：每次发现新问题 → 加 issue；修复完成 → 移到 ✅ Resolved 段落（带 commit 引用）。

---

## 📋 当前 Sprint 状态

| Sprint | 版本 | 状态 | 主要页面 | 估时 |
|--------|------|------|---------|------|
| S1 | V1.5.1 | ✅ 完成 | Skill 浏览器 + 通用执行器 | 3 天 |
| S2 | V1.5.2 | ✅ 完成 + 补丁中 | 章节管理 + 写作（Tiptap + SSE 8 阶段）| 4 天 |
| **S3** | **V1.5.3** | **🔄 进行中** | **审查 + 去 AI 味 + 短篇 + 封面 + 设置** | **3 天** |
| S4 | V1.5.4 | ⏸️ 待办 | Admin + 导入 + Onboarding + 移动响应式 | 3 天 |
| S5 (预留) | V1.5.5 | ⏸️ 待办 | 扫榜 + 拆文 + i18n | ? |

---

## 🔧 Open Issues（未解决）

### Issue #1: 修复 Sprint 2 已知问题时"无限中断"
- **报告时间**：2026-09-16
- **报告人**：用户
- **症状 1**（首次报告）：开发 Sprint 2 修复时遇到"无限中断"（具体描述待补）
- **症状 2**（澄清，2026-09-16 20:30）：**"每次下了命令，agent 都自己中断工作，说是 bug 导致了任务中断"**（频率高 / 是 agent 行为中断）
- **AI 实测（2026-09-16 20:30）**：
  - 当前 Bash 工具运行良好，所有基本命令（git / python -c / heredoc / rmtree）正常通过
  - 唯一观察到 `⚠️ Sandbox bypassed (escalation-approved)` 警告（不阻塞但有警告）
- **7 类可能原因**：
  - A. Sandbox 拦截 + 越权请求（最可能，频率高，警告类）
  - B. Bash 工具 timeout（默认 120s）
  - C. 网络中断（curl / git push）
  - D. EPERM 文件权限（DACL 拒绝）
  - E. safe-delete-common.sh 钩子破坏 .git（低频但严重）
  - F. Bash shim 损坏（dirname not found）— memory 已记录修复，不再触发
  - G. 多步任务 context 超限 → AI 响应截断（高频，长任务）
- **下一步**：
  - [ ] 用户复现一次完整中断并贴 error message + 终端输出
  - [ ] 写 hook 监控 sandbox 拦截事件
  - [ ] 主动拆分长任务为多个 turn
- **归属**：Sprint 2 补丁 / V1.5.5 i18n 同步修复

### Issue #2: progress event payload schema 不匹配
- **报告时间**：2026-09-16（cleanup 阶段发现）
- **后端 SSE 发**：`{task_id, phase, message}` (e.g. `{phase: "save", message: "已写文件: ..."}`)
- **前端 `useSkillStream` 期望**：`{phase, chars_written, chars_per_second, eta_seconds, message}`
- **影响**：`chars_written` 永远是 0 → 进度条永远 0%
- **临时方案**：前端 fallback — `charsWritten = 累计 chunk 长度`
- **归属**：Sprint 3 实施时同步修复
- **修复**（commit 07d683c）：
  - useSkillStream.ts 加 FallbackState 累计 chunk 长度 + 计算 charsPerSecond/etaSeconds
  - SkillRunner.tsx 加 computeCombinedProgress — writing 阶段按字符数在 60%~75% 间插值
  - 进度条 + 字符数 + 字/秒 + 剩余秒 全部可见
  - 验证：TS 0 errors / Vite 11.92s / 11 tests passed

### Issue #3: V0.30.5 E2E playwright 测试 disabled
- **报告时间**：2026-09-16
- **症状**：`tests/e2e/test_web_ui_playwright_v0305.py` 测 `/static/alpine.min.js` 等老 HTMX 资源，V1.5.x 重构已删 `web/static/`，CI fail
- **临时方案**：ci.yml 加 `if: false` 禁用 e2e-playwright job
- **最终方案**：写 `tests/e2e/test_web_ui_v15x.py` 测 V1.5 React SPA 核心流程（Login → Dashboard → SkillsPage → SkillRunner → WritePage → ChapterEditor）
- **归属**：Sprint 4 配套

---

## ✅ Resolved（已修复，附 commit 引用）

| # | 问题 | 修复 commit | 修复方式 |
|---|------|------------|---------|
| R1 | 后端 SSE 流在 error/cancel 路径不 emit `done`，前端 `useSkillStream` 永远 loading | `22537ab` + `5e09bdf` + `68af8a7` | 在 `_run_skill_task` + execute endpoint + write_chapter_stream 4 条 except 路径（cancel / OutlineNotFound / BlockingIssues / generic Exception）都 emit `progress + done` |
| R8 | progress event 缺 chars_written/chars_per_second/eta_seconds → 进度条卡 60% | `07d683c` | 前端 fallback：useSkillStream 累计 chunk 长度 + 计时器算 cps/eta；SkillRunner 加 computeCombinedProgress 在 writing 阶段按字符数在 60%~75% 间插值 |
| R2 | ruff format 不合规导致 CI lint 失败 | `ca2ec69` | `ruff format` 自动修复 `src/novel2all/web/app.py` + `tests/unit/test_skills_execute_v151.py` |
| R3 | Sprint 2 自动保存 404 误报 | `da00b94` | project 未初始化时跳过 save + UX 提示 |
| R4 | V1.5 React CSP script-src 阻挡内联 FOUC 脚本 | `16b8ab7` | CSP 加 `'unsafe-inline'` |
| R5 | UserSchema.disabled 类型错 | `b4fdd3c` | boolean → number |
| R6 | Sprint 1.1 Zod enum + UI 13 cards contract mismatch | `d155c34` | 后端 enum 字符串化 + 前端 schema 同步 |
| R7 | Sprint 1 unmount ref + env var + 后端 SSE | `42f5733` | 多项 fix 合并 |

---

## 📅 Sprint 3 实施计划（V1.5.3）

按 PRD-V1.5.x.md §5 Sprint 3，目标 = **写作闭环完成**（写 → 审 → 优化 → 导出）+ 短篇 + 设置。

### 任务列表

1. **T07 ReviewQueuePage 完整实现**（估时 1 天）
   - 当前是 794B 占位
   - 4-agent 审查队列（架构 / 可读性 / 一致性 / 爽点）
   - verdict diff modal，每个 Issue 可跳转到对应段落
   - 接入 `POST /api/chapter/{n}/review` (Idempotency-Key)
   - 接入 `useReviewChapter()` hook（已存在的话）

2. **T08 SettingsPage 完整实现**（估时 0.5 天）
   - 当前 3.5KB（部分实现？）
   - 模型下拉（实时切换 `POST /api/model/switch`）
   - cache 命中率展示（`GET /api/cache/stats`）
   - 重置按钮（`POST /api/cache/prompt-stats/reset`）

3. **T08.2 ExportPage 完整实现**（估时 0.5 天）
   - 当前 812B 占位
   - 单章导出（md / txt / epub）
   - 整书导出 + 流式下载
   - 接入 `/api/chapter/{n}/export?format=...` 和 `/api/export`

4. **去 AI 味 skill UI 集成**（估时 0.5 天）
   - 选中文本 → 右键 "去 AI 味" → Diff 对比 → 一键替换
   - 复用 `useSkillStream` + `story-deslop` skill

5. **短篇 8 节 tab 视图**（估时 0.5 天）
   - 复用 `/write/:chapter` 但切换 short mode
   - 单独的 prompt 配置 + 8 节 tab

6. **Cover 生成**（估时 0.5 天，估时合并自 Sprint 3 计划）
   - `/cover` 页面或并入 `/skills/story-cover`
   - 输入书名/题材/文风 → 输出 prompt + 复制

### 优先级（按 user-level preference 效率优先）

按 PRD 顺序实施，**每个 page 完成后立即 commit + push**（避免累积 dev branch 大改动）。

### 验收标准（PRD §5 Sprint 3 原文）

1. 写作界面 "送审" 按钮 → 调 review API → 4-agent 报告展示
2. 报告 Issue 可点击跳到对应段落
3. 选中文本 → 右键 "去 AI 味" → Diff 对比 → 一键替换
4. `/cover` 输入书名/题材/文风 → 输出 prompt + 复制
5. `/settings` 切换模型后,后续 AI 调用使用新模型
6. Cache 命中率实时显示
7. 短篇模式 8 节结构生成可用
