# 产品侧复杂度诊断与简化 PRD

> 文档类型：诊断 + 方案（本轮**不动代码**，仅输出结论供确认）
> 编写人：许清楚（产品经理）
> 面向产品：AI 小说创作工作台 / Novel2all
> 仓库根目录：`D:\workbuddyfiles\AI-Novel-Writing-Assistant-main`
> 用户诉求：当前项目使用起来非常复杂，希望进一步简化又不丢掉核心能力。本轮按用户确认的**激进精简**取向提出方案。
> 本文档所有结论均来自对 `client/src` 路由与导航、`client/src/pages`、`server/src`、`shared/types`、`README.md`、`TASK.md`、`AGENTS.md` 的实读，文件名与常量名可直接检索核对。

---

## 0. 一句话结论

产品当前把「AI 生产系统的内部复杂度」几乎完整地暴露给了用户：38 个页面路由、21 个一级导航、开书 5 阶段约 15 个人工决策、单书工作台 8+1 个 Tab、服务端 13 个工作流 Stage 与 9 个 Checkpoint、22 个编排步骤、8 类审批点，以及大量生产者术语（接手/检查点/产物/批次/重规划）。

而产品自身其实已经把正确的简约形态做出来了——`server/src/modules/setup/onboarding/application/FirstNovelOnboardingService.ts` 已经定义了正确的五步新手路线（创作环境 → 灵感与方向 → 开书准备 → 生产方式 → 首章成稿），`client/src/pages/novels/simpleCreation/SimpleNovelShelfPage.tsx` 也已经实现了"AI 自动写到全书完成、用户只需阅读"的目标形态。

**因此本方案的核心不是"发明一个新流程"，而是"把已经存在的正确流程扶正为主路径，把其余一切都从主路径上移走"。**

---

## 1. 现状盘点：用户视角的复杂度地图

### 1.1 一级入口 / 页面盘点（来源：`client/src/router/index.tsx` + `client/src/components/layout/Sidebar.tsx`）

`client/src/router/index.tsx` 共声明 **43 条路由**，去掉 4 条跳转重定向（`/chat`、`/auto-director/follow-up-center`、`/auto-director/followup-center`、`/writing-formula`）与 1 条兜底路由后，**用户可到达的真实页面为 38 个**。

侧边栏 `navGroups` 把这些页面暴露为 **3 组、共 21 个一级入口**：

| 分组 | 数量 | 入口（路由） | 说明 |
| --- | --- | --- | --- |
| 创作 | 8 | 首页 `/`、创作向导 `/help`、热门题材雷达 `/market-radar`、小说列表 `/novels`、短剧工作台 `/drama`（disabled，"即将推出"）、漫画工作台 `/comic`（Beta 角标）、创作中枢 `/creative-hub`、拆书 `/book-analysis` | 真正的"写小说"入口只有一个：小说列表 → 进入某本书。其余 7 项占去了 88% 的创作组注意力 |
| 资产 | 9 | 题材基底库 `/genres`、推进模式库 `/story-modes`、标题工坊 `/titles`、知识库 `/knowledge`、世界样本库 `/worlds`、写法引擎 `/style-engine`、反 AI 规则 `/anti-ai-rules`、基础角色库 `/base-characters`、视觉资源库（弹窗，非路由） | **9 个独立的"库管理学"页面**。服务端已在 `FirstNovelOnboardingService.ts` 的 `optionalEnhancements` 中承认：知识库、写法引擎、图像能力"不影响开始创作"。这 9 项全部是"可以先不学"的东西，却占了导航栏最宽的一块 |
| 系统 | 4 | 运行记录 `/tasks`、导演跟进 `/auto-director/follow-ups`、提示词管理 `/prompt-workbench`、系统设置 `/settings` | 运行记录与导演跟进是两张功能高度重合的"待处理清单" |

**未在导航栏暴露、但真实存在的隐藏一级页面**（用户会从各种按钮被送进去，从而产生"我又到了一个新地方"的困惑）：

- `/create` —— 创作工作台（`CreationStudioPage.tsx` 420 行），另一个"用灵感开书"入口
- `/novels/create` —— 手动完整设置开书（`NovelCreate.tsx` 227 行），第三个"开书"入口
- `/novels/auto-director` —— AI 自动导演开书（`AutoDirectorCreatePage.tsx` 805 行），第四个"开书"入口
- `/novels/:id/simple` —— 简易创作书架（阅读态）
- `/novels/:id/edit` —— 专业工作台（编辑态）
- `/novels/:id/story` —— 短篇工作台
- `/novels/:id/preview`、`/novels/:id/chapters/:chapterId`
- `/settings` 下另有 6 个子页：`/settings/models`、`/settings/model-routes`、`/settings/director`、`/settings/knowledge`、`/settings/maintenance`、`/settings/appearance`
- `/worlds/generator`、`/worlds/:id/workspace`（受 `featureFlags.worldWizardEnabled` 控制）
- `/chat-legacy`（`ChatPage`，已从 `/chat` 重定向保护下来的遗留页）
- `client/src/pages/astrology/AstrologyPage.tsx` —— **完全没有任何地方 import 的死页面**

孤儿文件清单（grep 全仓确认无引用）：

| 文件 | 行数 | 状态 |
| --- | --- | --- |
| `client/src/pages/astrology/AstrologyPage.tsx` | — | 死页面，无路由、无引用 |
| `client/src/pages/creativeHub/components/CreativeHubNovelSetupCard.tsx` | — | 无引用 |
| `client/src/pages/creativeHub/components/NovelProductionStarterCard.tsx` | — | 无引用 |
| `client/src/pages/genres/components/GenreTreeItem.tsx` | — | 仅被自身递归引用，外部无引用 |
| `client/src/pages/home/components/HomeAttentionQueue.tsx` | — | 无引用 |
| `client/src/pages/home/components/HomeRecentNovels.tsx` | — | 无引用 |
| `client/src/pages/novels/components/NovelWorkflowRunningIndicator.tsx` | — | 无引用 |

### 1.2 阶段数量盘点

**(a) 自动导演开书向导 —— 5 个阶段**
来源：`client/src/pages/novels/autoDirector/directorCreateStages.ts` → `AUTO_DIRECTOR_CREATE_STAGES`

| # | key | 用户可见标题 | 对应文件 | 用户要做的事 |
| --- | --- | --- | --- | --- |
| 0 | `idea` | 起始想法 | `StageIdea.tsx`（410 行） | 写一句灵感 |
| 1 | `basic` | 导演起始设置 | `StageBasicSetup.tsx`（308 行） | 7 项专业参数 + 折叠区 5 项 |
| 2 | `world_style` | 世界与写法 | `StageWorldStyle.tsx`（116 行） | 2 项选择 |
| 3 | `model_run` | 模型与生产准备 | `StageModelRun.tsx`（152 行） | 模型/温度/输出上限/AI 味开关/问题管理预设 |
| 4 | `candidates` | 方向与自动准备 | `StageCandidates.tsx`（111 行） | 二选一方向 |

**(b) 服务端导演工作流 —— 12 个 Stage / 8 个展示阶段 / 22 个编排步骤 / 9 个 Checkpoint / 8 类审批点**

- `shared/types/novelWorkflow.ts` → `NovelWorkflowStage` 共 **13 个**：`project_setup`、`creation_intent`、`short_story_plan`、`short_story_draft`、`short_story_review`、`auto_director`、`story_macro`、`world_setup`、`character_setup`、`volume_strategy`、`structured_outline`、`chapter_execution`、`quality_repair`。其中 3 个（`creation_intent`、`short_story_plan/draft/review`）属于短篇支线，`auto_director` 与 `project_setup` 分属两条 lane，长篇主链实际经历 8 个状态。
- `shared/types/novelWorkflow.ts` → `NovelWorkflowCheckpoint` 共 **9 个**：`candidate_selection_required`、`book_contract_ready`、`character_setup_required`、`volume_strategy_ready`、`production_experience_required`、`chapter_batch_ready`、`step_review_required`、`replan_required`、`workflow_completed`
- `shared/types/directorWorkflowStepCatalogData.ts` → `WORKFLOW_DISPLAY_STAGES` **8 个展示阶段**：项目设定 / 故事宏观规划 / 世界观准备 / 角色准备 / 卷战略 / 节奏·拆章 / 章节执行 / 质量修复
- `shared/types/directorWorkflowStepCatalogData.ts` → `WORKFLOW_STEP_CATALOG` **22 个编排步骤**（`chapter.state.commit`、`payoff.ledger.sync`、`character.resource.sync`、`chapter.draft.repair` 等）
- 同文件 Checkpoint 投影表 **9 条**（`candidate_direction_confirmed`、`character_setup_ready`、`volume_strategy_ready`、`structured_outline_ready`、`chapter_execution_continue`、`low_risk_quality_repair_continue`、`replan_continue`、`rewrite_cleanup_confirmed` 共 **8 类 approvalPoint**）
- 三条平行 lane（`manual_create` / `auto_director` / `creation_studio`），各自持有独立的 `taskQueryKey`（`workspaceTaskId` / `directorTaskId` / `taskId`）——**同一本书在不同入口会带不同的 URL 参数**

**(c) 单书工作台 —— 8 个流程 Tab + 1 个工具 Tab**
来源：`client/src/pages/novels/novelWorkspaceNavigation.ts` → `NOVEL_WORKSPACE_FLOW_STEPS` + `NOVEL_WORKSPACE_TOOL_TABS`

项目设定 / 故事宏观规划 / 世界观准备 / 角色准备 / 卷战略·卷骨架 / 节奏·拆章 / 章节执行 / 质量修复 / 版本历史

**关键事实**：这套 8 Tab 与服务端 8 个展示阶段是**同构的两套东西**，代码里用两张硬编码 switch 表互相翻译（`tabFromWorkflowStageName` 与 `tabFromDirectorDisplayStage`），并且两者标签**不一致**（服务端叫 `structured_outline` "节奏 / 拆章"，工作台 Tab 叫 `outline` "卷战略 / 卷骨架" 而 `structured` 才叫 "节奏 / 拆章"）。用户在学习一套流程时被迫接受两套名字。

实现体量的旁证：`client/src/pages/novels/NovelEdit.tsx` **2871 行**；`client/src/pages/novels/novelEditPlanningTabs.ts` 里 `BuildNovelEditPlanningTabsInput` 一个入参对象约 **150 个字段**。

### 1.3 新手从"开书"到"写完第一章"到底要走几步

按真实代码路径逐段统计（模型已配置完成的前提下）：

| # | 页面 | 页面里的必经动作 | 人工判断/填写次数 |
| --- | --- | --- | --- |
| 1 | `/`（首页） | 读 `FirstNovelJourneyStrip` / `HomeNextActionPanel`，点推荐按钮 | 1 次选择（在 4 个入口按钮里挑一个） |
| 2 | `/help`（创作向导） | 读 5 步路线卡 + 3 张"可选增强"卡，点主按钮 | 1 次点击 |
| 3 | `/novels/auto-director` | Stage①输入灵感（必填） | 1 次填写 |
| 4 | 同上 | Stage②导演起始设置：目标平台、读者频道倾向、叙事视角、节奏偏好、情绪浓度、战力体系、预计章节数 = **7 项**；若展开"补充读者与卖点"再加 目标读者 / 核心商业标签 / 竞品感 / 核心卖点 / 前 30 章承诺 = **5 项** | 0～12 次（默认值存在，但每一项都摆在眼前逼用户做判断） |
| 5 | 同上 | Stage③世界与写法：参考世界样本、书级默认写法 = **2 项** | 0～2 次 |
| 6 | 同上 | Stage④模型与生产准备：模型选择、温度、输出上限（`LLMSelector showParameters`）、"正文后去 AI 检测与修正"开关、"本书问题管理"策略卡 = **5 类** | 1～5 次（含打开策略弹窗选预设） |
| 7 | 同上 | Stage⑤方向与自动准备：从 AI 给出的两套方向中 **二选一** | **1 次真正的创作判断** ← 唯一有价值的决策 |
| 8 | `/novels/:id/edit?directorTaskId=...` | `NovelProductionExperienceHandoff`：阅读书架 vs 完整工作台 **二选一** | 1 次（对新手而言是一道难以理解的选择题） |
| 9 | `/novels/:id/simple` 或 `/novels/:id/edit` | 点"继续创作"/等待 AI 写第一章；若选专业工作台，还要在 9 个 Tab 里找到正确位置 | 1～3 次 |

**汇总：横跨 4～5 个页面、5 次阶段推进点击、15～25 个人工判断/填写项，其中只有 1 个（选整书方向）是真正服务于"写一本什么样的书"的判断。**

对照组：`DirectorProductionExperienceService.ts` 在用户选完创作界面后会 `enqueueContinueCommand({ continuationMode: "auto_execute_range", forceResume: true })` 自动启动全书生产——**系统本来就能一路自动跑到写完全书**。开书向导里的绝大部分人工步骤，在技术上是可选的，但在产品上被摆成了必经关卡。

### 1.4 概念术语负担：开发者术语泄漏到用户界面

以下均为 UI 直接可见文案（已附文件行号，可逐一核对）：

| 泄漏术语 | 出现位置 | 用户看到的话 | 为什么是负担 |
| --- | --- | --- | --- |
| **接手（Lease）** | `components/autoDirector/AICockpit.tsx:244` `leased_starting: "正在接手"`；`:509` `<SummaryMetric label="接手" value={workerHealth.leasedCommandCount} />`；该组件在 `pages/novels/NovelList.tsx:432/443` 渲染 | 小说列表页直接显示"排队 / 接手 / 执行 / 恢复"四个 worker 计数 | `lease` 是后台 worker 抢占任务的分布式概念，与"我的书写到哪了"毫无关系，却出现在用户进站第二屏 |
| **检查点（Checkpoint）** | `pages/novels/components/NovelAutoDirectorProgressPanel.tsx:419` "从检查点重新尝试"；`:404` "停在审核点，你可以先检查产物"；`pages/autoDirectorFollowUps/components/AutoDirectorFollowUpDetail.tsx:116` "检查点摘要：…"；`pages/novels/components/ChapterManagementTab.tsx:145` "AI 会先判断当前是否有活动批次、检查点或可执行章节范围" | 被当成"必须理解的系统名词"反复出现 | 用户心智里应该是"停在哪一章"，而不是"停在哪一个检查点" |
| **产物（Artifact）** | `NovelAutoDirectorProgressPanel.tsx:404` "先检查产物" | 同上 | 用户产出的是"角色 / 大纲 / 正文"，不是"产物" |
| **批量 / 批处理** | `pages/autoDirectorFollowUps/components/AutoDirectorFollowUpBatchBar.tsx:20` "批量重试异常任务" | 一级页面提供批量运维动作 | 这是运维台能力，不是一个写小说的人该做的事 |
| **AI 副驾确认 / 高级审批授权** | `components/autoDirector/AutoDirectorApprovalStrategyPanel.tsx` `summarizeDirectorAutoApprovalPoints(approvalPointCodes)` | "副驾确认边界：{审批点列表}。未包含的审批点会等待你确认。" | 把 8 类内部审批点（`low_risk_quality_repair_continue`、`rewrite_cleanup_confirmed` 等）当作可勾选对象交给新手 |
| **lane / taskQueryKey 三套参数** | `shared/types/novelWorkflow.ts` `NOVEL_WORKFLOW_LANE_DESCRIPTORS` | URL 上出现 `?directorTaskId=` / `?workspaceTaskId=` / `?taskId=` | 用户无感但导致"同一本书的链接长得不一样"，书签和恢复入口不稳定 |
| **向导 / Journey / graduated** | `components/onboarding/FirstNovelJourneyStrip.tsx` "N/5 步完成" | 首页 + `创作向导`页各显示一次 | 概念重复，用户不知道该看哪个 |
| **Debug 面板进入主工作区** | `pages/novels/components/NovelEditView.tsx:288` `<DirectorFactDebugDialog novelId={id} taskId={taskDrawer?.task?.id ?? null} />` | 对话内展示 `step.label` / `后台此刻正在碰这一步` | 调试能力混进了创作主界面 |
| **Beta / 即将推出** | `Sidebar.tsx:59` drama `disabled: true` + "即将推出"；`:138-150` comic "Beta" 角标 | 一级导航里出现两个不可用的入口 | 直接违反"低认知负荷" |

**结论：术语负担不是个别文案问题，而是"一层直接映射服务端运行时模型的 UI"。**

---

## 2. 核心能力红线

判断标准单一且严格：**是否直接服务"新手把整本书写完"**。分为三层给出明确结论。

### 2.1 红线层 —— 丢了产品就不成立（保留，且必须在主路径上可见）

| # | 能力 | 现状载体 | 为什么是红线 |
| --- | --- | --- | --- |
| R1 | **一句灵感 → AI 生成整书方向候选 → 用户二选一** | `StageIdea.tsx` + `StageCandidates.tsx` + `shared/types/creationStudio.ts` 的 `interpretCreationIdea` | 这是新手唯一能做、且唯一值得做的创作判断。它同时满足了"我不会写"和"我想写我想写的东西"。砍掉 = 产品失去存在理由 |
| R2 | **自动导演自动准备链**：故事宏观规划 → 本书世界 → 角色阵容 → 卷战略 → 拆章 → 章节执行资源，全自动跑完到"可开写" | `shared/types/directorWorkflowStepCatalogData.ts` `WORKFLOW_STEP_CATALOG` 的 planning 组（`story.macro.plan`、`book.contract.create`、`book.world.prepare`、`character.cast.prepare`、`volume.strategy.plan`、`volume.beat_sheet.generate`） | AGENTS.md 明确"不要假设主用户能手动修复结构、节奏、角色弧线"。这些必须是系统产出，不是用户任务 |
| R3 | **章节生产主链**：生成 → 审校 → 修复 → 状态回灌 → 推进下一章 | `WORKFLOW_STEP_CATALOG` execution 组（`chapter.draft.write`、`chapter.quality.review`、`chapter.draft.repair`、`chapter.state.commit`、`payoff.ledger.sync`、`character.resource.sync`） | "端到端完成整本书"的落点。`payoff.ledger.sync`（伏笔账）尤其不能砍——长篇不散架靠的就是它 |
| R4 | **可暂停可恢复的生产状态** | `NovelWorkflowTask` + `pendingManualRecovery` + `DirectorProductionExperienceService` 的 `enqueueContinueCommand` | 长篇生成必然跨小时甚至跨天。不能恢复 = 几千字白写 |
| R5 | **质量债机制**：局部质量问题记为章节级债并继续推进，**不得阻断全局** | AGENTS.md「Auto-Director Quality Gate Rules」+ `SimpleNovelShelfPage.tsx:315` "普通质量问题会作为待跟进事项记录，不会打断全书生产。" | 这是硬约束。任何简化方案**不得**引入"质量不达标就整本停下"的设计 |
| R6 | **完成度可读**：读已保存正文、看全书进度、导出成稿 | `SimpleNovelShelfPage.tsx`（正文阅读台、`downloadNovelExport`） | 用户必须能拿到成果，否则闭环不成立 |
| R7 | **AI 结构化理解优先于规则分支** | AGENTS.md「AI-First System Rules」 | 现有 `FirstNovelOnboardingService.ts` 的 `if/else` 路由决策树与 `novelWorkspaceNavigation.ts` 的两张 switch 表是合规风险点（详见 3.6）；保留其能力，但实现方式要收敛 |

### 2.2 价值层 —— 重要但可简化形态（不砍能力，改呈现）

| # | 能力 | 简化方向 |
| --- | --- | --- |
| V1 | **完整工作台的 8 Tab 分阶段人工编辑**（尤其卷规划版本管理 / 版本 diff / 影响分析 / 重平衡决策） | 下沉为"高级模式"。默认整页只展示当前步 + 写作进度 |
| V2 | **写法引擎 / 反 AI 规则**（686 + 340 行） | 合并进"写法偏好"，由 AI 自动推荐一套；手工规则编辑进高级模式 |
| V3 | **知识库 / RAG** | 下沉为可选能力。`FirstNovelOnboardingService` 已把它列为 `optionalEnhancements` |
| V4 | **世界样本库**（含 `worlds/generator`、`worlds/:id/workspace`，共 1406 行） | 收成一个"本书世界"只读视图；独立的 wizard 工作台下沉 |
| V5 | **标题工坊 / 题材基底库 / 推进模式库 / 基础角色库** | 合并为一个"创作资产"页，二级分区，不作为独立一级导航 |
| V6 | **问题治理预设（连续完成优先 / 质量优先）** | 默认一套（连续完成优先），另一套收进高级设置。不得在开书向导中出现 |
| V7 | **自动审批授权（8 类审批点勾选）** | 默认"AI 自动推进"全开；勾选面板移出主流程 |
| V8 | **AI 副驾 / Creative Hub Agent Runtime**（701 行 + `/chat-legacy`） | 下沉为高级入口，不进一级导航 |

### 2.3 可牺牲层 —— 激进精简的主要裁减对象（与"写完一本书"弱相关）

| # | 对象 | 体量 / 现状 | 砍掉后对核心旅程的影响 |
| --- | --- | --- | --- |
| S1 | **短剧工作台 `/drama`** | `DramaWorkspacePage.tsx` 573 行 + `DramaProjectPage.tsx` 709 行 = **1282 行**；`Sidebar.tsx:59` 已 `disabled: true` 标"即将推出" | **零影响**。它本来就没上线。砍掉连带删除 `server/src/services/drama`、`server/src/modules/drama` |
| S2 | **漫画工作台 `/comic`** | `ComicWorkspacePage.tsx` 586 行 + `ComicProjectPage.tsx` 415 行 = **1001 行**；Beta 角标 | **零影响**。与"写小说"是完全独立的创作物。服务端 `services/comic`、`modules/comic` 一并下沉 |
| S3 | **导演跟进 `/auto-director/follow-ups`** | 533 行 + `components/` 4 个面板 + `AutoDirectorFollowUpBatchBar` | **零损失**。它与"运行记录"是同一类清单的两份实现，且它是**可变状态的**（批量重试），本身就在擦 AGENTS.md「任务中心规则」的边。建议：删除页面，把它的"需要你决策的少数几条"推送到源页面（书架 / 工作台）顶部 |
| S4 | **提示词管理 `/prompt-workbench`** | 409 行 + `server/src/prompting/PromptWorkbenchService.ts` | **零影响**。纯开发者/调参者工具，非写作功能 |
| S5 | **`/chat-legacy` 遗留页 + `CreativeHubPage` 一级导航位** | `pages/chat/` 3 文件、`pages/creativeHub/` 19 文件 | **轻微**。保留 `CreativeHub` 能力但移出一级导航，进"高级模式"入口 |
| S6 | **`astrology` 死页面 + 6 个孤儿组件** | 7 个文件零引用 | **零影响**。直接删 |
| S7 | **热门题材雷达 `/market-radar`** | 1 文件；`FirstNovelOnboardingService` 未把它列为必要项 | **轻微**。它是"选题灵感"工具，不是"写书"功能。建议：合并为灵感输入框里的"看看最近热门"按钮（复用结果），删除独立页面 |
| S8 | **拆书 `/book-analysis`** | 413 行 + `pages/bookAnalysis/` 30 文件 | **轻微**。它服务于"照着别人的书写"，而非"把我的书写完"。建议：保留能力，从一级导航移入"创作资产"，并且不参与首章验收主路径 |
| S9 | **`settings/model-routes` / `settings/maintenance` / `settings/director` / `settings/knowledge` 四个独立子路由** | 各 10 行壳 page | **轻微**。合并入单一设置页的分区 |
| S10 | **世界样本 Wizard（`worlds/generator`、`worlds/:id/workspace`）** | 407 + 589 = 996 行，受 featureFlag 控制 | **轻微**。新手不会"手工搭建世界观"——这是 R2 里 AI 自动做的事 |
| S11 | **首页 `HomeNextActionPanel` 与 `/help` 创作向导双份引导** | 重复 | **零影响**。二选一保留，另一份删除 |
| S12 | **Desktop 打包（`desktop/`）** | 独立 workspace | **部署侧，不影响旅程**。下沉为构建产物而非主线交付（与架构师方案对齐） |
| S13 | **RAG / Qdrant 依赖** | `server/src/services/rag`、`routes/rag.ts` | **轻微**。作为可选能力，未配置时不得阻塞任何主流程（需在 #待确认 中与用户确认是否接受"未配置知识库时体验降级"） |

---

## 3. 产品体验层复杂度痛点（按认知负荷降序）

### Top 1 ｜四个"开始写"入口同时摆在眼前，且没有任何一个说清自己是什么

- **现象**：`/create`（"把想法写成作品"）、`/novels/create`（"完整设置"）、`/novels/auto-director`（AI 自动导演开书）、还有 `CreationStudioPage.tsx:137` 顶部的"完整设置"跳转按钮。首页 `homeViewModel.ts` 同时导出 `DIRECTOR_CREATE_LINK` / `SHORT_STORY_CREATE_LINK` / `MANUAL_CREATE_LINK` 三个常量，`CreationStudioPage.tsx:139-143` 又提供一个反向跳到 `/novels/create` 的出口。
- **面向谁**：完全不懂写作的新手——他第一次打开产品，第一屏就是一个必须选对的岔路口。
- **认知成本在哪**：新手无法通过任何线索判断"选错会不会白做"。四个入口背后是三条不同的 lane（`auto_director` / `creation_studio` / `manual_create`），产出物不同、后续 URL 参数不同、可恢复性不同。选错的代价是在做到一半时才发现"这个入口不能写长篇"。
- **历史成因**：`creation_studio` 是后来为"短篇 / 灵感直达"加的 AI-First 新 lane（`shared/types/creationStudio.ts` 的 `NarrativeForm = "short_story" | "long_novel"`），`auto_director` 是主 lane，`manual_create` 是早期手工填表时代的遗留。三者在 SSE 迭代中并行保留，没有做入口收敛。

### Top 2 ｜开书向导把新手不可能答好的专业问题摆成了必经关卡

- **现象**：`StageBasicSetup.tsx` 要求新手回答目标平台、读者频道倾向、叙事视角、节奏偏好、情绪浓度、战力体系、预计章节数，外加折叠区 5 项（目标读者、核心商业标签、竞品感、核心卖点、前 30 章承诺）；`StageModelRun.tsx` 要求选模型、温度、输出上限、AI 味修正开关、问题管理策略预设。
- **面向谁**：被定义为"完全不懂写作"的主用户群体。
- **认知成本在哪**：这些字段中大约一半本身就是写作专业术语（"叙事视角 / 节奏偏好 / 战力体系 / 温度"），另一半是模型工程参数（"温度 0.3～0.7 / 输出上限"）。新手的最优策略是全部保持默认——也就是说这些字段的现实作用是**制造焦虑，而不是收集信息**。
- **历史成因**：`StageBasicSetup.tsx:50` 自己的文案已经承认了这一点（"不确定时保持默认，AI 会继续根据你的起始想法判断"）。说明这些字段是"给专家留的逃生舱"，但因为被放在主流程第二步，就变成了新手的必答题。这是典型的「专家配置层与新手主流程层没有分层」。

### Top 3 ｜同一条生产链有两套名字：工作台 8 Tab vs 服务端 8 展示阶段

- **现象**：工作台 Tab 依次是"项目设定 / 故事宏观规划 / 世界观准备 / 角色准备 / **卷战略·卷骨架** / **节奏·拆章** / 章节执行 / **质量修复**"；服务端展示阶段是"项目设定 / 故事宏观规划 / 世界观准备 / 角色准备 / **卷战略** / **节奏·拆章** / 章节执行 / **质量修复**"。`novelWorkspaceNavigation.ts` 里 `tabFromWorkflowStageName` 和 `tabFromDirectorDisplayStage` 两张 switch 表把它们硬对起来，key 名 `outline` ↔ `volume_strategy`、`structured` ↔ `structured_outline`、`pipeline` ↔ `quality_repair` 都不一致。
- **面向谁**：所有用户，但新手受害最深——他没有稳定心智模型可以抵抗命名漂移。
- **认知成本在哪**：尤其"质量修复"这个词。服务端 `quality_repair` 其实是生产管线末端（审校、修复、状态提交、伏笔同步、资源同步）的总称，但对新手而言，"质量修复"读起来就是"我的书写坏了，系统正在修"。这会直接诱发焦虑和撤回行为。
- **历史成因**：Tab 是前端导航概念先有的（面向人类的导航），Stage 是服务端 LangGraph 编排概念后有的（面向机器的状态），两套命名各自演化，靠一张 switch 表缝合。

### Top 4 ｜工程侧术语直接出现在用户可见的界面上

- **现象**：见 1.4 全表。最典型的是**小说列表页**（用户进站第二屏）直接渲染 `AICockpit` 的"后台执行：排队 / 接手 / 执行 / 恢复"四项 worker 计数；以及前文 1.4 表列出的「检查点 / 产物 / 批次 / 范围」这一组工程名词， 出现在 `NovelAutoDirectorProgressPanel`、`ChapterManagementTab`、`FollowUpDetail` 的正文中。
- **面向谁**：新手。专家用户能猜到"接手"是 lease，新手只会把它读成"有人在接手我的书？"
- **认知成本在哪**：用户被迫维护一个自己完全不需要的模型。每多一个术语，新手的"我还敢不敢继续点"成本就上升一档。
- **历史成因**：这些投影（`DirectorBookAutomationProjection.workerHealth`、`checkpointSummary`、`artifactRows`）本来是为调试和运维设计的，之后被复用到面向用户的卡片与抽屉里，没有做用户向的再表述。

### Top 5 ｜"待办清单"被拆成了两个互不知情的页面，且其中一个是可变状态的

- **现象**：侧边栏系统组同时有 `/tasks`（运行记录，只读，符合 AGENTS.md 规则）和 `/auto-director/follow-ups`（导演跟进，带 `AutoDirectorFollowUpBatchBar` 的"批量重试异常任务"、详情里的"仅修复校验标记为低风险的状态、检查点、进度…"）。首页还有第三份清单逻辑（`HomeAssetHealth` + 未被引用的 `HomeAttentionQueue`）。
- **面向谁**：新手 + 回来续写的用户。
- **认知成本在哪**：出现问题时，用户不知道该去哪看。看 `/tasks` 只能只读，可能看得见但什么都做不了；看 follow-ups 可以做，但标题又是"导演"这种产品黑话。
- **历史成因**：AGENTS.md 后来加了"任务中心必须只读"的规则，`/tasks` 改合规了，但当时没把 follow-ups 一并收编，于是出现了"一个合规的只读清单 + 一个不合规的可操作清单"并存的局面。

### Top 6 ｜"选择创作界面"是一道新手看不懂、但必须回答的题

- **现象**：`NovelProductionExperienceHandoff.tsx` 在 AI 完成所有开书准备后横插一道"阅读书架 vs 完整工作台"的二选一，并且给阅读书架打了"推荐新手"标签。
- **面向谁**：已经在开书向导里被题目 15 轮的新手——此时他只想看到字，却又被拦了一次。
- **认知成本在哪**："不知道选了之后能不能改" "不知道两个界面里的东西是不是同一份" "怕选了简单的以后缺功能"。而代码里已经明确写了两句话可以避免这道选择题——`FirstNovelOnboardingService.ts` 的"两种界面共享同一套创作、审校和恢复能力"，以及 `SimpleNovelShelfPage.tsx:238` 的"专业模式"一键切换。
- **历史成因**：这是 expert flexibility 与 novice completion 冲突时，产品选择了"两个都要、让用户选"，而不是按 AGENTS.md 要求选后者。

---

## 4. 简化后的目标主路径（Happy Path）

### 4.1 目标旅程：3 个人工动作、2 个页面，从一句灵感到第 N 章

```
[页面 1] 首页 / 我的书
   ① 只有一个主按钮： 「用一句灵感开始」              ← 人工动作 1：填写一句话
        ↓
   AI 自动生成 2 套整书方向（书名/核心设定/主角/冲突/读者会有什么感觉）
        ↓
[页面 1，同一屏内] 方向卡片
   ② 「选这个方向继续」                              ← 人工动作 2：二选一（唯一有价值的创作判断）
        ↓
   AI 在后台自动完成：故事宏观规划 → 本书世界 → 角色阵容 → 卷战略 → 拆章 → 执行资源
   （进度以「AI 正在准备故事 / 世界 / 角色 / 分卷 / 拆章」的自然语言描述 + 一条进度条呈现，不出现阶段技术名）
        ↓
[页面 2] 这本书的书架（原 SimpleNovelShelfPage 强化）
   AI 自动开始写第 1 章 → 第 N 章，审校、修复、伏笔回灌全部后台进行
   AI 写好的章节会陆续出现在左侧目录里，点开即可读
   ③ 想调整时：「让 AI 改这一段」/「继续写下一章」      ← 人工动作 3（可选、创作性）
        ↓
   写完全书 → 「导出成稿」
```

**对比：跨页面 4～5 → 2；人工判断/填写 15～25 项 → 2 项（一句话 + 一个二选一）；一级导航可见入口 21 → 7。**

### 4.2 默认策略：以下全部由 AI 直接替用户决定，不再询问

| 原人工决策 | 简化后的处置 |
| --- | --- |
| 选哪个开书入口（4 选 1） | **删除选择**。全站只有一个"用一句灵感开始"入口，系统在后台根据灵感自动判断长短篇与推进方式（复用 `CreationStudioInterpretRequest` / `CreationIntentInterpretation` 的 AI 结构化理解） |
| 目标平台 / 读者频道 / 叙事视角 / 节奏偏好 / 情绪浓度 / 战力体系 / 预计章节数 | **AI 推断 + 事后可在"这本书的设置"里改**。全部带推荐值，不进主流程 |
| 目标读者 / 商业标签 / 竞品感 / 核心卖点 / 前 30 章承诺 | **折叠进"想让 AI 更懂你"的可选区域**，默认关闭 |
| 参考世界样本 / 书级默认写法 | **AI 自动选择**，不选也不阻断 |
| 模型 / 温度 / 输出上限 | **使用当前默认模型路由**。全部下沉到"高级-模型"分区 |
| 正文后 AI 味检测开关 | **默认开启**（值是质量保障不是取舍），开关移出主流程 |
| 本书问题管理策略预设（连续完成优先 / 质量优先） | **默认"连续完成优先"**（与 AGENTS.md 质量门禁非阻断规则一致）。不再出现在开书流程里 |
| 8 类审批点是否自动放行 | **默认全部自动放行**。仅有 / 保留 `candidate_direction_confirmed`（选方向）与 `production_experience_required`（见下）两个用户触点，其余下沉为自动确认 |
| 阅读书架 vs 完整工作台 | **默认进入书架**。专业工作台作为书架顶部一个"完整工作台"文字链（现状已经有"专业模式"切换能力，只是从强制选择改为可随时切换） |
| 什么时候开始写正文 | **选完方向就自动开始**。删掉"等待选择生产方式"这个 checkpoint 的阻断性，改为后台已启动 + 用户落地书架即可读到正在写的第一章 |

### 4.3 被折叠 / 下沉的能力去了哪里（不是消失）

| 能力 | 去向 |
| --- | --- |
| 8 Tab 专业工作台 | 保留，**书架页顶部"完整工作台"入口**进入（等价于切换 `creationExperience = professional`） |
| 卷规划版本管理 / diff / 影响分析 / 重平衡 | 收进工作台内的"分卷"分区（V1），默认折叠 |
| 写法引擎 / 反 AI 规则 | 合并为"写法偏好"，AI 自动推荐一套；手工规则编辑在偏好面板底部（V2） |
| 知识库 / RAG | "上传参考资料"抽屉，仅在书架页按需唤起（V3） |
| 拆书 / 世界样本 / 标题工坊 / 题材库 / 推进模式库 / 基础角色库 | 合并为一个**"创作资产"页**（二级 tab），一级导航只剩一个入口（V5） |
| 题材雷达 | 降级为灵感输入框旁的"看看最近热门"（S7） |
| Creative Hub / AI 副驾 | "高级模式"开关后可用的工作台（V8） |
| 提示词管理 / 模型路由 / 维护 / 导演设置 | 合并进单一"设置"页的分区（S9） |
| 运行记录 | 保留只读，作为唯一定位入口；**删除导演跟进页**，其待办收敛到源页面（S3） |
| 短剧 / 漫画 / astrology / 孤儿组件 | 删除（S1/S2/S6） |

---

## 5. 裁剪与合并候选清单

`影响面` 说明：`主路径` = 影响"灵感→写完全书"必经路径；`旁路` = 仅影响专家/可选功能。

| # | 候选对象 | 处置建议 | 理由 | 影响面 | 风险与前置条件 |
| --- | --- | --- | --- | --- | --- |
| C1 | 短剧工作台 `/drama` + `services/drama` + `modules/drama` | **砍掉** | `Sidebar.tsx:59` 已 disabled 标"即将推出"，从未上线；1282 行前端 + 整条服务端 | 旁路 | 需确认无用户已建 drama 数据；删除前做数据存在性检查 |
| C2 | 漫画工作台 `/comic` + `services/comic` + `modules/comic` | **砍掉**（或整体下沉为独立可选 repo） | Beta 状态，1001 行前端；与"写小说"零交集 | 旁路 | 同上；若已有用户数据在跑，改为 featureFlag 关闭 + 不进导航，暂不删代码 |
| C3 | `client/src/pages/astrology/AstrologyPage.tsx` + 6 个孤儿组件 | **砍掉** | grep 全仓零引用 | 旁路 | 无 |
| C4 | 导演跟进 `/auto-director/follow-ups`（含 BatchBar 批量动作） | **砍掉页面**，待办并入源页面 | 与"运行记录"功能重合；且持有 AGENTS.md「任务中心规则」禁止的批量可变动作 | 主路径（正） | 必须保证每一条跟进都有明确落地的源页面入口，否则用户会失去处理通道。**这是本方案中最需要谨慎的一条** |
| C5 | `/create`（创作工作台）、`/novels/create`（完整设置）两个开书入口 | **合并** 到唯一的 `/novels/auto-director` | 4 个开书入口可能造成选错入口后重来 | 主路径（正） | `creation_studio` lane 的 AI 结构化理解（`interpretCreationIdea`）**要保留并作为主干**，只收敛入口，不删能力 |
| C6 | `/help` 创作向导 vs 首页 `HomeNextActionPanel` | **合并**：保留首页内嵌向导卡，删除 `/help` 一级导航 | 同一份 `getFirstNovelOnboarding` 数据渲染两次 | 主路径（正） | 首页向导卡要能承载完整 5 步展开态 |
| C7 | 开书向导 Stage②`basic` / ③`world_style` / ④`model_run` | **从必经阶段改为折叠的可选项** | 15 项决策中只有 1 项（选方向）有价值 | 主路径（正） | 必须保留"默认值 + AI 推断"，且事后在本书设置中可改 |
| C8 | 生产方式二选一 checkpoint `production_experience_required` | **自动化**（默认书架，可随时切）/ 或降级为非阻断提示 | 代码已证明两种界面共享能力且可随时切换 | 主路径（正） | `DirectorProductionExperienceService.select` 需要默认序列化为 `simple` 不再阻断（见 #待确认 Q3） |
| C9 | 单书工作台 8 Tab + 版本历史 | **合并 / 下沉**：主视图"当前步 + 进度"，其余 Tab 为按需展开 | 8 Tab 与服务端 8 Stage 是同构两套东西 | 主路径（正） | 需同步改造服务端，统一命名（一套面向用户的名字，内部 key 不外露） |
| C10 | `DirectorFactDebugDialog`（`NovelEditView.tsx:288`） | **下沉** | 调试视图混进创作主界面 | 旁路 | 开发者仍需要；改为 featureFlag 或 URL 参数进入 |
| C11 | `AICockpit` 的 worker 指标（排队/接手/执行/恢复） | **从小说列表页移除** | `lease` 是 worker 内部概念 | 主路径（正） | 高级模式保留 |
| C12 | UI 术语：检查点 / 产物 / 批次 / 范围 / 重规划 | **改写为** 用户视角表述（"停在第 N 章"、"AI 正在准备角色"、"这一段需要 AI 重新安排"） | 术语泄漏构成主要认知负荷 | 主路径（正） | **注意：改写文案不得写成变更说明**，必须写"用户能做什么 / 系统在帮你做什么 / 下一步是什么"（AGENTS.md UI 文案规则）。例如不得出现"这里不再显示检查点"这类措辞 |
| C13 | 资产组 9 个一级页面 | **合并为 1 个"创作资产"页 + 二级分区** | 服务端已承认这些是 `optionalEnhancements` | 旁路 | 需保证每个原页面都有可达路径（可从 URL 直达某分区） |
| C14 | 设置页 6 个子路由 | **合并为单页分区** | 壳 page 各 10 行，说明本就没有独立承载内容 | 旁路 | 深链需重定向到带 hash/分区参数的主设置页 |
| C15 | 热门题材雷达 `/market-radar` | **降级**为灵感输入框内的"看看最近热门" | 选题工具，非写作工具 | 旁路 | 榜单数据与"自动选择榜单+逐本勾选"能力要能在内联面板里用 |
| C16 | 拆书 `/book-analysis`（30 文件） | **下沉**到"创作资产"，不进一级导航 | 服务于"照着别人的书写"，不是"写完我的书" | 旁路 | 已有引用关系（本项目 `.sourceNovelBookAnalysis` 能力）要先梳理 |
| C17 | 世界样本 Wizard（`WorldGenerator` / `WorldWorkspace`，996 行） | **下沉**：书架/工作台只保留"本书世界"只读视图 | 新手动手搭世界观与"AI 自动准备"重复 | 旁路 | `featureFlags.worldWizardEnabled` 已有开关，可直接置 false 观察 |
| C18 | RAG / Qdrant（`services/rag`、`routes/rag.ts`） | **下沉为可选能力** | 未配置时不应阻塞任何主流程 | 旁路 | 需验证"知识库未配置"时全书链路能完整跑通 |
| C19 | Desktop 打包（`desktop/`） | **下沉为构建产物** | 部署形态，与产品复杂度无关 | 旁路 | 与架构师方案对齐 |
| C20 | 三条 lane（`auto_director` / `creation_studio` / `manual_create`） | **收敛为一条**（保留 AI lane），其余合并 | 同一本书三种 URL 参数、三套 resume 逻辑 | 主路径（正） | 成本最高的一条，建议放在最后一个阶段；先做 C5 的入口收敛，再做 lane 收敛 |

---

## 6. 简化 PRD 主体

### 6.1 产品目标

让一个完全不懂写作的新手，只通过**填写一句话灵感**和**在 AI 给出的两套整书方向中二选一**这两个动作，就能启动一整部长篇小说的 AI 自动生产，并在一个稳定的界面里持续阅读 AI 写完的章节直到全书完成；过程中不需要理解任何阶段名、状态名、 checklist 或模型参数，遇到问题时有一个唯一入口告诉他"下一步做什么"。

### 6.2 用户故事（面向新手的真实场景）

| # | 用户故事 |
| --- | --- |
| US1 | 作为一个只有一个模糊想法的新手，我想把这句话直接交给产品，希望它自己想出整本书的方向、角色、分卷和章节安排，这样我不用先学"什么是大纲/什么是章法"。 |
| US2 | 作为一个不会判断答案的新手，我希望 AI 在给我两套方向时，直接告诉我"这套适合连续追更的读者，那套适合喜欢慢燃关系的读者"，这样我凭阅读直觉就能选，而不用理解其他的专业术语。 |
| US3 | 作为一个开始就要看到成果的新手，我希望选完方向后 AI 就开始写第一章并且我能直接读，不需要再回答"用哪个界面""用什么模型""质量策略怎么配"。 |
| US4 | 作为一个中途关掉电脑的新手，我希望下次打开时能直接回到我这本书、看到"写到第 12 章了"，并且继续写的动作就在这本书里，而不是先去别的清单页找任务。 |
| US5 | 作为一个读到某段不满意的新手，我希望能在正文本页直接说"这里让主角更狠一点"，就让 AI 改这一段并保留前后文一致，而不用知道要不要"重规划"或"回滚版本"。 |
| US6 | 作为一个不关心工程细节的新手，我希望屏幕上永远不出现我不需要认识的词，AI 在做什么、我下一步能做什么都用人话写出来。 |
| US7 | 作为一个终于写完全书的新手，我希望一键导出成稿并且能看到全书进度与已写字数，这样我有一份可以交出去的成果。 |

### 6.3 需求池

#### P0（不做这些，简化不成立）

| ID | 需求 | 可衡量标准 |
| --- | --- | --- |
| P0-1 | **单一开书入口**：全站仅保留一个"用一句灵感开始"的主入口，删除 `/create` 与 `/novels/create` 的一级可见性（能力合并进同一条 AI 理解链，不删除 AI 理解能力） | 首页 + 我的书 + 任何"新建"按钮都指向同一个路由； codebase 中三个 `*_CREATE_LINK` 常量收敛为一个 |
| P0-2 | **开书向导收敛为"填想法 → 选方向"两步**：Stage②/③/④ 从必经变为折叠可选 | 从灵感输入到"开始生成方向"的必经点击 ≤ 1 次；必经人工填写项 = 1 个（灵感文本）；默认不展示模型/温度/节数/写法等字段 |
| P0-3 | **选完方向即自动开始写第一章**：取消"选择创作界面"的阻断性 checkpoint，默认落地书架 | 用户在方向确认后 ≤ 10 秒内进入书架页，且书架页无需任何按钮点击即有首章任务在跑 |
| P0-4 | **一级导航从 21 项收敛到 ≤ 8 项** | Sidebar `navGroups` 项数 ≤ 8；短剧（disabled）与漫画（Beta）不再占用一级位 |
| P0-5 | **唯一待处理入口**：删除 `/auto-director/follow-ups` 页面，把需要用户决策的事项收敛到源页面顶部；`/tasks` 保持只读 | 全站不存在第二个可变状态的"任务清单"页面；AGENTS.md「任务中心规则」100% 符合 |
| P0-6 | **术语改写**：清除主路径上的「检查点 / 产物 / 批次 / 范围 / 接手 / lease 计数 / 重规划 / 接管」 | 主路径（首页、我的书、书架、开书向导）文案中不出现上述英文名词与工程隐喻；所有替代文案为"用户能做什么 / 系统在帮你做什么 / 下一步是什么"，且不含变更叙述措辞 |
| P0-7 | **小说列表页移除 worker 健康指标**（`AICockpit` 的排队/接手/执行/恢复四元组） | 小说列表卡片上只呈现"写到第几章 / 当前在做什么 / 是否需要你处理" |
| P0-8 | **保留并强化"写到全书完成"的默认连续生产**：默认策略 = 连续完成优先；局部质量问题记为章节级待优化并继续 | 满足 AGENTS.md「Auto-Director Quality Gate Rules」；**不得以任何理由引入"质量不达标整本停下"** |
| P0-9 | **删除死代码**：`AstrologyPage.tsx` 与 6 个零引用组件 | 文件被删除且构建通过 |
| P0-10 | **阶段命名统一**：面向用户的生产阶段只有一套名字（建议：准备故事 / 准备世界 / 准备角色 / 规划分卷 / 拆分章节 / 写正文 / 检查优化），禁止服务端 Stage key（`structured_outline`、`quality_repair` 等）出现在 URL 与 UI 中 | UI 与 URL 中不出现 `outline` / `structured` / `pipeline` / `quality_repair` 等内部 key |

#### P1（做完 P0 后的第二轮）

| ID | 需求 | 可衡量标准 |
| --- | --- | --- |
| P1-1 | **资产组合并为单一"创作资产"页**（技法/世界/标题/题材/模式/角色，二级分区） | 一级导航资产组从 9 项降到 1 项，每个原能力仍可通过带分区参数的 URL 直达 |
| P1-2 | **设置页合并**：6 个子路由收敛为单页分区 | `pages/settings/views` 从 7 个 page 收敛为 1 个 page + N 个分区组件 |
| P1-3 | **专业工作台 8 Tab 下沉**：默认书架，工作台按需进入，进入后默认展示"当前步"而非 9 个并列 Tab | `NOVEL_WORKSPACE_FLOW_STEPS` 不作为默认导航形态 |
| P1-4 | **写法引擎 / 反 AI 规则合并为"写法偏好"**，AI 默认推荐一套 | 主路径上不存在独立"写法引擎""反 AI 规则"入口 |
| P1-5 | **热门题材雷达降级**为灵感输入框旁的"看看最近热门" | 一级导航不再有 `/market-radar` |
| P1-6 | **拆书下沉**到"创作资产"二级分区 | 一级导航不再有 `/book-analysis` |
| P1-7 | **知识库降级为按需抽屉**，且未配置时主流程零阻塞 | 未配置知识库时跑通"灵感 → 写完全书"全链路 |
| P1-8 | **`DirectorFactDebugDialog` 下沉**为 featureFlag / URL 参数进入 | 主工作台界面默认不渲染该弹窗触发点 |
| P1-9 | **世界样本 Wizard 下线**（保留本书世界只读视图） | `featureFlags.worldWizardEnabled = false`；WorldList 保留只读取用 |
| P1-10 | **AI-First 合规收敛**：`FirstNovelOnboardingService` 的 if/else 路由决策与 `novelWorkspaceNavigation` 的两张 switch 表，改为消费 AI/编排层已结构化的"下一步 + 目标路由"输出（保留确定性的安全兜底与已完成结构化结果的后处理） | 决策路径不再由字符串分支表主导；允许保留输入校验与安全守卫类的固定判断 |

#### P2（激进精简的收尾）

| ID | 需求 |
| --- | --- |
| P2-1 | 短剧 / 漫画工作台整体移出主线（删除代码或抽为独立可选 repo） |
| P2-2 | 三条 lane（`auto_director` / `creation_studio` / `manual_create`）收敛为一条 |
| P2-3 | Creative Hub / AI 副驾移出一级导航，进"高级模式"开关后可用 |
| P2-4 | RAG / Qdrant 与 Desktop 打包下沉为完全可选的能力与交付形态 |
| P2-5 | `/chat-legacy` 遗留页删除 |

### 6.4 UI / 交互简化方向（结构级指引，非设计稿）

**导航：3 组 21 项 → 2 组 7 项**

| 分组 | 入口 |
| --- | --- |
| 创作（3） | 首页 · 我的小说 · 创作资产 |
| 我的（4） | 运行记录（只读） · 知识库（按需） · 写法偏好 · 系统设置 |
| 隐藏于页面内（非一级导航） | 完整工作台（书架顶部文字链） · 高级模式开关（设置内） · 灵感热门（灵感输入框内） |

再进一步（激进档）：一旦一本书正在写作中，首页与"我的小说"合并为"继续写《书名》"的单一落地页，导航只剩 5 项。

**结构约束（对齐 AGENTS.md 视觉与文案规则）**

- **低边框层次**：普通内容分组靠排版、间距、对齐与弱背景对比；边框只出现在表单控件、选中/聚焦、警告错误、表格分隔、拖拽目标、浮层上。**书架页现状存在嵌套带边框卡片**（`SimpleNovelShelfPage.tsx:180/201/261/278` 多层 `border rounded-3xl` 嵌套），简化重排版时需一并收敛。
- **文案规则**：拟用文案示例（均为用户视角，不含变更叙述）：
  - 替代"审核过程停在检查点"：`AI 已写到第 N 章，系统正在检查这一章的节奏和前后是否连贯。`
  - 替代"先检查产物再决定是否继续"：`你可以先读一遍已写好的章节，再决定让 AI 继续写下一章。`
  - 替代"需要重规划"：`后面几章的安排需要 AI 重新调整，已写好的正文会保留。`
  - 替代"（AI 生成书籍候选 / 接手 / 排队）"：`AI 正在准备这一章的写作素材。` / `AI 正在写第 N 章。`
- **进度呈现**：只给一条自然语言状态 + 一条整体进度条 + 章节目录三件套。禁止把服务端 Stage/Checkpoint 列表直接渲染成 UI。
- **动作位置**：任何"继续 / 恢复 / 重试 / 重规划 / 修复"动作**必须**放在能看到创作上下文的页面（书架、章节编辑页）；运行记录页只允许刷新、筛选、查看、跳转。

### 6.5 待确认问题（需用户拍板）

| # | 问题 | 为什么需要拍板 | 我的建议 |
| --- | --- | --- | --- |
| Q1 | **C1/C2（短剧、漫画）是"删代码"还是"移出主产品"？** | 涉及历史数据去留与不可逆操作；若已有用户在用，删除会造成数据损失 | 建议分两步：先删除一级导航入口 + featureFlag 关闭并观察；确认无活跃数据后再删代码。**删除前必须按 AGENTS.md 数据保护规则先做备份并验证** |
| Q2 | **C4（导演跟进页）是否接受删除？** | 它是目前"异常处理通道"的一部分；删掉后必须保证每条待办都有源页面落点，否则用户会在异常时失去处理能力 | 建议删页面、留能力：把"需要你决策的少数几条"以卡片形式呈现在书架页顶部，其余自动处理或记为质量债继续推进 |
| Q3 | **C8（生产方式二选一）是"完全自动化"还是"降级为非阻断提示"？** | 完全默选书架＝最大化新手完成率；但对"我想要专业工作台"的用户多了一次切换成本 | 建议默认书架 + 顶部"完整工作台"文字链；即不阻断、可随时切。这已经是现有能力，改动面小 |
| Q4 | **C20（三条 lane 收敛）本轮是否纳入实施范围？** | 这是成本最高、风险最大的一条（涉及 `taskQueryKey` 三套参数、历史任务兼容、URL 兼容），但收益也最大（一套恢复逻辑） | 建议本轮先做 C5 入口收敛（低成本），lane 收敛列入下一阶段，不与本轮混做 |
| Q5 | **RAG / Qdrant 与 Desktop 是否可以接受"未配置时体验降级、主流程不受影响"？** | 如果用户的实际使用场景已经依赖知识库写特定题材，下沉会影响这部分体验 | 建议下沉为完全可选；若用户确认依赖，则保留但移出一级导航，放宽到 P1 |
| Q6 | **"`重规划` 这个动作是否需要对新手可见？** | 完全隐藏会让用户在 AI 自己调整时感到失控；完全暴露又是术语泄漏 | 建议在书架页以"AI 正在调整后面几章的安排，已写正文会保留"的方式表达，**不出现"重规划"三个字**，也不做任何"让用户决定是否重规划"的按钮 |
| Q7 | **是否需要继续支持"短篇小说 / 长篇小说"双形态？** | `shared/types/creationStudio.ts` 有 `NarrativeForm = "short_story" \| "long_novel"`，`short_story_plan/draft/review` 三个 Stage 与 `ShortStoryStudioPage`。如果只保留长篇，可进一步砍掉一整条支线 | 建议本轮保留双形态但只保留一个入口，由 AI 判断；单形态决策交由用户后续确认 |

---

## 附录 A：本文引用到的关键代码位置

| 结论 | 位置 |
| --- | --- |
| 38 个真实页面路由 / 43 条声明 | `client/src/router/index.tsx` |
| 一级导航 3 组 21 项 | `client/src/components/layout/Sidebar.tsx:51-88` |
| 开书向导 5 阶段 | `client/src/pages/novels/autoDirector/directorCreateStages.ts:14-24` |
| 开书向导表单字段 | `client/src/pages/novels/autoDirector/StageBasicSetup.tsx`、`StageWorldStyle.tsx`、`StageModelRun.tsx` |
| 服务端 8 展示阶段 / 22 编排步骤 / 8 类审批点 | `shared/types/directorWorkflowStepCatalogData.ts:82-94, 96-128, 130-...` |
| 13 Stage / 9 Checkpoint / 3 lane | `shared/types/novelWorkflow.ts:3-82` |
| 工作台 8 流程 Tab + 1 工具 Tab 及两张 switch 映射表 | `client/src/pages/novels/novelWorkspaceNavigation.ts:16-29, 94-138` |
| 正确的 5 步新手路线定义 | `server/src/modules/setup/onboarding/application/FirstNovelOnboardingService.ts:11-17` |
| 「知识库/写法/图像不影响开始创作」的自证 | `server/src/modules/setup/onboarding/application/FirstNovelOnboardingService.ts:256-275` |
| 目标形态（AI 写完、用户只读） | `client/src/pages/novels/simpleCreation/SimpleNovelShelfPage.tsx` |
| 选完界面自动跑全书的技术证据 | `server/src/services/novel/director/commands/DirectorProductionExperienceService.ts:113-137` |
| 生产方式二选一在主路径上的强制卡点 | `client/src/pages/novels/components/NovelProductionExperienceHandoff.tsx` |
| worker lease 指标泄漏到小说列表 | `client/src/components/autoDirector/AICockpit.tsx:244, 509` + `client/src/pages/novels/NovelList.tsx:432,443` |
| 检查点/产物术语实例 | `client/src/pages/novels/components/NovelAutoDirectorProgressPanel.tsx:404,419`；`client/src/pages/novels/components/ChapterManagementTab.tsx:145`；`client/src/pages/autoDirectorFollowUps/components/AutoDirectorFollowUpDetail.tsx:116` |
| 审批点勾选面板 | `client/src/components/autoDirector/AutoDirectorApprovalStrategyPanel.tsx`、`AutoDirectorApprovalPointMultiSelect.tsx` |
| Debug 面板进入主工作台 | `client/src/pages/novels/components/NovelEditView.tsx:288` |
| 任务中心只读合规（正面样板） | `client/src/pages/tasks/TaskCenterPage.tsx:263,300-306` |
| TASK.md「明确不做」 | `TASK.md:199-205`（不增加第三套问题治理路线、不把两套预设复制成两套执行器、不为尚未出现的旧数据问题预建迁移框架） |

---

## 附录 B：给架构师的边界输入（供 `task #2` 对齐）

产品侧的红线分层约束应当在代码收敛时被当作硬边界：

1. **红线层 R1–R7 对应的服务端/客户端模块不可删**，只能重构。尤其 `WORKFLOW_STEP_CATALOG` 中 planning 组与 execution 组（`payoff.ledger.sync`、`chapter.state.commit`）是"写完一本书"的结构保证。
2. **质量债非阻断机制不可简化**。任何"整齐化"都不得以引入全局失败为代价，局部质量问题必须继续走章节级质量债路径；这与 AGENTS.md 最高优先级规则一致。
3. **可牺牲层 S1–S13 可以按这份清单删除**，其中 S1/S2/S3/S4/S6 是最低风险、最高收益的五个。
4. **三条 lane（C20）不在本轮要求范围内**，建议架构侧先做 S 层的物理删除，lane 收敛留到下一阶段，避免与数据迁移在同一批次内混合落地。
5. **共享取舍**：RAG / Desktop / 短剧 / 漫画下沉后，应在构建产物与依赖声明层面真正可选，而非仅在 featureFlag 层隐藏。
