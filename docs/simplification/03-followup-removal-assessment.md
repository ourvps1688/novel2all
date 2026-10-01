# T03 前置调研：应用内注意力提醒页（原「导演跟进」）`/auto-director/follow-ups` 删除可行性评估（已完成，见 PR #28）

> **状态：✅ 已完成（术语已统一为「应用内注意力提醒 / Director Attention」，见 PR #28）。** 本评估为 T03 的前置调研，结论已全部落地：跟进页已删除，能力重命名为「应用内注意力提醒（Director Attention）」并收口到统一入口（导航栏角标 / 全局横幅 / 任务中心）；源页面落点已验证；企业 IM 通知能力保留。下文保留当时的分析与判定供追溯。

> 本文是**只读调研产物**。调研过程中未删除任何文件、未修改任何代码、未提交代码改动。
> 调研对象：分支 `simplify/phase1-remove-dead-modules`（Phase 1 T01/T02/CSS 三个提交之后的代码状态）。
> 结论口径：拿不准的一律记为「保留」或「需用户确认」，不替决策者圈定删除范围。

---

## 0. 结论速览

| 结论 | 内容 |
| --- | --- |
| **可直接删** | 仅客户端跟进页自身：`client/src/pages/autoDirectorFollowUps/**`（7 文件 / 1,399 行）+ 路由 3 条 + Sidebar/移动导航/首页入口 4 处 |
| **不能删** | `client/src/api/autoDirectorFollowUps.ts`（被 `NovelEdit.tsx` 依赖）、服务端 `services/task/autoDirectorFollowUps/**` 中的 **9 个文件**（通知渠道、自动审批审计、动作执行器、投影、校验抽取、安全修复、事件构建、reason 解析器、企业微信回调签名）、`routes/autoDirectorChannelCallbacks.ts` |
| **缺口** | 3 类：① 跨小说的「待处理清单」发现能力消失；② `open_detail` 落点是只读的 `/tasks`，不是源页面；③ 浏览器暂停通知（`AutoDirectorPauseNotificationWatcher`）失去落点 |
| **结论（已落地）** | **分两步，均已落地**：本轮已删页面（T03-A），服务端保留待后续；删页面前已先补「发现能力」落点，未违反架构方案硬前置（见 PR #28） |

---

## 1. 范围校准：架构方案估计 vs 实际

架构方案 `02-architecture-simplification-plan.md` 估计服务端 7 文件 / 2,769 行。实际扫出来是 **12 个文件 / 3,741 行**：

```
server/src/routes/autoDirectorFollowUps.ts                                    180
server/src/routes/autoDirectorChannelCallbacks.ts                             221
server/src/services/task/autoDirectorFollowUps/
  AutoDirectorFollowUpActionExecutor.ts                                       637
  autoDirectorFollowUpProjection.ts                                           555
  AutoDirectorFollowUpNotificationService.ts                                  402
  autoDirectorFollowUpReasonResolver.ts                                       311
  AutoDirectorFollowUpService.ts                                              303
  autoDirectorAutoApprovalAudit.ts                                            276
  autoDirectorFollowUpEventBuilder.ts                                         233
  WeComNotifier.ts                                                            173
  DingTalkNotifier.ts                                                         161
  autoDirectorFollowUpValidationResult.ts                                     148
  autoDirectorSafeFix.ts                                                      109
  wecomMarkdownCallback.ts                                                     32
                                                                   合计     3,741
```

team-lead 的初步判断**成立**：企业 IM（钉钉 / 企微）的通知推送与回调能力确实就放在跟进页同一个目录里，删目录会连带删掉通知能力。

客户端实际规模（此前未单列）：

```
client/src/api/autoDirectorFollowUps.ts                     （6 个导出函数）
client/src/pages/autoDirectorFollowUps/
  AutoDirectorFollowUpCenterPage.tsx                                          533
  components/AutoDirectorFollowUpList.tsx                                     262
  components/AutoDirectorFollowUpDetail.tsx                                   238
  followUpPresentation.ts                                                     168
  components/AutoDirectorFollowUpOverview.tsx                                 110
  components/AutoDirectorFollowUpBatchBar.tsx                                  66
  selectionState.ts                                                            22
                                                                      合计  1,399
（另有两个随页测试：followUpPresentation.test.mjs、selectionState.test.mjs）
```

---

## 2. 清单 A：11 种 reason × 动作 × 源页面落点对照表

### 2.1 数据来源

- reason 枚举：`shared/types/autoDirectorFollowUp.ts:10-22`
- reason → 动作映射：`server/src/services/task/autoDirectorFollowUps/autoDirectorFollowUpReasonResolver.ts:89-311`
- `auto_approval_completed` 不走 resolver，由 `autoDirectorFollowUpProjection.ts:352-397`（`projectAutoApprovalRecordItem`）直接产出
- 三个 URL 的构造：`AutoDirectorFollowUpService.ts:164-170`
  - `originDetailUrl` = **`/tasks?kind=novel_workflow&id=${taskId}`**（运行记录页）
  - `candidateSelectionUrl` = `task.sourceRoute`
  - `replanUrl` = `task.sourceRoute`
  - `task.sourceRoute` 由 `resumeTargetToRoute()`（`server/src/services/novel/workflow/novelWorkflow.shared.ts:103-157`）算出，典型结果 `/novels/:id/edit?directorTaskId=…&stage=…`

### 2.2 源页面落点的关键事实

`client/src/pages/novels/NovelEdit.tsx`（小说编辑页 = 源页面）**已经完整消费跟进数据**：

- `:29` 导入 `executeAutoDirectorFollowUpAction`、`getAutoDirectorFollowUpDetail`
- `:821-836` 用 `queryKeys.autoDirectorFollowUps.detail(...)` 拉取 `activeAutoDirectorFollowUp`
- `:1169-1186` `executeFollowUpActionMutation` 调 `executeAutoDirectorFollowUpAction`
- `:1287-1306` `handleDrawerFollowUpAction`：navigation 动作走内部跳转/外链，mutation 动作走 executor
- `:2828-2830` 把 `followUp` / `onFollowUpAction` 传给 `NovelTaskDrawer`

`client/src/pages/novels/components/NovelTaskDrawer.tsx:444-480` 渲染「当前需要处理的动作」区块，**把 `followUp.availableActions` 全量渲染成按钮**（mutation 与 navigation 都渲染，`:465-478`），条件只有 `capabilities?.availableFollowUps !== false && Boolean(followUp)`（`:343`）。

**这条是最关键的发现**：源页面侧的落点**已经存在且是完备的**，不需要新造 UI。

### 2.3 对照表

| # | reason | 优先级 | 跟进页提供的 actionCode | 删除跟进页后的源页面落点 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | `manual_recovery_required` | P0 | `continue_generic`(mut) · `open_detail`(nav) | `continue_generic` → `NovelTaskDrawer`（`NovelEdit.tsx:1301` 走 executor）；`open_detail` → `/tasks`（只读） | **mutation 有落点**；`open_detail` 落点是只读页 |
| 2 | `runtime_failed` | P0 | `retry_with_task_model`(mut) · `retry_with_route_model`(mut) · `open_detail`(nav)；**batch: retry_with_task_model** | mutation → `NovelTaskDrawer`；另外 `NovelEdit.tsx:1344-1365` 有两个等价的「按当前模型重试 / 按任务原模型重试」mutation（`retryTask(..., { resume: true })`） | **mutation 有落点（且有两条等价路径）**；批量见 §4 |
| 3 | `validation_required` | P0 | `open_detail`(nav) · `auto_backfill_structured_outline`(mut, 条件) · `safe_fix_validation`(mut, 条件) | mutation → `NovelTaskDrawer`（executor 内经 `autoDirectorSafeFix.ts` / 补齐逻辑） | **mutation 有落点**（但只在 `NovelTaskDrawer` 这一处，且需先打开抽屉） |
| 4 | `runtime_cancelled` | P1 | `retry_with_task_model`(mut) · `retry_with_route_model`(mut) · `open_detail`(nav)；**batch: retry_with_task_model** | 同 #2 | **mutation 有落点**；批量见 §4 |
| 5 | `candidate_selection_required` | P1 | `go_candidate_selection`(nav) · `open_detail`(nav) | `go_candidate_selection` → `task.sourceRoute`（`resumeTargetToRoute` → `/novels/:id/edit?...`）→ **直接落到源页面** | **有落点**（纯导航，落点就是源页面本身） |
| 6 | `replan_required` | P1 | `go_replan`(nav) · `open_detail`(nav) | `go_replan` → `task.sourceRoute` → `/novels/:id/edit?...` | **有落点** |
| 7 | `chapter_batch_execution_pending` | P2 | `continue_auto_execution`(mut) · `open_detail`(nav)；**batch: continue_auto_execution** | mutation → `NovelTaskDrawer` | **mutation 有落点**；批量见 §4 |
| 8 | `quality_repair_pending` | P2 | `continue_auto_execution`(mut) · `open_detail`(nav)；**batch: continue_auto_execution** | 同 #7 | **mutation 有落点**；批量见 §4 |
| 9 | `auto_progress_running` | P2 | `open_detail`(nav) | `open_detail` → `/tasks`（只读） | 无 mutation，只需导航；但落点是**只读页**，不是源页面 |
| 10 | `runtime_replaced` | P2 | `open_detail`(nav) | 同 #9 | 同上 |
| 11 | `auto_approval_completed` | P2 | `open_detail`(nav)，targetUrl 硬编码 `/tasks?kind=novel_workflow&id=${row.taskId}`（`projection:385`） | `/tasks`（只读）；`NovelEdit.tsx:1384-1400` 另有 `archiveTask` 「收起这次自动导演完成提醒」mutation | 导航落点是只读页；**归档动作有源页面落点** |

### 2.4 清单 A 的三条缺口

| 缺口 | 说明 | 影响 |
| --- | --- | --- |
| **缺口 A-1：跨小说发现能力消失** | `NovelTaskDrawer` 的落点是**单本小说内**的。跟进页是目前唯一能「跨所有小说」一眼看到 N 个待处理事项、并直接跳转的界面。删掉后，用户必须自己记得是哪本书、再打开对应 `/novels/:id/edit` 才能看到动作。 | **违反架构方案硬前置**「每条跟进都能在源页面找到落点」——落点有，但**找到落点的路径没了** |
| **缺口 A-2：`open_detail` 落点是只读的 `/tasks`，不是源页面** | 11 种 reason **全部**带 `open_detail`，其 `targetUrl` 是 `/tasks?kind=novel_workflow&id=X`（`AutoDirectorFollowUpService.ts:164`）。而 `/tasks` 按 AGENTS.md 是只读页。`projection:385` 的 `auto_approval_completed` 更是硬编码指到 `/tasks`。 | 严格按 AGENTS.md 第 3 条「Put each workflow action on the source page」衡量，这条导航**本身就不达标**（是既有问题，非 T03 引入） |
| **缺口 A-3：`auto_approval_completed` 的 `itemType` 是 `auto_approval_record` 不是 `task`** | 它由 `projectAutoApprovalRecordItem` 从 `AutoApprovalRecord` 投影而来，不是 workflow task。它能否被 `/novels/:id/edit?directorTaskId=X` 正常打开、能否在 `NovelTaskDrawer` 里拿到对应 `followUp`，需要实测确认。 | 若不能，则该 reason 删除后**完全没有落点**（见 §2.5 静态验证结论） |

### 2.5 缺口 A-3 的静态验证结论（未做运行时实测）

**验证方式：纯静态代码追踪。环境无法启动完整应用，未做运行时实测。**

追踪结论：

1. `auto_approval_completed` **不经过 reason resolver**。`autoDirectorFollowUpReasonResolver.ts:89-311` 的 11 个分支中没有任何一个返回该 reason；它由 `autoDirectorFollowUpProjection.ts:352-397`（`projectAutoApprovalRecordItem`）从 `AutoApprovalRecord` 单独投影而来，`itemType` 为 `"auto_approval_record"`。
2. **明细接口对它是不可达的（今天就是如此）**。`AutoDirectorFollowUpService.getDetail()`（`:117-197`）走的是 `projectFollowUpItem(row, ...)`，而 `projectFollowUpItem` 在 resolver 返回 `null` 时直接 `return null`（`projection:302-305`）。因此当底层 workflow task 的状态不匹配任何 resolver 分支时，`getDetail` 返回 `null` → 404。
3. 跟进页点击该条目时（`AutoDirectorFollowUpList.tsx:190` → `onSelectTask(item.directorTaskId)`）取的正是 `directorTaskId`（`= AutoApprovalRecord.taskId`）。若底层任务此刻是 `running`/`queued`，resolver 会返回 `auto_progress_running`，明细会打开但**显示的 reason 标签与实际不符**；若是 `succeeded` 等，则直接 404。
4. 该 reason **唯一的 action 就是 `open_detail`**，`targetUrl` 硬编码为 `/tasks?kind=novel_workflow&id=${row.taskId}`（`projection:385`）。

**删除跟进页后的落点判定：不构成新增缺口。**

- 它唯一的 action 指向 `/tasks?kind=novel_workflow&id=X`，该深链在删除后依然有效，且 `/tasks` 支持 `kind`/`id` 参数（`TaskCenterPage.tsx:57-58,130-163` 会自动选中并加载详情）。
- 从 `/tasks` 详情面板可由「打开来源页面」（`TaskCenterDetailPanel.tsx:106`）接力到 `/novels/:id/edit`。
- 源页面另有等价动作：`NovelEdit.tsx:1384-1400` 的 `archiveTask`「收起这次自动导演完成提醒」。

**残留风险（未实测，需人工确认）：**
- 如果用户原本把跟进页的「最近自动通过」列表当作**查看近期自动审批记录的唯一入口**，删除后这个视图消失。`/tasks` 会列出全部 `novel_workflow` 任务（含自动导演任务），但**不会标注"最近自动通过"这一语义**。
- 明细接口对该 reason 的 404 / 标签错配问题**今天就已存在**，与 T03 无关；若要在删除后一并修好，属独立议题。

---

## 3. 清单 B：服务端文件调用方图

### 3.1 逐个文件

| 文件 | 行 | 被谁 import（`server/src` 内） | 只服务 `/api/auto-director/follow-ups`？ | 其他链路依赖 | 结论 |
| --- | --- | --- | --- | --- | --- |
| `routes/autoDirectorFollowUps.ts` | 180 | `app.ts:15,152` | **是**（`GET /overview`、`POST /batch-actions`、`GET /`、`GET /:taskId`、`GET /:taskId/revalidation`、`POST /:taskId/actions`） | 无 | **可删（页面删除后）** |
| `routes/autoDirectorChannelCallbacks.ts` | 221 | `app.ts:14,154` | **否**（`POST /dingtalk`、`POST /wecom`、`GET /wecom/execute`） | 钉钉/企微卡片回调入口 | **保留** |
| `AutoDirectorFollowUpService.ts` | 303 | `routes/autoDirectorFollowUps.ts:10`、**`routes/tasks.ts:10`** | **否** | `routes/tasks.ts:120-142` 的 `GET /auto-director-follow-ups/:taskId` | **保留**（运行记录页在用） |
| `AutoDirectorFollowUpActionExecutor.ts` | 637 | `routes/autoDirectorFollowUps.ts:9`、`routes/autoDirectorChannelCallbacks.ts:7`、**`routes/tasks.ts:9`** | **否** | ① IM 卡片回调执行动作；② `routes/tasks.ts:144-167` 的 `POST /auto-director-follow-ups/:taskId/actions` | **保留**（IM 回调 + 运行记录页） |
| `AutoDirectorFollowUpNotificationService.ts` | 402 | **`services/novel/workflow/NovelWorkflowStoreService.ts:12,44`**、`autoDirectorAutoApprovalAudit.ts:9` | **否** | 工作流核心 store 的 `notifyAutoDirectorTaskTransition`（`:103,199`）→ 钉钉/企微推送 | **保留**（删了就没有 IM 通知） |
| `DingTalkNotifier.ts` | 161 | `AutoDirectorFollowUpNotificationService.ts:9` | 否 | 钉钉 webhook 发送 | **保留** |
| `WeComNotifier.ts` | 173 | `AutoDirectorFollowUpNotificationService.ts:10`、`wecomMarkdownCallback.ts` 反向依赖 | 否 | 企微 webhook 发送 | **保留** |
| `autoDirectorAutoApprovalAudit.ts` | 276 | **`novelDirectorPipelineRuntime.ts:21`**、**`NovelDirectorService.ts:77`**、**`novelDirectorPipelinePhases.ts:20`**、`autoDirectorFollowUpProjection.ts:40`(type)、`AutoDirectorFollowUpService.ts:39` | **否** | 导演核心运行时/服务/阶段都在调 `recordAutoDirectorAutoApproval*` | **保留**（自动审批审计，与页面无关） |
| `autoDirectorFollowUpEventBuilder.ts` | 233 | **`NovelWorkflowStoreService.ts:13`**(type)、`AutoDirectorFollowUpNotificationService.ts:20` | 否 | 事件构建，供通知链路 | **保留** |
| `autoDirectorFollowUpProjection.ts` | 555 | `AutoDirectorFollowUpService.ts:38` | 是（间接） | 无 | **可删（页面删除后；但需先确认 `AutoDirectorFollowUpService` 保留部分不依赖它——实际依赖，故若 Service 保留则 Projection 必须保留）** |
| `autoDirectorFollowUpReasonResolver.ts` | 311 | `AutoDirectorFollowUpActionExecutor.ts:19`、`autoDirectorFollowUpEventBuilder.ts:11`、`AutoDirectorFollowUpNotificationService.ts:21`、`autoDirectorFollowUpProjection.ts:35` | 是（间接） | **质量债链路不引用**（见 §3.2） | **保留**（4 个保留文件依赖它） |
| `autoDirectorFollowUpValidationResult.ts` | 148 | `ActionExecutor:21`、`EventBuilder:12`、`NotificationService:22`、`Projection:39` | 是（间接） | 同上 | **保留** |
| `autoDirectorSafeFix.ts` | 109 | `AutoDirectorFollowUpActionExecutor.ts:26` | 是（间接） | 无 | **保留**（executor 依赖） |
| `wecomMarkdownCallback.ts` | 32 | `routes/autoDirectorChannelCallbacks.ts:9`、`WeComNotifier.ts:11` | 否 | 企微 markdown 回调签名 | **保留** |

**小结：12 个服务端文件中，可删的只有 1 个（`routes/autoDirectorFollowUps.ts`）；其余 11 个全部是「保留」。**
其中 `autoDirectorFollowUpProjection.ts` 名义上只被 Service 用，但 Service 本身要保留（运行记录页依赖），所以 Projection 也必须保留。

### 3.2 架构师指定核查项：`autoDirectorFollowUpReasonResolver` 是否被质量债链路引用

**结论：未被引用。**

全仓（`server/src` + `client/src` + `shared`）引用 `autoDirectorFollowUpReasonResolver` / `autoDirectorFollowUpValidationResult` / `extractBlockedAutoDirectorValidationResult` 的文件只有 5 个，全部在 `server/src/services/task/autoDirectorFollowUps/` 目录内：

```
AutoDirectorFollowUpActionExecutor.ts
AutoDirectorFollowUpNotificationService.ts
autoDirectorFollowUpEventBuilder.ts
autoDirectorFollowUpProjection.ts
autoDirectorFollowUpValidationResult.ts
```

质量债链路文件（`QualityDebtSettingsService.ts`、`ChapterQualityLoopService.ts`、`QualityRepairStageRunner.ts`、`ChapterQualityClosure.ts`、`novelDirectorQualityRepairRisk.ts`、`DirectorQualityLoopBudgetLedgerService.ts` 等）**零引用**。

架构方案设的「若被引用则必须保留」风险条件**已解除**——但注意：解除的是「因为质量债链路而必须保留」，它仍然因为**通知链路和执行器依赖**而必须保留（§3.1）。

### 3.3 通知链路的对外可见性（需用户确认的点）

- 通知渠道在设置页有独立配置 UI：`client/src/pages/settings/AutoDirectorChannelSettingsCard.tsx`（webhook 地址配置）、`AutoDirectorBrowserNotificationSettingsCard.tsx`（浏览器通知开关）
- 服务端配置服务：`server/src/services/settings/AutoDirectorChannelSettingsService.ts`
- 触发源是**核心工作流**（`NovelWorkflowStoreService.notifyAutoDirectorTaskTransition`），不是跟进页
- 回调入口 `POST /api/auto-director/channel-callbacks/{dingtalk,wecom}` 与 `GET /wecom/execute` 是 IM 卡片点按钮后的执行通道

> **需用户确认**：用户是否实际在用钉钉 / 企微通知？本调研无法从代码判断运行时是否在用。
> 但无论是否在用，**通知能力的删除不是 T03「跟进页删除（即原「导演跟进」页）」（已完成）的必然结果**——架构上它属于通知渠道，只是物理上恰好同目录。实际按「保留」处理；如确要一并裁掉通知能力，应作为**独立议题**立项（涉及设置页、回调路由、3 个 notifier 文件、2 个测试共约 1,700 行）。

---

## 4. 清单 C：批量动作与 AGENTS.md 合规

### 4.1 `AutoDirectorFollowUpBatchBar` 的批量动作

`client/src/pages/autoDirectorFollowUps/components/AutoDirectorFollowUpBatchBar.tsx`：

- 可选中的批量动作码（`:15-21`）：`continue_auto_execution`、`retry_with_task_model`
- 依赖 `batchActionCodes` / `supportsBatch`（`shared/types/autoDirectorFollowUp.ts:76-77`）
- 产生批量码的 reason（resolver）：`runtime_failed`、`runtime_cancelled`（→ `retry_with_task_model`）；`chapter_batch_execution_pending`、`quality_repair_pending`（→ `continue_auto_execution`）

**删除跟进页后，批量可变动作随之消失**——因为 `AutoDirectorFollowUpBatchBar` 是页面专属组件，`executeAutoDirectorFollowUpBatchAction`（`client/src/api/autoDirectorFollowUps.ts:84`）也只在页面内调用（已 grep 确认 client 内无其他调用点）。服务端 `POST /api/auto-director/follow-ups/batch-actions` 会失去唯一调用方。

> 这个方向本身是**符合 AGENTS.md 的**：批量重试/批量继续属于「task-mutating actions」，从简化角度看它们随页面消失是净收益，不构成缺口。

### 4.2 `/tasks`（运行记录页）当前是否只读合规

**服务端不是只读，但客户端页面是只读的。**

服务端 `server/src/routes/tasks.ts` 确实暴露了可变端点：

| 端点 | 动作 |
| --- | --- |
| `POST /recovery-candidates/resume-all` | 批量恢复 |
| `POST /recovery-candidates/:kind/:id/resume` | 恢复 |
| `POST /auto-director-follow-ups/:taskId/actions` | 跟进动作（continue/retry 4 种） |
| `POST /:kind/:id/retry` | 重试 |
| `POST /:kind/:id/cancel` | 取消 |
| `POST /:kind/:id/archive` | 归档 |

但**客户端 `/tasks` 页面没有调用任何一个**：

- `retryTask` 的调用点只有 `client/src/pages/novels/NovelEdit.tsx:1328,1353`
- `cancelTask` 的调用点只有 `NovelEdit.tsx:1372`
- `archiveTask` 的调用点只有 `NovelEdit.tsx:1391`
- `/tasks` 页面里所有叫 "retry" 的东西都是 `onRetry` → 重新**读取**（`TaskCenterListPanel.tsx:26,36,55`、`TaskCenterDetailPanel.tsx:22,52`），按钮文案是「重新读取」
- 页面文案明确声明只读：`TaskCenterDetailPanel.tsx:99`「继续、恢复、切换模型和推进策略请回到小说页面处理；运行记录只展示状态、错误、恢复位置和来源入口。」；`:105`「只打开任务来源，不会改变任务状态。」
- 只读页提供来源跳转：`TaskCenterDetailPanel.tsx:106` `<Link to={task.sourceRoute}>打开来源页面</Link>`

**判定：`/tasks` 页面当前符合 AGENTS.md 第 1、2、4 条。**（服务端残留的可变端点属于历史遗留，前端未消费；如果要彻底合规，应另立一项清理服务端 `/tasks` 可变端点的任务，不属于 T03。）

### 4.3 全站是否还存在第二个可变状态的任务清单页

**存在，但只有一个，且是全局弹窗而非清单页**：

- `client/src/components/layout/TaskRecoveryContext.tsx` + `TaskRecoveryDialog.tsx` 调 `resumeAllRecoveryCandidates` / `resumeRecoveryCandidate`，提供「一键全部恢复 / 恢复单项」
- 挂载在 `TaskRecoveryContext`（全局），不是 `/tasks` 页面内

> 这是**既有状态**，与 T03 无关（删除跟进页不会新增或消除它）。但它本身是一个「在来源页面之外执行 task-mutating action」的入口，与 AGENTS.md 第 3 条存在张力。建议记为独立的技术债，不在本轮处理。

### 4.4 逐条对照 AGENTS.md「Task Center Role Rules」

| AGENTS.md 条款 | 现状 | 删除跟进页后的影响 |
| --- | --- | --- |
| 第 1 条：运行记录是只读列表，不是操作界面 | ✅ 符合 | 无影响（`/tasks` 不变） |
| 第 2 条：不得放置 continue/recover/retry/cancel/replan/repair/approve/archive | ✅ 符合（前端未消费任何可变端点） | **改善**：批量 retry / continue 随之消失 |
| 第 3 条：工作流动作应放在源页面 | ⚠️ 部分符合 | `NovelTaskDrawer` 已承载全部 11 种 reason 的动作 → **改善**；但 `open_detail` 指向只读 `/tasks` 仍不达标（既有问题） |
| 第 4 条：只读页可刷新/筛选/选择/查看/打开来源页，不得改状态 | ✅ 符合 | 无影响 |
| 第 5 条：任务投影必须带稳定来源路由，能回到正确的可执行页面 | ✅ 符合（`task.sourceRoute` 由 `resumeTargetToRoute()` 生成） | 无影响 |
| 第 6 条：文案不得引导用户在运行记录内恢复/重试 | ✅ 符合（文案明确指向源页面） | 无影响 |

**AGENTS.md 合规结论：删除跟进页本身不会引入任何新的不合规，反而消除了一处批量可变动作。**

---

## 5. 删除跟进页的连带影响（容易被漏掉的部分）

| 位置 | 引用内容 | 处理方式 |
| --- | --- | --- |
| `client/src/api/autoDirectorFollowUps.ts` | `NovelEdit.tsx:29` 导入 `getAutoDirectorFollowUpDetail`、`executeAutoDirectorFollowUpAction` | **不能删整个文件**；最多删 `getAutoDirectorFollowUpOverview` / `listAutoDirectorFollowUps` / `revalidateAutoDirectorFollowUpDetail` / `executeAutoDirectorFollowUpBatchAction` 四个仅页面使用的函数 |
| `client/src/components/layout/Sidebar.tsx:28,78,117,148` | 导航项「应用内注意力提醒」（**已移除**，能力收口到导航栏注意力角标）+ 未读计数 badge（`getAutoDirectorFollowUpOverview`） | 已改：摘除导航项 + badge 查询 |
| `client/src/pages/home/homeViewModel.ts:299-307` | 首页卡片「N 个创作流程等待处理」→ `/auto-director/follow-ups` | 需改：这是**缺口 A-1 的主要暴露点**，删前必须给它换落点 |
| `client/src/components/autoDirector/AutoDirectorPauseNotificationWatcher.tsx:3,17` | 全局浏览器通知，轮询 `listAutoDirectorFollowUps`，`targetUrl` = `/auto-director/follow-ups?directorTaskId=…` | 需改：挂载在 `AppLayout.tsx:82,99,117,133`（4 处）。删页面会让它失去落点，且它依赖将被删的 `listAutoDirectorFollowUps` |
| `client/src/components/layout/mobile/mobileSiteNavigation.ts:88` + 路由 pattern `:40` | 移动端「应用内注意力提醒」入口（**已移除**，统一到导航栏注意力角标） | 已改（同 T01/T02 处理方式） |
| `client/src/mobile/autoDirector/mobileSupportContracts.ts:4` | `AUTO_DIRECTOR_MOBILE_ROUTE_PATTERNS` 含 `/auto-director/follow-ups` | 需改 |
| `client/src/router/index.tsx:23,64,65,66` | 懒加载 + 3 条路由（含 2 条兼容重定向） | 需改 |
| `client/src/api/queryKeys.ts:116-120` | `autoDirectorFollowUps` 命名空间 | 需改（保留 `detail`，`NovelEdit.tsx:822` 在用） |
| `server/src/app.ts:15,152` | `autoDirectorFollowUpsRouter` 挂载 | 可删（但 `/tasks` 下仍有功能等价的 `GET /auto-director-follow-ups/:taskId`） |
| 测试 | `client/tests/internalNavigation.test.js`、`mobilePageContracts.test.js`、`mobileSiteNavigation.test.js`、`taskQueueWorkspaceContracts.test.js`、`server/tests/autoDirectorFollowUpRoutes.test.js`、`autoDirectorFollowUpService.test.js`、`autoDirectorFollowUpActionExecutor.test.js`、`autoDirectorFollowUpEventBuilder.test.js`、`autoDirectorFollowUpReasonResolver.test.js`、`autoDirectorAutoApprovalAudit.test.js`、`autoDirectorChannelCallbacks.test.js`、`autoDirectorFollowUpNotificationService.test.js`、`novelWorkflowNotificationIntegration.test.js`、`client/src/mobile/autoDirector/mobileContracts.test.mjs`、`client/src/pages/autoDirectorFollowUps/{followUpPresentation,selectionState}.test.mjs` | 服务端 8 个测试覆盖的是**保留文件**，不能删；随页删的只有 2 个 mjs + 需要改的 4 个 client 测试 |
| `docs/**` | 20 份文档提及（含 `docs/public/modules/director-follow-up.md` 整页、`docs/wiki/product/task-center-role.md`） | 按此前约定文档本轮不动，记为后续项 |

---

## 6. 结论（已落地，见 PR #28）

**结论：分两步，均已落地。** 本轮已做 T03-A（删页面），服务端保留待后续；删页面前已先补发现能力。

理由：

1. **服务端几乎没有可删的东西。** 12 个文件里 11 个必须保留（通知渠道、自动审批审计、动作执行器、运行记录页依赖）。硬删只会把「删除跟进页」变成「删除企业 IM 通知 + 自动审批审计」，远超 T03 范围。
2. **架构方案的硬前置（每条跟进都能在源页面找到落点）在「动作」层面已满足，但在「发现」层面不满足。** `NovelTaskDrawer` 已经把 11 种 reason 的动作全量渲染，说明动作落点是现成的；但跨小说的待处理清单（首页卡片、Sidebar badge、浏览器通知）在删页后没有替代。
3. **执行顺序（均已落地）**：
   - **T03-A1（前置，必做）**：给「发现能力」找新落点。最小成本方案是把首页卡片和浏览器通知的跳转目标从 `/auto-director/follow-ups` 改为 `/tasks`（运行记录页已有 `failedTaskCount` / `recoveryCandidateCount` / `replanCount` 聚合，且是只读合规页），并由 `/tasks` 的「打开来源页面」按钮接力到 `NovelTaskDrawer`。
   - **T03-A2**：确认 `auto_approval_completed`（`itemType: "auto_approval_record"`）能在 `NovelTaskDrawer` 正常打开（缺口 A-3，需实测）。
   - **T03-A3**：删除 `client/src/pages/autoDirectorFollowUps/**`、路由 3 条、Sidebar/移动导航/首页入口、`api` 中 4 个仅页面使用的函数、移动端契约，跑与 T01/T02 相同的验证口径。
   - **T03-B（后续独立议题）**：服务端 `routes/autoDirectorFollowUps.ts` + `app.ts` 挂载摘除；企业 IM 通知能力是否保留需用户先确认。

**实际未一次性删**：保留服务端避免了连带删除钉钉/企微通知与回调（约 1,700 行 + 设置页 UI），避免了未经评估的功能裁减。
**实际也未直接暂缓**：页面本身的简化价值已明确落地（1,399 行 + 批量可变动作已移除），先补 A-1/A-2 两个前置后即安全推进。

---

## 7. 待决策项（均已拍板 / 落地，见 PR #28）

1. **企业 IM（钉钉/企微）通知是否仍在用？** 经确认保留（本轮只删页面，服务端 11 个文件全部保留）；若未来确认废弃，另立独立议题（涉及设置页 UI + 回调路由 + 3 个 notifier + 2 个测试）。
2. **发现能力的新落点选哪个？** 已选 `/tasks`（改动最小、只读合规），并由导航栏注意力角标 / 全局横幅 / 任务中心接力到源页面；首页卡片改为列出「待处理小说」并跳 `/novels/:id/edit`。
3. **`AutoDirectorPauseNotificationWatcher` 浏览器通知怎么处理？** 已退役（改由导航栏注意力角标 / 全局横幅常驻提示替代），相关设置卡片与 lib 一并移除。
4. **服务端 `/tasks` 残留的 6 个可变端点**（retry/cancel/archive/resume/resume-all/follow-up actions）是否另立清理任务？前端已不消费，属历史遗留；已另立清理任务（不在 T03 范围内）。
