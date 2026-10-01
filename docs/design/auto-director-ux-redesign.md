# 自动导演交互重设计（Phase 5 规划）

> 目标：让**小白用户**在自动导演「停止 / 卡住 / 等确认」时，能一眼看到「出了什么问题 + 该点哪个按钮」，而不是越看越晕、自恢复又不继续。
> 本文基于 2026-10-01 对 `server/src` 与 `client/src` 的代码调研，定位真实问题后给出「该合并的合并、该解耦的解耦」方案。

---

## 1. 现状诊断（代码实证）

### 1.1 服务端：状态模型错位（根因）

- `DirectorRuntimeInstance.status` 是**死字段**：全仓 `prisma.directorRuntimeInstance` 仅出现在 `novelDirectorRuntimeProjection.ts:506` 的 `findFirst`，**从不 update/create**。`schema.prisma` 里该模型的 `failed_hard / failed_recoverable / waiting_gate / cancelled / completed` 分支在投影里都是防御性残留。
- **真实驱动「导演是否停、为何停、怎么恢复」的状态全部编码在 `NovelWorkflowTask` 上**：`status`、`pendingManualRecovery`、`checkpointType`、`checkpointSummary`、`lastError`、`cancelRequestedAt`。
- 投影 `derivedState` 的 `requiresUserAction` 只挂在 `runtime.status === "waiting_gate" || "failed_hard"`（line 314、357），而这两个值实际从不写入 → 生产环境里「需要用户操作」的真正信号是 `NovelWorkflowTask.pendingManualRecovery` 与 `status==="waiting_approval" + checkpointType`。
- 三套互斥/叠加的状态编码（runtime.status / task.status+checkpointType / command lease stale），前端要自己拼，极易漏判。

**结论**：客户端当前不该再消费 `DirectorRuntimeInstance.status`。统一以 `NovelWorkflowTask` 字段为准。

### 1.2 客户端：恢复入口散落 + 死胡同（来自 UI 调研）

| # | 问题 | 位置 |
|---|------|------|
| 1 | **默认零主动提示**：导演一停，无应用内横幅 / Toast；浏览器桌面通知默认**关闭**（`lib/autoDirectorPauseNotifications.ts:18` 仅 `localStorage` 显式为 true 才开） | `AutoDirectorPauseNotificationWatcher.tsx`、`settings/director` |
| 2 | **入口只在 `/novels/:id/edit`**：恢复控件散在 NovelEdit 主横幅、workspace 栏卡片、AICockpit 对话框、TaskCenter 详情；首页 / 列表 / Creative Hub 看不到可点恢复件 | `NovelEdit.tsx:389`、`NovelWorkspaceRail.tsx:582`、`AICockpit.tsx` |
| 3 | **`blocked`（已暂停）死胡同**：`NovelEdit.tsx:1451-1714` 的 action 分支按 `checkpointType` 枚举匹配，`mapDashboardModeToTakeoverMode`（`:110-127`）甚至**没有 `blocked/paused` 分支**；普通 `blocked` 且非标准 checkpoint 时横幅只显示「需要你处理」却**没有继续/恢复按钮**，只剩「执行详情 / 退出导演模式」 | `NovelEdit.tsx:1451`、`110-127` |
| 4 | **横幅可一键消失**：`NovelEdit.tsx:2805` 的 `isTakeoverDismissed` 一旦触发，`takeover` 置 null，写 sessionStorage，整段入口消失 | `NovelEdit.tsx:228-229, 927-937` |
| 5 | **Creative Hub 名不副实**：`/creative-hub` 只是对话式诊断，`pendingManualRecovery` 态只发一句「解释失败原因」聊天，不提供恢复/接管件 | `CreativeHubPage.tsx:547, 571-589`、`presentation/creativeHubWorkspaceViewModel.ts:199-225` |
| 6 | **列表「继续创作」排除已暂停**：`NovelList.tsx:232-238` 只收 `running||waiting_approval`，`failed/cancelled/blocked/paused` 不出现，新手在此看不到入口 | `NovelList.tsx:330-338` |

### 1.3 意图 vs 现实

- 文档 / README 把 Creative Hub 包装为「统一创作中心」，代码里它只做聊天诊断。
- 多处文案声称「AI 会自己重试 / 从进度继续」（`DirectorRuntimeProjectionCard.tsx:297`、`AICockpit.tsx:247-250`），但 `blocked` 通用态**无对应可点动作**——自恢复只是展示性描述，没有用户能真正续跑的触发。

---

## 2. 设计原则

1. **单一真相源**：客户端只认 `NovelWorkflowTask` 的规整化状态，不再依赖 `DirectorRuntimeInstance.status`。
2. **主动、常驻、跨页**：任何「待处理」在全局壳层常驻提示，不依赖默认关闭的浏览器通知。
3. **一个入口管所有**：合并散落的恢复 UI 为统一组件 / 中心。
4. **永不「需要你处理」却无按钮**：每个停态都有主操作（服务端下发 `primaryAction`）。
5. **自愈透明 + 手动兜底**：`auto_recovering` 显示进度；卡住即给手动继续。

---

## 3. 重设计方案

### 3.1 服务端：规整化「导演注意力状态」（解耦）

新增单一投影服务，把三套状态编码收敛成一个对象（**不依赖 `DirectorRuntimeInstance.status`**）：

```ts
type DirectorAttentionState = {
  novelId: string;
  level: 'idle' | 'running' | 'waiting_approval' | 'auto_recovering' | 'needs_recovery';
  headline: string;        // 一行给用户：为什么停 / 在做什么
  detail: string;          // checkpointSummary 或 lastError
  primaryAction: { type: 'resume_from_checkpoint'|'continue'|'retry'|'takeover'|'approve_gate'; label: string };
  fallbackActions: { type: string; label: string }[];
};
```

- 推导来源：`NovelWorkflowTask.status` + `pendingManualRecovery` + `checkpointType` + `lastError`。
- 端点：`GET /novels/:id/director-attention` 返回单本；`GET /director-attentions` 聚合所有待处理小说（供全局徽标）。
- 复用现有恢复命令入口（`POST /tasks/:taskId/commands` 的 continue/resume_from_checkpoint/retry/approve_gate/takeover）。

### 3.2 客户端：统一恢复组件（合并）

新建 `components/director/DirectorAttentionCenter.tsx` + hook `useDirectorAttentions()`，提供三形态：

- **全局徽标**：`Navbar.tsx` 加常驻「待处理 N」铃铛，点开是待处理小说列表，每条带 `headline` + 主操作按钮。
- **横幅**：`NovelEdit` 顶部用统一 `DirectorAttentionBanner` 替代现有 `AITakeoverContainer` 的散乱 `checkpointType` 分支；任何 `level !== idle|running` 都显示，且**必有 `primaryAction`**。
- **卡片复用**：workspace 栏 `DirectorBookAutomationCard`、AICockpit 对话框、TaskCenter 详情都改用同一卡片，消除重复。

修复死胡同：action 由服务端 `primaryAction` 下发，前端不再按 `checkpointType` 硬拼 → `blocked` 也能拿到「继续自动导演」。

### 3.3 主动提示（不靠浏览器通知）

- 全局 in-app Toast / Banner：检测待处理时，进站或状态变化提示「《书名》自动导演已暂停，点此处理」。
- 「收起」只隐藏本次横幅，**Navbar 徽标仍常驻**；不写 sessionStorage 使其消失。

### 3.4 Creative Hub 真正接管

`/creative-hub` 的「下一步」在 `pendingManualRecovery / waiting_approval` 时返回真实 action：**转到恢复**按钮（调用统一入口），而非只发一句聊天。

### 3.5 列表页「继续创作」补全

`NovelList` 把 `blocked/cancelled/paused` 也纳入「继续创作」，统一导向恢复入口。

---

## 4. 合并 / 解耦清单

### 解耦（Decouple）

- **D1**：导演「是否停 / 为何停」从 `DirectorRuntimeInstance.status`（死字段）解耦 → 收敛到 `NovelWorkflowTask` 规整化投影。
- **D2**：多套 `derivedState` / `nextAction` / `displayState` 推导解耦 → 单一 `DirectorAttentionState` 服务。
- **D3**：UI 状态展示与「恢复动作触发」解耦 → 展示组件只读 `primaryAction`，不自拼分支。

### 合并（Merge）

- **M1**：AICockpit 对话框、DirectorBookAutomationCard、NovelEdit 横幅、TaskRecoveryDialog、NovelAutoDirectorProgressPanel 五个恢复 UI → 统一 `DirectorAttentionCenter`（卡片 / 横幅 / 徽标三形态）。
- **M2**：多处 recovery-candidates 列表逻辑 → 统一 `useDirectorAttentions()` hook + 聚合端点。
- **M3**：各页散落的「继续 / 恢复 / 接管」按钮 onClick → 统一 `directorAttentionActions.ts` 一个执行器。

---

## 5. 分阶段实施计划

### Phase 5-A：服务端正本清源（解耦）✅ 已完成（PR #21，合并于 `08e7ca2`）
- **T1**：新增 `DirectorAttentionState` 规整化服务（`server/src/services/novel/director/attention/DirectorAttentionService.ts` + 类型 `shared/types/directorAttention.ts`）。`mapProjectionToAttention` 基于现有 `DirectorBookAutomationProjectionService.getProjection` 输出归一，`level` 仅由 task 派生字段（`status` / `requiresUserAction` / `workerHealth.derivedState`）推导，**不读 `DirectorRuntimeInstance.status`**。`primaryAction`/`fallbackActions` 复用既有 `DirectorBookAutomationAction` 结构化描述符（未新增字符串分支表，符合 AI-First 红线）。
- **T2**：新增 `GET /api/director-attentions`（聚合）与 `GET /api/director-attentions/:novelId`（单本）端点（`server/src/routes/directorAttention.ts`，挂载于 `app.ts` 的 `/api/director-attentions`）。端点路径采用 `/api/director-attentions` 而非设计稿的 `/novels/:id/director-attention`，更贴合现有 `/api/tasks` 风格。
- **T3**：新增两个 DB-free 测试——`directorAttentionService.test.js`（纯映射断言：pendingManualRecovery→needs_recovery、waiting_approval、blocked、failed、running、auto_recovering、idle）+ `directorAttentionRoutes.test.js`（路由断言，mock service prototype）——`node --test` 9/9 通过。
- **实现注意（关键）**：`NovelWorkflowTask.status` 枚举实际只有 `queued|running|waiting_approval|succeeded|failed|cancelled`；`waiting_recovery` / `blocked` 是 **projection 层** `DirectorBookAutomationStatus` 的值，由 `pendingManualRecovery` 布尔与 dashboard 推导，并非 task 列值。因此聚合查询用 `OR:[{status in [...]},{pendingManualRecovery:true}]`，避免漏掉「运行中卡住」的小说（projection 会把它提升为 `needs_recovery`）。

### Phase 5-B：客户端统一组件 ✅ T4-T6 已完成（PR #22，合并于 `850895f`）
- **T4**：新建 `DirectorAttentionCenter`（卡片/横幅/徽标）与 `useDirectorAttentions()` hook。
  - 组件仅按服务端 `level` 切换视觉（`LEVEL_META`），渲染 `state.primaryAction` + `state.fallbackActions`；`idle` 惰性；**绝不**按 `checkpointType` 分支。
  - 新增 `client/src/api/directorAttention.ts`、`client/src/hooks/useDirectorAttention.ts`、`client/src/lib/directorAttentionActions.ts`（唯一归一化动作入口，复用 `isDirectorCockpitContinuationAction` → `continueDirectorRuntime(...)`，其余回落 `action.target.href`）。
- **T5**：`Navbar` 接入常驻徽标 `DirectorAttentionBadge`（持久化、非 sessionStorage）+ Radix Dialog 待处理抽屉，`useDirectorAttentions()` 统计非 idle 数——修复「不知去哪处理」。
- **T6**：`NovelEdit` 横幅改用 `DirectorAttentionBanner`（薄封装），替换原 `AITakeoverContainer`，删除散乱 `checkpointType` 分支，补 `blocked` 兜底按钮（服务端始终返回可点 primaryAction）。
- **验证**：`shared build` ✅、`client typecheck` EXIT 0 ✅、`client test` 182/182 ✅。
- **T7**（已完成，PR #25）：workspace 栏卡片、AICockpit、TaskCenter 改用统一组件（删除重复）。具体见 PR #25：workspace 栏卡片改渲染 DirectorAttentionCenter；NovelTaskDrawer 删除 runProjectedAction 字符串匹配与 checkpointType 标签覆盖，动作统一走 useDirectorAttentionActionExecutor；NovelList 对话框删除重复的 handleCockpitAction；TaskCenterDetailPanel 顶部接入统一注意力卡片（保留富信息 DirectorRuntimeProjectionCard）。新增客户端适配器 mapProjectionToAttention 镜像服务端归一化，复用既有 DirectorBookAutomationAction 描述符，不新增字符串分支表。AICockpit 保留富信息渲染，仅统一动作层。）。

### Phase 5-C：主动提示与闭环
- **T8**：全局 in-app Toast / Banner（替代默认关的浏览器通知）；「收起」不消灭入口。
- **T9**：Creative Hub「下一步」在停态返回真实恢复 action。
- **T10**：列表页「继续创作」纳入 `blocked/paused`。

### Phase 5-D：收尾
- **T11**：回归测试 + 小白可用性走查（覆盖 `blocked` / `needs_recovery` 场景）。
- **T12**：更新 README 与恢复手册对齐新交互。

---

## 6. 验收标准（小白视角）

- 导演任一种「停」态：Navbar 徽标有数、进任意页能看到横幅、横幅必有可点主操作。
- 点主操作后能**真正续跑 / 恢复**（不再「自恢复却不继续」）。
- 不出现「需要你处理」却无按钮；横幅关掉后仍有入口。
- Creative Hub 在停态给真实处理入口，而非聊天诊断。
- 列表页「继续创作」包含已暂停的导演。
