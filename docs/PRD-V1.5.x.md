# novel2all V1.5.x PRD — 基于后端能力的前端实现规划

> 版本: V1.5.x 系列规划
> 后端基线: V1.5.0 (FastAPI + 13 skills + 7 roles + 44 API)
> 前端基线: V1.5.0 React SPA (login + dashboard 4 卡 + WritePage textarea + 5 placeholder)
> 写作者: Alice (Product Manager)
> 写于: 基于现有后端能力,规划前端分 sprint 实现路径

---

## 0. TL;DR

novel2all 后端能力**远超当前 V1.5.0 前端所能承载**——13 个 skill 中只有 1 个 (story-long-write) 有最简 textarea UI,其余 12 个完全无 UI;7 个 role 只在 review API 内部使用,前端不可见;44 个 API 中前端的 useSSE 只调了 `/api/write/stream` 与 `/api/chapter/{n}/save` 两个。

V1.5.x 目标: **让 13 个 skill 全部可触达 + 让长/短篇作者完成「选题材 → 拆文/扫榜 → 写 → 审 → 导出」闭环 + 让 admin 能管用户/项目/审计**。

---

## 1. 用户角色 (Personas)

### Persona A — 新用户 / Onboardee

| 维度 | 描述 |
|------|------|
| **典型** | 网文爱好者,从公众号/B站/朋友处听说 novel2all,想试试 AI 写网文 |
| **技术能力** | 一般,懂浏览器,不懂 Git/CLI |
| **痛点** | 不知道 novel2all 能干啥;不知道怎么开始 |
| **成功标志** | 5 分钟内能创建一个空项目,看到页面友好,想留下来 |
| **关键诉求** | 引导式 onboarding + 模板化起步 + 通俗语言 |

### Persona B — 长篇作者 / Long-form Writer

| 维度 | 描述 |
|------|------|
| **典型** | 起点/番茄长篇连载作者,日更 4000-10000 字,管理 50-300 章 |
| **技术能力** | 中等,会用 Markdown/Word |
| **痛点** | 长篇一致性崩塌(前后矛盾);AI 续写接不上剧情;管理多章节成本高 |
| **成功标志** | 用 5 层 memory 写出 50 章以上无重大前后矛盾;每章 8000+ 字 |
| **关键诉求** | 章节管理强;上下文自动加载;AI 续写可控可改;审稿可视化 |

### Persona C — 短篇作者 / Short-form Writer

| 维度 | 描述 |
|------|------|
| **典型** | 知乎盐言/番茄短篇/七猫短篇创作者,单篇 3000-8000 字,需情绪钩子+反转 |
| **技术能力** | 一般 |
| **痛点** | 反转生硬;情绪曲线平淡;8 节结构总写飞;平台调性差异(盐言深度 vs 番茄爽文) |
| **成功标志** | 单篇能在 1-2 小时内完成 8 节结构 + 情绪钩子 + 强反转 + 标题党 |
| **关键诉求** | 平台调性预设;短篇结构化模板;反转点提示;封面 prompt 一键生成 |

### Persona D — 策划者 / Strategist

| 维度 | 描述 |
|------|------|
| **典型** | 编辑/工作室策划/写之前要做大量调研的作者 |
| **技术能力** | 中等,熟悉数据分析 |
| **痛点** | 不知道什么题材火;竞品怎么写;题材生命周期;平台分布 |
| **成功标志** | 用扫榜(scan)+ 拆文(analyze) 拿到可执行选题报告,1 小时内出选题 |
| **关键诉求** | 扫榜数据可视化;拆文结构化输出;题材热度时间序列;跨平台对比 |

### Persona E — Admin / 管理员

| 维度 | 描述 |
|------|------|
| **典型** | novel2all 部署方/工作室 IT |
| **技术能力** | 高 |
| **痛点** | 用户失控;项目授权混乱;审计难追责 |
| **成功标志** | 5 分钟创建/禁用一个用户;给用户分配项目;看审计日志判定异常 |
| **关键诉求** | 用户 CRUD;项目授权矩阵;审计日志查询与导出 |

---

## 2. 功能矩阵 (Feature Matrix)

> 优先级定义:**P0** = 必须有(用户能用 skill); **P1** = 应该有(核心闭环); **P2** = 锦上添花(效率优化)

### 2.1 Skill 功能矩阵

| Skill | 目标 Persona | 前置条件 | 用户输入 | 系统输出 | 触发 UI | 结果展示 | 优先级 |
|-------|--------------|----------|----------|----------|---------|----------|--------|
| **story** (路由入口) | A | 已登录 | 自由文本需求 | 推荐具体 skill + 自动路由执行 | Dashboard "我想..." 输入框 | 推荐卡片 → 跳到对应 skill | P1 |
| **story-setup** | A, B, C | 已登录 + 项目路径 | 项目名/题材/平台/笔名 | `_tracking-state.json` + 模板项目结构 | Onboarding 向导 第 1 步 | 创建成功 toast + 跳到主页 | **P0** |
| **story-import** | A, B | 已登录 + 项目路径 | 已存在的 .txt/.md/.docx 路径 | 反向解析出的项目结构 + 章节拆分 | Dashboard "导入已有小说" 按钮 | 导入报告 + 跳到章节列表 | P1 |
| **story-long-write** | B | 已 setup + 有项目根 | 章节 prompt + 项目根 + 章节号 | 一章内容 (SSE 流式,8 阶段进度) | `/write/:chapter` 主按钮 "AI 续写" | Tiptap 流式填充 + 阶段进度条 | **P0** |
| **story-long-analyze** | D | 已 import 或有 chapters | 选 1-N 章 | 黄金三章 + 爽点密度 + 节奏曲线 + 文风 | 章节列表右键 "拆文" / 工具栏 | 多 tab 报告(摘要/爽点/节奏/文风) | P1 |
| **story-long-scan** | D | 无(全局 skill) | 题材关键词 + 时间范围 | 题材分布 + 新题材信号 + 篇幅/更新模式 | `/skills/story-long-scan` 独立页 | Recharts 图表 + 题材列表 | P1 |
| **story-short-write** | C | 已 setup (短篇模式) | 主题/情绪钩子 + 平台 | 8 节结构 + 每节正文 (SSE 流式) | `/write/short/:session` | 8 节 tab + AI 续写 | **P0** |
| **story-short-analyze** | D, C | 已 import 短篇 或粘贴文本 | 短篇全文 | 故事核 + 情感线 + 反转点 + 共鸣强度 | 短篇编辑器 "分析" 按钮 | 报告卡片 + 可点击锚点跳转 | P1 |
| **story-short-scan** | D | 无(全局 skill) | 平台(盐言/番茄/七猫) + 分类 | 平台热度 + 标题模板 + 套路库 | `/skills/story-short-scan` 独立页 | 平台对比表 + 套路列表 | P2 |
| **story-cover** | B, C | 有项目根 | 书名 + 题材 + 文风关键词 | 封面 prompt (英文,可接 MJ/SD) | 项目设置 "封面" 按钮 | Prompt 文本框 + 复制按钮 + 调 browser-cdp 预览 | P1 |
| **story-deslop** | B, C | 有选中文本 | 选中的章节段落 | 去 AI 味后的同义改写 | 编辑器右键 "去 AI 味" | Diff 对比 + 一键替换 | **P0** |
| **story-review** | B, C 内部 | 有 chapter content | 章节号 + Idempotency-Key | 4-agent 报告 (架构/可读性/一致性/爽点) | 编辑器 "送审" 按钮 | 报告 modal + Issue 列表 + QualityScore | **P0** |
| **browser-cdp** | (内部) | 无 | URL + 抓取规则 | 结构化文本 | 不暴露 UI | 后端用 | (P-infra) |

### 2.2 非 Skill 功能矩阵

| 功能 | 目标 Persona | 前置条件 | 用户输入 | 系统输出 | 触发 UI | 优先级 |
|------|--------------|----------|----------|----------|---------|--------|
| 登录/登出 | All | 无 | username + password | JWT cookie | `/login` | **P0** |
| 当前用户信息 | All | 已登录 | - | user info | AppBar 头像 | **P0** |
| 章节 CRUD | B, C | setup 完成 | 章节号/标题/正文 | chapters list | `/chapters` | **P0** |
| 章节导出 | B, C | 有 chapter content | format (txt/md/epub) | 下载文件 | 章节列表 "导出" | P1 |
| 章节 AI 插入段落 | B, C | 有选区 | 选中文本 + 指令 | 插入文本 | 编辑器右键 "AI 插入" | P1 |
| 章节 AI 重写选区 | B, C | 有选区 | 选中文本 + 指令 | 替换文本 | 编辑器右键 "AI 重写" | P1 |
| 写作流式 SSE | B, C | 有 project root | prompt + project_path | SSE events | `/write` 主操作 | **P0** |
| 模型切换 | All | 已登录 | model name | 切换生效 | `/settings` 模型下拉 | P1 |
| 模型列表 | All | 已登录 | - | 可用模型 + 当前 | `/settings` | P1 |
| Cache 统计 | D, Admin | 已登录 | - | cache stats | Dashboard | P2 |
| 用户管理 (CRUD) | Admin | admin role | username/password/admin | user 对象 | `/admin/users` | P1 |
| 项目授权 | Admin, A | 已登录 | username + project path | share record | 项目设置 "分享" | P2 |
| 审计日志 | Admin | admin role | filters | audit records | `/admin/audit` | P2 |

---

## 3. 核心页面 (IA + 路由 + 字段表)

### 3.1 全局 IA

```
novel2all
├── /login                     公开
└── AppShell (已登录)
    ├── AppBar (logo + 用户菜单 + 模型切换器)
    ├── Sidebar (可折叠)
    │   ├── Dashboard (/)
    │   ├── Skills (/skills)
    │   ├── Chapters (/chapters)
    │   ├── Write (/write 或 /write/:chapter)
    │   ├── Review (/review)
    │   ├── Cover (/cover 或并入 /skills/story-cover)
    │   ├── Settings (/settings)
    │   ├── Import (/import)
    │   └── Admin (/admin/users, /admin/audit) [仅 admin]
    └── Main Content
```

### 3.2 页面字段表

| 路由 | 页面 | 主要功能 | 调用 API | 关键字段/组件 |
|------|------|---------|----------|--------------|
| `/login` | 登录页(已实现) | 用户名密码登录 | `POST /api/auth/login` | username, password, rememberMe |
| `/` | Dashboard(已实现,需扩展) | 4 卡片 + 快捷入口 | `GET /api/auth/me`, `GET /api/cache/stats`, `GET /api/cache/prompt-stats`, `GET /api/tracking` | 最近项目、Cache 命中率、活跃写作 task、最近审稿 |
| `/skills` | **Skill 浏览器**(新建) | 卡片网格展示 13 个 skill,按分类分组 | `GET /api/skills` | name, description, category, version, lastRun |
| `/skills/:name` | **Skill 执行页**(新建) | 输入 prompt + 配置 → 调 execute → SSE 流式输出 | `POST /api/skills/{name}/execute`, `GET /api/skills/{name}/status` | skillName, params (JSON), outputStream, statusBadge |
| `/chapters` | **章节列表**(新建) | 表格 + 拖拽排序 + 批量操作 | `GET /api/chapters`, `GET /api/tracking`, `GET /api/outlines` | chapter_no, title, word_count, status, updated_at |
| `/write` 或 `/write/:chapter` | **写作主界面**(扩展) | Tiptap + 工具栏 + AI 续写/重写/插入/审稿 + SSE 8 阶段 | `GET /api/write/active`, `POST /api/write/stream` (SSE), `POST /api/chapter/{n}/save`, `POST /api/chapter/{n}/insert`, `POST /api/chapter/{n}/rewrite`, `POST /api/chapter/{n}/review` | editor, toolbar, progressStepper, reviewPanel |
| `/review` | **审查队列**(新建) | 所有章节的 4-agent 审稿状态 | `GET /api/chapter/{n}/review`, 本地存历史 | chapter_no, overallScore, issues[架构/可读性/一致性/爽点], status (pass/warn/fail) |
| `/cover` | **封面生成**(新建,或并入 setup) | 书名 + 题材 → prompt → 调 MJ/SD/本地 SD | `POST /api/skills/story-cover/execute` | bookTitle, genre, style, promptText, copyButton |
| `/import` | **导入向导**(新建) | 选文件 → 解析 → 确认 | `POST /api/skills/story-import/execute` | filePath, detectedChapters[], confirmMapping |
| `/settings` | **设置**(新建) | 模型切换 + cache 配置 + 创作设定编辑 | `GET /api/models`, `GET /api/model/current`, `POST /api/model/switch`, `GET /api/skills` (用于编辑 prompt template) | modelSelect, cacheConfigForm, promptTemplateEditor |
| `/admin/users` | **用户管理**(新建,仅 admin) | CRUD + 角色 | `GET /api/auth/users`, `POST /api/auth/users`, `DELETE /api/auth/users/{id}` | users[], createForm, deleteConfirm |
| `/admin/audit` | **审计日志**(新建,仅 admin) | 查询 + 过滤 + 导出 | `GET /api/auth/audit` | auditRecords[], filters, exportBtn |
| `/admin/projects` | **项目授权**(新建,仅 admin) | 用户 ↔ 项目 矩阵 | `POST /api/auth/projects/{path}/share`, `DELETE /api/auth/projects/{path}/share/{user_id}`, `GET /api/auth/projects/{user_id}/projects` | users[], projects[], shareMatrix |

---

## 4. 用户流程 (User Flows)

### 4.1 Persona A — 新用户 Onboarding

```
1. 访问 /login → 输入凭据 → 登录成功 → 进入 /
2. Dashboard 显示空状态 + "🎉 欢迎使用 novel2all,创建你的第一个项目"
3. 点 "创建项目" → 进入 /import 或 /skills/story-setup
4. Onboarding 向导:
   Step 1: 项目基础信息 (项目名/笔名/题材)
   Step 2: 写作类型选择 (长篇 / 短篇 / 不确定)
   Step 3: 平台预设 (起点 / 番茄 / 盐言 / 七猫 / 不限)
   Step 4: 创作设定提示(可后补)
5. 提交 → POST /api/skills/story-setup/execute → 成功后跳 /chapters
6. 空章节列表 + "开始写第一章" 按钮
```

### 4.2 Persona B — 长篇作者写一章

```
1. 进入 /write/:chapter (默认章节号)
2. Tiptap 加载已有内容(若有)
3. 在工具栏选 "AI 续写"
4. 弹出 prompt 输入框:
   - 章节大纲
   - 关键转折点
   - 上文要点
   - 字数目标
5. 提交 → POST /api/write/stream (SSE)
6. 8 阶段进度条:
   ①加载上下文 → ②分析记忆 → ③生成大纲 → ④填充正文
   ⑤一致性检查 → ⑥去 AI 味 → ⑦审稿预览 → ⑧完成
7. 流式文本填入 Tiptap,实时 word count
8. 完成后: "保存" → POST /api/chapter/{n}/save
9. 自动触发: "是否送审?" → POST /api/chapter/{n}/review (Idempotency-Key)
10. 审稿结果 → review modal → 接受/修改/忽略
11. "导出" → 选择格式 → POST /api/chapter/{n}/export?format=md|txt|epub → 下载
```

### 4.3 Persona C — 短篇作者写 8 节短篇

```
1. 进入 /skills/story-short-write (或 setup 时选短篇 → 自动跳)
2. 输入: 主题 / 情绪钩子 / 平台 (盐言/番茄/七猫)
3. 提交 → SSE 流式生成 8 节结构骨架
4. 进入 8 节 tab 视图:
   - Tab 1-8 各自一个简化编辑器
   - 每节可单独 AI 续写/重写/插入
5. 全篇预览 (横向串联 8 节)
6. 自动触发去 AI 味 + 短篇分析 (故事核/反转/共鸣)
7. 导出 + 一键生成封面 prompt
```

### 4.4 Persona D — 策划者扫榜 + 选题

```
1. 进入 /skills/story-long-scan 或 /skills/story-short-scan
2. 选择平台 + 时间范围 + 题材关键词
3. 提交 → 后端扫榜 + 返回结构化数据
4. 展示:
   - 题材热度条形图 (Recharts BarChart)
   - 新题材信号 (列表 + 高亮)
   - 篇幅/更新模式 (折线图 + 散点图)
   - 标题套路 (Top 20 列表)
5. 选题材 → 跳 /skills/story-setup,预填题材
6. 也可对已存在的书:导入 → story-long-analyze 拆文
7. 拆文报告 tab: 摘要/黄金三章/爽点/节奏/文风
8. 报告可导出 PDF/MD
```

### 4.5 Persona E — Admin 管用户

```
1. 以 admin 登录 → Sidebar 出现 "Admin"
2. 进入 /admin/users:
   - 列表 (username, role, created_at, last_login, status)
   - "新建用户" → 弹窗表单 (username, password, admin?)
   - 行操作: 重置密码 / 禁用 / 删除 (二次确认)
3. 进入 /admin/projects → 选用户 → 列出其项目
   - 分享新项目: 输 project path + username
   - 撤销分享
4. 进入 /admin/audit:
   - 过滤: 时间范围 / 用户 / 操作类型
   - 表格: timestamp, user, action, resource, status
   - 导出 CSV
```

---

## 5. Sprint 规划

> 估算: 1 人天 = 8h 有效开发;已考虑前后端联调、SSE 调试、QA 自测时间

### Sprint 总览

| Sprint | 版本 | 目标 | 主要页面 | 触达 Persona | 估时 | 风险 |
|--------|------|------|---------|---------------|------|------|
| **S1** | V1.5.1 | **Skill 浏览器 + 1 个 skill 端到端** (打通 SSE 通用通道) | `/skills`, `/skills/:name` | A, D | **3 天** | SSE 重连、断线续传 |
| **S2** | V1.5.2 | **章节管理 + 写作主界面** (Tiptap + 续写/重写/插入) | `/chapters`, `/write/:chapter` | A, B, C | **4 天** | Tiptap 性能、SSE 大文本 |
| **S3** | V1.5.3 | **审查 + 去 AI 味 + 短篇模式 + 封面 + 设置** | `/review`, 短篇 8 节 tab, `/cover`, `/settings` | B, C, D | **3 天** | 4-agent 报告聚合逻辑 |
| **S4** | V1.5.4 | **Admin + 导入 + Onboarding + 移动响应式** | `/admin/*`, `/import`, Dashboard 增强 | A, E | **3 天** | 权限矩阵复杂度 |
| **S5** (预留) | V1.5.5 | **扫榜 + 拆文图表 + 项目切换 + 国际化 (zh-CN/en)** | `/skills/story-long-scan`, `/skills/story-long-analyze` | D | **3 天** | 扫榜性能 |

**总计约 16 工作日 = 3.2 周**

### Sprint 1: V1.5.1 — Skill 浏览器 + 通用 Skill 执行器

**目标**: 让 13 个 skill 全部可触达 + 至少 1 个 skill 完整跑通

**页面**:
- `/skills` — 卡片网格 (按 category 分组: 创作类/分析类/工具类)
- `/skills/:name` — 通用 Skill 执行器 (schema-driven 表单 + SSE 输出流)

**关键 API**:
- `GET /api/skills` → 列出所有 skill + schema (每个 skill 应该有 params schema)
- `POST /api/skills/{name}/execute` → 触发执行
- `GET /api/skills/{name}/status` → 轮询状态 (SSE 不可用时降级)

**关键工程**:
- Skill schema 需前端先 mock 后端 schema(若后端暂未返回 schema,前端维护一个静态 mapping)
- 通用 SSE 客户端 hook `useSkillStream()` 支持断线重连 + chunked output + 进度回调
- 输出展示: 自动判别 text / JSON / file 三种返回类型

**验收标准**:
1. `/skills` 列出全部 13 个 skill 卡片
2. 点击任一卡片进入 `/skills/:name`
3. 表单提交后 SSE 流式输出可见
4. 完成后可下载结果或复制文本
5. 网络断开 → 重连 → 续传

### Sprint 2: V1.5.2 — 章节管理 + 写作主界面

**目标**: 长篇作者能管理章节 + 续写 + 保存 + 重写选区 + 插入段落

**页面**:
- `/chapters` — 表格视图 + 新建/删除/排序/搜索
- `/write/:chapter` — 写作主界面 (Tiptap + 工具栏 + SSE 续写)

**关键 API**:
- `GET /api/chapters` + `GET /api/tracking`
- `GET /api/write/active` (锁)
- `POST /api/write/stream` (SSE,主轴)
- `POST /api/chapter/{n}/save`
- `POST /api/chapter/{n}/insert` (AI 插入段落)
- `POST /api/chapter/{n}/rewrite` (AI 重写选区)
- `GET /api/chapter/{n}/content`

**关键工程**:
- Tiptap 配置: 工具栏(粗体/斜体/标题/列表/引用/代码块)
- 编辑器右键菜单: AI 插入 / AI 重写 / 去 AI 味 / 复制 / 粘贴纯文本
- 自动保存: 防抖 3s → 调 save
- 字数实时统计 + 阅读时长估算
- 锁机制: 显示当前活跃 task,防止多端冲突

**验收标准**:
1. `/chapters` 列出所有章节,显示标题/字数/状态/更新时间
2. 可新建/删除/重命名章节
3. 进入 `/write/1` → Tiptap 编辑器加载
4. 点 "AI 续写" → 输入 prompt → SSE 8 阶段进度 → 流式填入
5. 选中文本 → 右键 "AI 重写" → 重写后弹 diff → 接受/拒绝
6. 选中文本 → 右键 "AI 插入" → prompt 输入 → 插入到选区后
7. 防抖保存工作正常
8. 字数实时更新

### Sprint 3: V1.5.3 — 审查 + 去 AI 味 + 短篇 + 封面 + 设置

**目标**: 写作闭环完成 (写 → 审 → 优化 → 导出),短篇模式可用,设置可改

**页面**:
- `/review` — 审查队列
- 短篇 8 节 tab 视图 (复用 `/write/:chapter` 但切换 short mode)
- `/cover` — 封面 prompt 生成 (或并入 `/skills/story-cover`)
- `/settings` — 模型 + cache 配置

**关键 API**:
- `POST /api/chapter/{n}/review` (Idempotency-Key)
- `POST /api/skills/story-deslop/execute`
- `POST /api/skills/story-cover/execute`
- `GET /api/models` + `GET /api/model/current` + `POST /api/model/switch`
- `GET /api/cache/stats` + `POST /api/cache/prompt-stats/reset`

**关键工程**:
- Review 结果存前端 IndexedDB (后端暂未提供 review list API)
- Review modal: 4 agent 报告分 tab (架构/可读性/一致性/爽点),每个 Issue 可跳转到对应段落
- 短篇模式: 8 节 tab + 单独的 prompt 配置
- 设置页: 模型下拉(实时切换) + cache 命中率展示 + 重置按钮

**验收标准**:
1. 写作界面 "送审" 按钮 → 调 review API → 4-agent 报告展示
2. 报告 Issue 可点击跳到对应段落
3. 选中文本 → 右键 "去 AI 味" → Diff 对比 → 一键替换
4. `/cover` 输入书名/题材/文风 → 输出 prompt + 复制
5. `/settings` 切换模型后,后续 AI 调用使用新模型
6. Cache 命中率实时显示
7. 短篇模式 8 节结构生成可用

### Sprint 4: V1.5.4 — Admin + 导入 + Onboarding + 移动响应式

**目标**: 完整闭环,admin 可管,新用户可引导,移动端可用

**页面**:
- `/admin/users` + `/admin/audit` + `/admin/projects`
- `/import` — 导入向导
- 增强 Dashboard + Onboarding wizard
- 移动端响应式 (768px 断点)

**关键 API**:
- `GET/POST/DELETE /api/auth/users*`
- `POST/DELETE /api/auth/projects/{path}/share*`
- `GET /api/auth/audit`
- `POST /api/skills/story-import/execute`

**关键工程**:
- Admin 路由守卫 (role-based, 非 admin 重定向到 /)
- 导入向导: 文件上传(若后端接受 multipart) 或 输入路径 → 后端解析 → 显示章节预览 → 确认映射
- Onboarding: 4 步向导 + 进度条 + 可跳过
- 移动端: Sidebar 折叠成汉堡菜单 + 编辑器全屏

**验收标准**:
1. 非 admin 访问 /admin/* → 重定向
2. Admin 可创建/删除/禁用用户
3. Admin 可分享项目给用户
4. 审计日志可查询 + 导出 CSV
5. 导入向导可解析 .txt 文件并生成章节
6. 新用户首登可见 onboarding 向导
7. 移动端 (375px / 768px) 布局正常,核心功能可用

### Sprint 5 (预留): V1.5.5 — 扫榜 + 拆文 + 项目切换（i18n 已取消）

**目标**: 策划者全流程可用,支持多项目（仅中文版，无需 i18n）

**页面**:
- `/skills/story-long-scan` + `/skills/story-short-scan`
- 拆文报告可视化
- 项目切换器

**关键 API**: 复用 scan/analyze API + 项目授权 API

**关键工程**: Recharts 集成 + 项目上下文

**验收标准**:
1. 扫榜数据可视化 (条形/折线/散点)
2. 拆文报告结构化展示
3. 多项目切换不需重登

> **2026-09-16 用户决定取消 i18n**（V1.5.5 范围）：用户表示「i18n 不用做，不用考虑多语言版本，就当前的中文版就够用了」。不再做 react-i18next / i18next 集成，不抽取 hardcoded 字符串。中文版即最终版。

---

## 6. 关键设计决策

### D1. Skill 执行 UX: SSE 流式 vs Polling

**决策**: **默认 SSE,失败降级 Polling**

**理由**:
- SSE 用户体感好 (实时反馈)
- 网络抖动时 SSE 易断,需降级
- 部分 skill 跑得久 (扫榜),需明确状态

**实现**:
- `useSkillStream()` hook 抽象
- 心跳机制: 每 15s 无消息 → 客户端发 ping → 服务端响应
- 断线重连: `Last-Event-ID` header 续传 (需后端支持)
- 失败降级: SSE 3 次失败 → 改 polling `/api/skills/{name}/status` 每 2s
- 超时: 单 skill 最大执行 10 分钟,超时提示用户重启

### D2. 章节列表拖拽排序

**决策**: **P2,先不做**

**理由**:
- 章节号是核心标识,业务上很少重排
- 拖拽排序需后端支持章节号重排 API
- 后续若有用户反馈再加

### D3. AI 操作权限

**决策**: **登录用户均可调用 AI 操作,但需明确展示 token/cost**

**理由**:
- 当前后端无配额/计费
- 后续若加配额,可在前端做 disabled 状态
- 显示调用次数 + 估算成本 (token * 单价)

**实现**:
- 每个 AI 按钮 hover 显示 "本次调用约消耗 X token"
- Dashboard 卡片显示 "本月已消耗 Y token"

### D4. 多项目切换

**决策**: **V1.5.x 不做,后端单项目模式**

**理由**:
- 后端 `POST /api/skills/{name}/execute` 需 project_root 参数
- 前端若支持多项目,需全局 project context + 切换器
- 当前 13 个 skill 调用时都需传 project_root,前端维护当前 project 即可

**V1.5.4 缓解**:
- AppBar 加 "当前项目" 选择器 (从 `/api/auth/projects/{user_id}/projects` 拉取)
- 切换项目 = 跳到对应 /chapters

### D5. 数据可视化: 扫榜/拆文

**决策**: **Recharts (与 MUI 兼容好)**

**理由**:
- Recharts 与 React 18 兼容,MUI 主题可注入
- 不引入 D3 (太重)
- 不引入 ECharts (包大,且风格不搭 MUI)

**图表清单**:
- 题材热度: BarChart
- 新题材信号: List + Badge
- 篇幅/更新模式: ScatterChart
- 爽点密度: LineChart
- 文风雷达: RadarChart

### D6. 错误处理: LLM 限流 / 超时 / 失败

**决策**: **明确错误分级 + 友好提示 + 自动重试**

**实现**:
- HTTP 429 (限流): Toast "服务繁忙,请稍后重试" + 倒计时按钮
- HTTP 504 / SSE timeout: Toast "AI 响应超时,已自动重试 1 次,仍失败请检查网络"
- HTTP 5xx: Toast "服务异常,已记录错误,请稍后重试"
- 网络断开: 全局 Snackbar "网络已断开" + 重连后恢复
- LLM 内容审查拒绝: Toast "AI 输出被安全策略拒绝,请调整 prompt"
- 配额耗尽: 模态框 "本月配额已用完,升级或等待下月"

**错误日志**:
- 前端 Sentry-style 上报 (可选)
- 所有 API 调用包一层 try/catch,统一上报到 `/api/audit` (若 admin 启用)

---

## 7. 不在本 PRD 范围

明确**不做**:

| 不做 | 原因 |
|------|------|
| **移动原生 App** (iOS/Android) | 当前只做 Web 响应式,后续若有需求再考虑 PWA 或 React Native |
| **实时协作编辑** (Google Docs 模式) | 后端无 CRDT/OT 能力,且会大幅增加复杂度 |
| **AI 模型微调** (Fine-tuning UI) | 后端无对应能力,属于另一个产品线 |
| **商业付费 / 订阅** | 后续独立模块,不混入创作流程 |
| **社交分享 / 评论 / 打赏** | 与创作工具定位不符 |
| **公开作品市场 / 阅读 App** | novel2all 是创作工具,不是发布平台 |
| **多语言 (i18n)** | V1.5.x 默认仅 zh-CN,V1.5.5 起考虑 |
| **离线编辑** | 浏览器 IndexedDB 仅做轻量缓存,不做离线完整编辑 |
| **AI 自动写完全书** (零人工) | 违反创作伦理,且 LLM 能力不足以一次产出长篇 |
| **第三方登录** (微信/GitHub OAuth) | 当前仅 username/password,后续独立模块 |
| **语音输入 / 语音朗读** | 浏览器 API 已有基础支持,但非核心需求 |
| **图片上传 / 富媒体** | 当前仅支持纯文本章节,后续若支持插图再考虑 |
| **版本控制 / Git 集成** | 当前无版本回退需求,后续若用户反馈再加 |

---

## 8. 风险与缓解

| 风险 | 等级 | 影响 | 缓解 |
|------|------|------|------|
| V1.5.0 React SPA 与后端 SSE 协议不一致 | **高** | S2 续写功能可能跑不通 | S1 先做 skill 通用执行器验证 SSE,失败回退 polling |
| 后端 skill 缺少 schema | 中 | 通用执行器无法 schema-driven | 前端维护静态 mapping,后续推动后端补 schema |
| Tiptap 大文档性能 | 中 | 长篇 100 章每章 1 万字可能卡 | 启用 virtualization,长文档分页 |
| 4-agent review 耗时长 | 中 | 用户等待 > 30s | 前端 SSE 流式渲染 review,边算边出 |
| Admin 权限漏洞 | 高 | 普通用户访问 /admin/* | 路由守卫 + 后端二次校验 |
| 移动端编辑器体验差 | 中 | iOS Safari 软键盘遮挡 | iOS safe-area + 编辑器 sticky toolbar |
| LLM 成本失控 | 中 | 用户滥用 AI 调用 | 显示估算成本 + 加全局频控 (后端已有 B4) |
| Sprint 估时偏差 | 中 | 可能延期 1-2 天/每个 sprint | S5 预留缓冲;若 S2 延期,S3/S4 可压缩 |

---

## 9. 度量指标 (上线后跟踪)

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| Onboarding 完成率 | > 70% | 完成向导 / 进入向导 |
| Skill 触发转化率 | > 40% | 进入 skill 页 / 完成 skill |
| 平均章节产出 | > 5000 字/章 | 章节字数 / 章节数 |
| Review pass 率 | > 60% | pass / total review |
| 用户 7 日留存 | > 30% | 7 日内回访 / 新增用户 |
| LLM 调用平均耗时 | < 8s (短) / < 30s (长) | API 响应时间 |
| Cache 命中率 | > 25% | `/api/cache/stats` |
| 移动端占比 | < 40% (Web 为主) | ua 检测 |

---

## 10. 附录: Sprint 估时复核

| Sprint | 原估时 | 复核 | 备注 |
|--------|--------|------|------|
| S1 | 3 天 | ✅ 合理 | Skill 浏览器相对简单,关键是 SSE 通用 hook |
| S2 | 4 天 | ⚠️ 偏紧 | Tiptap + 8 阶段 SSE + 3 个 AI 操作,实际可能 5 天 |
| S3 | 3 天 | ⚠️ 偏紧 | 4 模块并行,Review modal 复杂,可能 4 天 |
| S4 | 3 天 | ✅ 合理 | Admin 简单 CRUD + Onboarding 向导 |
| S5 | 3 天 | ✅ 合理 | Recharts + i18n 标准化 |
| **合计** | **16 天** | **17-19 天** | 建议预留 1 周缓冲 |

**建议**: S2 和 S3 各加 1 天缓冲,即总工期 **18-20 工作日 ≈ 4 周**。

---

## 输出摘要

- **IS_PASS: YES**
- **完成度评估**: 5 个 Persona 全覆盖;13 个 skill 全部分配 P0/P1/P2;9 个核心页面全部 IA 定义;5 个 user flow 详细;6 个关键设计决策明确;不做项清晰。
- **关键风险点**:
  1. **SSE 协议一致性** (S2 续写能否跑通取决于此)
  2. **Tiptap 大文档性能** (100 章 × 1 万字可能卡)
  3. **Sprint 估时** S2/S3 偏紧,建议各加 1 天
  4. **后端 skill schema 缺失** (若 S1 验证发现,需补充)
  5. **移动端编辑器体验** (iOS Safari 软键盘)
