# 10 · 极简交互信息架构（IA）规划

> 只读方案，不改代码。目标：重新构思交互，而非修 bug。
> 所有结论均经 `grep`/`wc` 实测（命令见附录）。HEAD = `46a59b6`（2026-10-03 更新；原 `9dea824` 已过期）。
>
> **落地进度速览**（四阶段 A/B/C/D；截至 2026-10-03）
>
> | 阶段 | 内容 | 状态 | 落地 PR |
> |---|---|---|---|
> | **A · 恢复/注意态统一** | 单 `<BookAutomationStatusBar>` + 调色板 `bookAutomationStatusMeta` + 消费已有 locator；删 2/3 横幅面 | 已完成 | PR #39 `46a59b6` |
> | **D · 枢纽加固（白屏）** | 修 `/assets` 嵌套 invariant 白屏（根因：合成 location + `<Routes location>` 机制触发 invariant） | 已完成 | PR #37 `c0df852` |
> | **D · 枢纽加固（子项）** | 把 `knowledge`/`book-analysis` 也改为 inline（参数命名空间化） | 未做 / 可选 | — |
> | **B · 运行模式收敛** | 隐藏 runMode/policyMode 选择器，给默认；单一"智能自动" | 已完成 | 见本次 PR（接管对话框冗余选择器已删；实测入口从无 3×4 矩阵，启动 payload 从不携带 policyMode，runMode 由服务端按缺省 `auto_to_ready` + 就绪度推导） |
> | **C · 单工作台** | 合并散落界面 → `/novels/:id` + Context Drawer | 待做 | — |
>
> 注：痛点 ①②⑤（三处恢复横幅轰炸、`/assets` 白屏）已随 PR #37/#39 消除；B/C 对应的痛点（模式矩阵、多页多概念）仍待解决。

## 0. 关键发现：单一真源其实已经存在，碎片化全在客户端

服务端已经产出一个**规范化的统一投影**，客户端只需一致地消费它：

- `DirectorBookAutomationProjection`（`shared/types/directorRuntime.ts:784`）已携带：
  - `status`（9 值枚举）+ `displayState`（**6 值规范 UI 态**：`processing` / `needs_confirmation` / `paused` / `needs_attention` / `completed` / `idle`）
  - `requiresUserAction` + `primaryAction` + `secondaryActions`（统一动作封套 `DirectorBookAutomationAction`，含 `type/target/commandPayload/emphasis`）
  - `headline` / `userHeadline` / `userReason` / `currentStage` / `currentLabel` / `blockedReason`
  - `timeline`（统一步骤轨迹）
- 每本小说的注意态 `DirectorAttentionState`（`shared/types/directorAttention.ts:10`）由 `mapProjectionToAttention(projection)` 派生，已存在。
- 运行模式有两套**正交**的用户选择：`runMode`（`manual` / `auto_to_execution` / `full_book_autopilot`）× `policyMode`（`suggest_only` / `run_next_step` / `run_until_gate` / `auto_safe_scope`）= 最多 12 种隐式组合 —— 这正是痛点 ④ 的"概念爆炸"根源。

所以：**状态/步骤模型不需要新建，碎片化在生产链路的"客户端渲染/路由编排层"**。

## 1. 目标信息架构（IA）

当前 `router/index.tsx` 实测 **34 条路由**；`Sidebar` 经 C10/B2 已收敛出单个 `/assets`（第 49 行），但 8 个旧资产路由（genres/story-modes/titles/anti-ai-rules/worlds/style-engine/base-characters，外加 knowledge/book-analysis）仍以独立路由存在。

目标（扁平、6 项主导航）：

| 主区 | 路由 | 形态 |
|---|---|---|
| 首页 | `/` | 现状 |
| 我的小说 | `/novels` | 现状 |
| **创作工作台** | `/novels/:id` | **新建唯一主工作区**，吞掉 auto-director/create/edit/story/preview/chapters/\*/creative-hub 的散落界面 |
| 资产 | `/assets` | 已落地的枢纽（C10/B1-B2），作为"可复用素材"区模板 |
| 任务 | `/tasks` | 现状（任务中心，只读仪表） |
| 设置 | `/settings` | 现状 |

- **一个主工作区 + 极简上下文抽屉**：规划/世界/角色/节奏板/章节执行/审核修复/质量，全部在 `/novels/:id` 内以 section 渲染；深看（节奏板详情、章节正文、世界手册）走**右侧 Context Drawer** 浮层，不离开工作区。
- `/assets` 已验证"旁挂枢纽"可行，作为第二项（资产）的模板，不再单独做大改。
- `creative-hub` 可并入工作台或保留为可选入口；`chat-legacy` 已是 `creative-hub` 重定向；`market-radar` 已内联（C18）。

## 2. 单一真源的状态/步骤模型

规则：**全仓只有一个组件 `<BookAutomationStatusBar>`**，绑定 `displayState` + `requiresUserAction` + `primaryAction`/`secondaryActions`。任何页面需要状态/恢复动作时，**复用此组件，禁止各页面自绘 Banner**。

- 步骤轨迹用单一 `<StepTrail>`（消费 `projection.timeline` / `currentStage` / `currentLabel`），取代散落在卡片里的多根进度条。
- 这从架构上保证"状态永远可见且唯一、恢复动作零寻找"：状态**只有一处被读取**、动作**只有一处被渲染**。
- 既有的 `RecoveryGuidanceBanner` / 侧栏 `/` 横幅 / 页内嵌恢复提示（痛点 ① 三处重复）收敛为：删掉其中 2 处，全部走统一的 status bar + 已建好的 recovery locator（任务 52–55）。

## 3. 运行模式收敛

今天向用户暴露 `runMode × policyMode` 两个正交选择（见 §0）。提案：**收为单一选择"智能自动执行"（默认）**。

- 3 个 `runMode` + 4 个 `policyMode` 退回**纯后端策略旋钮**，前端不再出现选择器。
- 凡真实检查点（人工审批门）由统一的 `displayState = needs_confirmation` + `primaryAction` 暴露**恰好一个"确认/继续"**——不出现模式矩阵。
- 仅保留一个高级开关（可选）："出错时自动暂停等我"给偏手动的用户；不暴露 3×4 矩阵。
- **纯前端/交互改动，零 schema/迁移影响**：服务端仍接受 `runMode`/`policyMode`，只是前端不再展示（给默认即可）。

## 4. 落地风险与依赖（红线）

- **红线（必须避开）**：`schema.prisma` / `schema.sqlite.prisma` / `migrations/` —— Phase 1–3 已合并契约，本轮**一律不动**。投影类型已存在，我们只**读**不动。
- `/assets` 嵌套 invariant 白屏（痛点 ②）：枢纽用"合成 location + `<Routes location>`"机制，子路由 pathname 不以 `/assets` 开头触发 invariant。这是前端 bug，且就是 `knowledge`/`book-analysis` 被迫退化为 `link` 模式（见 `assetHub.config.ts` 注释 §4.4）的根因。必须修，纯前端。
- 恢复 locator（任务 52–55）**已存在**：本方案**消费它**，不再重建。
- 节奏板覆盖门提示不带卷名 + 要手动去别处点"重生成节奏板"（痛点 ③）：`displayState`/`headline`/`userReason` 已带这些信息，修复方式是把节奏板卡片提示绑定到 `projection.currentLabel` / 按卷 attention，纯前端。
- **全部阶段均不涉及 Prisma**，可安全先动。

## 5. 分阶段落地建议

| 阶段 | 范围 | 风险 | 是否触 schema |
|---|---|---|---|
| **A · 恢复/注意态统一** | 单 `<BookAutomationStatusBar>` + Context Drawer；删 2/3 横幅面；全走 locator | 低（纯前端，locator 已建） | 否 |
| **B · 运行模式收敛** | 隐藏 runMode/policyMode 选择器，给默认；单一"智能自动" | 低（纯前端交互） | 否 |
| **C · 单工作台** | 合并 auto-director/create/edit/story/preview/chapters/\*/creative-hub → `/novels/:id` + Drawer | 中（界面重组，0 测试兜底，需手工回归） | 否 |
| **D · 枢纽加固** | 修 `/assets` 嵌套 invariant；把 knowledge/book-analysis 也改为 inline（参数命名空间化） | 中（回归白屏风险） | 否 |

每阶段独立可回滚；A 不依赖 B/C/D。

## 6. 最先收敛的那一层（结论）

**恢复/注意态渲染面（痛点 ① 与 ⑤）。**

理由：
1. 服务端已发出规范 `displayState`（6 态）+ 统一动作封套 + 每书 `DirectorAttentionState`，碎片化 100% 在客户端拼接/重绘；
2. 这是**最高频、最高焦虑**的界面——用户回到半成品书第一件事就是"找现在该干嘛/在哪恢复"；
3. 收口后，**其它每个屏幕都能复用同一个 `<BookAutomationStatusBar>`**，而非各自重新推导状态，因此 A 是 B/C/D 的前置使能层；
4. 风险最低（纯前端、locator 已建、不碰 schema）。

---

## 附录 · 实测命令与输出

```bash
# 路由条数
grep -c 'path: ' client/src/router/index.tsx        # → 34
# Sidebar 当前入口
grep -n 'to: "/assets"\|to: "/genres"\|to: "/worlds"' client/src/components/layout/Sidebar.tsx
# 规范显示态枚举
sed -n '618,624p' shared/types/directorRuntime.ts   # processing|needs_confirmation|paused|needs_attention|completed|idle
# 运行模式两正交选择
grep -rn "DIRECTOR_RUN_MODES\|DIRECTOR_POLICY_MODES" shared/types/novelDirector.ts shared/types/directorRuntime.ts
# 投影字段
sed -n '784,823p' shared/types/directorRuntime.ts
# 注意态派生
sed -n '1,20p' shared/types/directorAttention.ts
# 资产枢纽 inline/link 分裂根因
sed -n '1,80p' client/src/pages/assets/assetHub.config.ts
```

> 注：本方案与已在进行的 C10（/assets 枢纽）同向；C10 先落地验证了"旁挂枢纽"模式，本方案将其推广到"生产工作台"并统一状态/模式层。
