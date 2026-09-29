# Phase 2 重新校准报告（基线 `main` @ `74a03b8`）

> 作者：高见远（架构师）
> 日期：本轮
> 基线：`git log --oneline -1` → `74a03b8 chore: 更新工作记录`
> 性质：**只读侦察 + 排期建议**，本文件不含任何代码改动
> 上一版：`docs/simplification/02-architecture-simplification-plan.md` §4.2（C8–C18），该表是**在删掉 3.6 万行之前**估算的，本文件逐项实测推翻或修正

---

## 0. 测量方法与口径声明

本轮全部数字来自以下三种**实测**手段之一，不再出现"目录行数 × 系数"的估算：

| 手段 | 用于 |
|---|---|
| `find <dir> -type f -exec wc -l` / `cat` 汇总 | 文件数、行数 |
| `grep -rn --include=*.ts --include=*.tsx -F "<符号>"` 全仓枚举 | 引用关系、挂载点、依赖点 |
| Python 全文扫描（client/src 共 4,008,410 字符）+ 正则匹配 import 字面量 | 依赖真实引用数 |

**口径**：行数只统计 `.ts` / `.tsx`（不含 `dist/`、不含 `.test.*` 除非单独标注、不含 `node_modules`）。

**环境限制（影响可验证性，如实标注）**：`node_modules` 不完整（esbuild postinstall 被沙箱拦），因此
- `prisma` CLI 不可用 → schema 结论全部来自**静态 grep** `^model ` 计数，未做 `prisma validate`
- `client build` 本轮**无法执行** → C15 的验收只能延到环境就绪后
- 可用：`node ../node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`（server/client 均可）

---

## 1. 基线现状（实测）

| 工作区 | 文件数 | 行数 | 备注 |
|---|---:|---:|---|
| `client/src` | 568 | 103,316 | 含 20 个测试文件 |
| `server/src` | 1,085 | 202,238 | |
| `shared` | 70 | 14,683 | **另含 288 个 `shared/dist/` 文件 / 27,336 行（构建产物，不计入源码）** |
| `site` | 36 | 1,744 | |
| `desktop` | — | — | **已整体移除**，且 `pnpm-workspace.yaml` 已不含该项 |

`server/src/prisma/schema.prisma`：`grep -c "^model "` = **162**（与改造前一致，Phase 1 未动 schema）。

`server/src/app.ts`：`app.use("/api…")` 共 **32** 处（原方案记 27，口径不同：本轮含 `app.use("/api", …)` 这种无子路径挂载）。

**已完成、不得重复计数**（本轮复核确认）：
- Phase 1 模块裁剪：drama / comic / astrology / chains / promptWorkbench → −30,403 行
- T03 director follow-up 页面 → −1,860 行
- 钉钉 / 企微通知链 → −3,890 行
- validation-chain 渠道来源死分支 → −57 行
- **C16 已关闭**（见 §2.C16）
- desktop 工作区移除

---

## 2. C8–C18 逐项重新校准

### C8 ｜RAG / Qdrant 可选化 —— **仍存在，实际工作量远小于原估**

**1. 是否仍存在**：是。`server/src/services/rag/` 15 文件 / **3,688 行**，一行未删；`server/src/routes/rag.ts` 125 行。

**2. 真实规模**

| 位置 | 实测 |
|---|---|
| `server/src/services/rag/` | 15 文件 / 3,688 行 |
| `server/src/routes/rag.ts` | 1 文件 / 125 行（5 个 handler，含 `embeddingService.healthCheck()` / `vectorStoreService.healthCheck()`） |
| `server/src/app.ts` | 5 处：`:46` import、`:256` `ragWorker.start()`、`:257` `ragRetrievalTraceRetention.start()`、`:301` `:302` stop |
| **第二个启动点** | `server/src/services/knowledge/KnowledgeService.ts:28` 又调了一次 `ragServices.ragWorker.start()`（原方案未发现） |
| `server/src/routes/settings.ts` | `:30` `:442` `:444` `:454` — ragWorker start/stop + `enqueueReindex("all")` |
| `server/src/services/rag/index.ts` | 31 行，**模块加载即 new 全部 9 个服务**（embeddingService / vectorStoreService / ragContextualChunkService / ragRerankerService / ragIndexService / ragJobCleanupService / ragRetrievalTraceRetention / hybridRetrievalService / ragWorker） |

**3. 真实风险点**（本轮逐点 grep + 读源码核实完毕）

✅ **已核实：主链调用点全部已有 try/catch 降级，不需要补**

| 调用点 | 验证结果 |
|---|---|
| `novelCoreCharacterService.ts:247-256` | ✅ `let ragContext = ""; try { …buildContextBlock(…) } catch { ragContext = "" }` |
| `novelCoreReviewService.ts:237-249` | ✅ 嵌套 try + `catch { ragContext = "" }` |
| `GenerationContextAssembler.ts:612-630` | ✅ 同上 |
| `AuditService.ts:291-300` / `:387-396` | ✅ 全文 + 轻量双路径均已容错 |
| `routes/chat.ts:204-215` | ✅ 已容错 |
| `services/world/worldImprovementService.ts:41` / `:311` | ✅ 已容错 |
| `services/world/worldLayerGeneration.ts:160` | ✅ 已容错 |

🔴 **新发现：3 处未降级的读路径（这才是 C8 真正要补的）**

| 调用点 | 形态 | 影响面 |
|---|---|---|
| `server/src/agents/tools/novelReadTools.ts:457` | 裸 `await ragServices.hybridRetrievalService.buildContextBlock(...)` | agent 工具链，Qdrant 不可达 → 整工具抛错 |
| `server/src/services/knowledge/KnowledgeService.ts:480` | 裸 `hybridRetrievalService.retrieve(...)` | 知识库检索主路径 |
| `server/src/services/bookAnalysis/bookAnalysisCharacter/BookAnalysisCharacterRagAdapter.ts:64` | 裸 `retrieveByFacet(...)` | 外层 `BookAnalysisCharacterService.ts:444` 有 try，且仅在 depth = `deep`/`exhaustive` 时触发 → **风险最低，可后补** |

🔴 **新发现：2 处 worker 缺少 `ragConfig.enabled` 闸门**
- `RagRetrievalTraceRetention.start()` —— `app.ts:257` 无条件启动
- `RagIndexService` —— 全文 grep **未找到任何** `ragConfig.enabled` 判断

✅ **已存在的现成机制（原方案假设要新建 CapabilityResolver，实测不需要）**
- `server/src/config/rag.ts:98` → `enabled: isEnabled(process.env.RAG_ENABLED, true)`
- `HybridRetrievalService.ts:221` → `if (!ragConfig.enabled) return [];`（**读路径已闸住**）
- `RagWorker.ts:38` → `if (!ragConfig.enabled || this.timer) return;`（**worker 已闸住**）

> **结论修正**：C8 不需要"新建能力解析器"。真实工作只有 4 件：
> (a) `app.ts:256-257` 按 `ragConfig.enabled` 条件化；
> (b) 给 `RagRetrievalTraceRetention.start()` 加 enabled 闸门；
> (c) 给上述 2~3 处未降级读路径补 try/catch；
> (d) `rag/index.ts` 改懒实例化（可选，收益是启动时不构造 Qdrant 客户端）。
> **预估改动 < 80 行，不是原方案暗示的"5 分工作量"。**

**4. 前置依赖与建议批次**：无前置依赖。**建议批次 1**（独立、改动小、但风险等级"中"，因为动的是 server 启动路径，需全链路 smoke）。

**5. 是否涉及 Prisma schema**：**涉及但本轮不动**。`RagRetrievalTrace` 模型存在（1 个）。C8 的所有动作都在代码层，Phase 1–3 零数据动作，不碰 schema / 迁移。

---

### C9 ｜设置页合并 —— **仍存在，但原估算偏差约 19 倍，建议降级**

**1. 是否仍存在**：是，但形态与原方案描述完全不同。

**2. 真实规模**

| 项目 | 原方案 | 实测 | 偏差 |
|---|---:|---:|---|
| `client/src/pages/settings/views/` | 32 文件 / 4,074 行 | **7 文件 / 216 行** | **−94.7%** |
| `client/src/pages/settings/`（整个目录） | — | 29 文件 / 3,720 行 | 原估大概是拿整个目录当 views 了 |

实测 `views/` 明细：`SettingsOverviewPage 80` / `AppearanceSettingsPage 61` / `KnowledgeSettingsPage 31` / `DirectorSettingsPage 14` / `MaintenanceSettingsPage 10` / `ModelRoutesSettingsPage 10` / `ModelsSettingsPage 10`。

**这 7 个"子路由壳"本来就已经是 10~80 行的壳**，全部通过 `router/index.tsx:28-34` lazy 导入、`:68-74` 挂载，已天然代码分割。

**真实重量根本不在 `views/`**，而在：
`SettingsPage.tsx` 517 + `ModelRoutesPage.tsx` 546 + `components/ProviderStatusCard.tsx` 341 + `components/ProviderConfigDialog.tsx` 279 = **1,683 行**（占 settings 目录的 45%）。

**3. 真实风险点**：低，但**收益为负**。把 7 个壳合并进 `SettingsPage` 只会把已经 517 行的页面撑到 700+，且要额外写 tab 状态机；净减仅 ~216 行，却要重写导航（`SettingsNavigationCards.tsx` 82 行 + 7 条路由）。

**4. 前置依赖与建议批次**：无依赖。**建议：降级为 P2，Phase 2 不做**。若要保留，放在**批次 3 末尾**做"删壳 + tab 化"，且必须与 PM 复核——因为 PM 的 S9 诉求是"设置项太多太散"，真正的解法是**减少设置项本身**，而不是把 7 个页面拼成 1 个。

**5. 是否涉及 Prisma schema**：否。

---

### C10 ｜资产组页面合并 —— **仍存在，是 Phase 2 最大的一块，但风险最高**

**1. 是否仍存在**：是。侧栏「资产」组 9 项（`Sidebar.tsx:61-71`），其中 8 个是真页面 + 1 个弹层。

**2. 真实规模**（实测，不含 `style-engine`）

| 页面 / 目录 | 文件数 | 行数 | 服务端路由 |
|---|---:|---:|---|
| `pages/worlds/` | 34 | 7,922 | `app.ts:141` `/api/worlds` |
| `pages/knowledge/` | 7 | 2,568 | `app.ts:129` `/api/knowledge` |
| `pages/storyModes/` | 6 | 1,461 | `app.ts:128` `/api/story-modes` |
| `pages/antiAiRules/` | 9 | 1,046 | （挂在 `/api` 复合路由下） |
| `pages/characters/`（`/base-characters`） | 5 | 1,550 | `app.ts:143` `/api/base-characters` |
| `pages/genres/` | 6 | 872 | `app.ts:127` `/api/genres` |
| `pages/titles/` | 5 | 796 | `app.ts:132` `/api/title-library` |
| **小计（7 页）** | **72** | **16,215** | |
| `pages/writingFormula/`（`/style-engine`） | 18 | 4,599 | `app.ts:145` `/api/writing-formula` ← **原方案未计入** |

**3. 真实风险点**：**中高**（原方案标"中"，本轮上调）
- 7 个页面各自有独立 CRUD、独立 `queryKey`（`client/src/api/queryKeys.ts`）、独立表单与对话框；
- "合并为单页 + 二级 tab"实质是**重写 7 个页面的容器层**，回归面 ≈ 16,215 行，且 7 个页面 0 个测试文件（实测 `*.test.*` 均为 0）→ **没有任何自动化兜底**；
- 每个原能力必须保留可直达 URL（原方案已提示"先定 URL 契约"，本轮确认这条必须先做）；
- `worlds` 与 C11 重叠，**必须同批或让 C11 先做**，否则 worlds 会被改两遍。

**4. 前置依赖与建议批次**：依赖 C11（worlds 边界先定）+ URL 契约先定。**建议批次 3**（最大、最独立、风险最高，放最后单独一批，不与 C8 混）。

**5. 是否涉及 Prisma schema**：**涉及但本轮不动**。已确认模型：`World`、`TitleLibrary`、`AntiAiRule`、`KnowledgeDocument`、`NovelGenre`、`NovelStoryMode`、`BaseCharacter`、`BaseCharacterRevision`、`CharacterLibraryLink`。本轮只动前端导航与容器，schema / 迁移一律不动；若要删服务端 → 移到 Phase 4。

---

### C11 ｜世界样本 Wizard 下线 —— **仍存在，可删范围比原估大 68%，但有一个未决边界**

**1. 是否仍存在**：是。

**2. 真实规模**

| 分组 | 文件数 | 行数 | 处置 |
|---|---:|---:|---|
| `WorldGenerator.tsx` + `WorldWorkspace.tsx` | 2 | 996 | 原方案口径，实测一致 ✅ |
| **`components/generator/`（向导专属）** | **9** | **1,670** | ← **原方案漏掉的真实大头** |
| `components/workspace/`（世界工作台） | 15 | 3,283 | **保留** |
| `components/visualization/`（世界图谱） | 7 | 1,183 | **保留** |
| `WorldList.tsx` + `worldConsistencyUi.ts` | 2 | ~520 | **保留** |

`components/generator/` 明细：`WorldGenerator.tsx 407` / `WorldGeneratorStepOne.tsx 359` / `worldGeneratorShared.ts 151` / `WorldGeneratorStepThree.tsx 156` / `WorldReferenceSeedSelector.tsx 129` / `WorldGeneratorStepTwo.tsx 126` / `useWorldGeneratorDerivedState.ts 120` / `WorldPropertyOptionSelector.tsx 112` / `WorldLibraryQuickPick.tsx 110`。

**真实可删 = 10 文件 / 1,670 行**（原估口径 996 行，低估 68%）。

**3. 真实风险点**：中
- 🔴 **未决边界**：`worlds/:id/workspace`（`WorldWorkspace.tsx`）**也挂在 `featureFlags.worldWizardEnabled` 下**（`router/index.tsx:82`）。它其实是"世界编辑工作台"，不是"向导"。**删 wizard 时若按 featureFlag 一刀切，会连带误删工作台**。必须先与 PM 确认 PM S10/C17 的边界到底是"只删 generator 三步向导"还是"连工作台一起下线"。这是本项**唯一的阻塞点**。
- 门闸已就位：`router/index.tsx:78,82`、`WorldList.tsx:258,297`、服务端 `worldHttpContext.ts:13` —— 删除时是摘路由 + 删目录，不牵扯逻辑分支。
- 服务端 `server/src/services/world/` **21 文件 / 7,248 行必须全保留**：`NovelProductionService.ts:5,19` 直接 `new WorldService()`；`WorldContextGateway` 被 `novelCoreCharacterService.ts:9` 与 `novelCoreGenerationService.ts:24` 依赖（属 R 线）。原方案"只删前端 wizard，不删 service"的判断**实测成立**。

**4. 前置依赖与建议批次**：阻塞点是 PM 边界确认（非技术前置）。若为"只删 generator"，则**建议批次 2**（单点删除 + 摘路由，无跨模块风险）。

**5. 是否涉及 Prisma schema**：**涉及但本轮不动**。`World` 模型（+ `NovelWorldInstance` 分支）。本轮只删前端，不动 schema。

---

### C12 ｜`/help` 与首页 `HomeNextActionPanel` 二选一 —— **仍存在，最干净的一项**

**1. 是否仍存在**：是。

**2. 真实规模**
- `client/src/pages/help/HelpPage.tsx` — **1 文件 / 216 行**（原估一致 ✅）
- `client/src/pages/home/components/HomeNextActionPanel.tsx` — 1 文件 / 235 行

**3. 真实风险点**：低
- `HelpPage` 全仓引用仅 2 处：`router/index.tsx:8`（lazy import）与 `:47`（路由挂载）——**删除面极干净**；
- 深链 3 处需改写：`Sidebar.tsx:52`（侧栏「创作向导」）、`components/onboarding/FirstNovelJourneyStrip.tsx:20`、`components/onboarding/QuickSetupDialog.tsx:243`；
- 前置校验：首页卡（`HomeNextActionPanel` 235 行）需能承载原 `/help` 的 5 步展开态 —— 这是**唯一的内容工作量**，建议先读 `HelpPage.tsx` 确认 5 步内容是否已被首页卡覆盖。

**4. 前置依赖与建议批次**：无依赖。**建议批次 2**。净减 ~216 行 + 1 条路由 + 1 条侧栏项。

**5. 是否涉及 Prisma schema**：否。

---

### C13 ｜`DirectorFactDebugDialog` 下沉 —— **仍存在，但净减行为 0，价值存疑**

**1. 是否仍存在**：是。

**2. 真实规模**：`client/src/pages/novels/components/DirectorFactDebugDialog.tsx` — **1 文件 / 311 行**（原估一致 ✅）。

**3. 真实风险点**：低
- 唯一挂载点：`NovelEditView.tsx:19`（import）+ `:288`（渲染）—— 删除面干净；
- ⚠️ **净减行数 = 0**：改成 `?debug=1` 或 devFlag 后代码一行不删，只是不渲染。真正的收益是"调试视图不再混进创作主界面"（PM C10 的原意），不是减代码；
- 另注：该文件内 `formatStageLabel`（`:22-34`）处理了 `candidate_selection` / `candidate_confirm` / `takeover` / `book_contract` 四个**不在正式枚举里**的 stage key，属 M8 手工翻译表——若未来做 stage 真值收敛，这里要一并处理，但**本轮不动**。

**4. 前置依赖与建议批次**：无依赖。**建议批次 2**。

**5. 是否涉及 Prisma schema**：否。

---

### C14 ｜`AICockpit` worker 四元组文案改写 —— **仍存在，且原方案漏了 1/3 挂载点**

**1. 是否仍存在**：是。

**2. 真实规模**
- `client/src/components/autoDirector/AICockpit.tsx` — **615 行**（原方案未给行数）
- 四元组渲染点：`:508-511` `<SummaryMetric label="排队/接手/执行/恢复" …>`，对应 `workerHealth.queuedCommandCount` / `leasedCommandCount` / `runningCommandCount` / `staleCommandCount`
- 状态文案表：`:243-249`（`queued_waiting_worker: "等待接手"` 等 6 条）
- 辅助文案：`:260-269`（health 推导话术）

**3. 真实风险点**：低（纯文案），但**挂载点是 3 个不是 1 个**：

| 挂载点 | 形态 |
|---|---|
| `pages/novels/NovelList.tsx:432` / `:443` | 原方案已知 ✅ |
| `pages/novels/components/NovelTaskDrawer.tsx:357` | **原方案未列** |
| `components/autoDirector/DirectorBookAutomationCard.tsx:39` | **原方案未列**，且这个卡片本身也是被复用的 |

→ 只改 `NovelList` 两处会导致**同一组黑话在任务抽屉与自动化卡片里仍然存在**，简化不完整。

- 约束：受 AGENTS.md UI 文案规则约束（"用户能做什么 / 系统在帮你做什么 / 下一步是什么"），新文案需 PM 过稿。

**4. 前置依赖与建议批次**：需 PM 出新文案（非技术前置）。**建议批次 2**。

**5. 是否涉及 Prisma schema**：否。

---

### C15 ｜零引用依赖 + 失效 manualChunks —— **仍存在，实测 12 个（原估 9 个）**

**1. 是否仍存在**：是。

**2. 真实规模**（方法：Python 全文扫描 `client/src` 全部 `.ts/.tsx/.js/.css/.html`，共 4,008,410 字符，对 41 个 `dependencies` 逐个正则匹配 import 字面量）

🔴 **12 个零引用**：

```
@assistant-ui/react-devtools   @assistant-ui/react-ui      @hookform/resolvers
@langchain/langgraph-sdk       @platejs/ai                 d3-array
d3-selection                   d3-zoom                     dagre
react-hook-form                recharts                    zod
```

其中 `@langchain/langgraph-sdk` 在 `client/vite.config.ts:81` 有**字符串引用**（manualChunks 分块名），非真实 import —— 删包后该分支同时失效。

✅ **必须保留**（实测有引用，命名相近易误删）：

```
d3-force (2)   d3-scale (1)   d3-shape (1)        ← 被 tensionCurve/curveCoordinates.ts、
                                                     characterRelationshipGraphModel.ts、
                                                     worldGraphLayout.ts 使用
platejs (5)                                        ← 注意：@platejs/ai(0) 与 platejs(5) 不是一回事
@assistant-ui/react (5)  @assistant-ui/react-langgraph (3)
@xyflow/react (8)  framer-motion (8)  idb-keyval (3)  zustand (5)  sonner (3)
```

**3. 真实风险点**：低，但验收受限
- 必须跑一次 `client build` 验证；**当前 `node_modules` 不完整，本轮无法执行** → 验收条件需延到环境就绪；
- `vite.config.ts:79-89` manualChunks 中 `assistant-ui`（含 `@langchain/langgraph-sdk` 判断）与 `plate-editor` 两个分块名随删包失效，需一并清理；
- `zod` 在 client 侧零引用（类型校验全走 shared），但删除前需确认没有运行时动态 import。

**4. 前置依赖与建议批次**：无依赖，但验收依赖可用 `node_modules`。**建议批次 1**（与 C8 同批，两者互不相干，可并行分给两个人）。

**5. 是否涉及 Prisma schema**：否。

---

### C16 ｜desktop 硬耦合解耦 —— **✅ 已完成，本项关闭**

复核命令：
```
grep -rn "desktop" client/vite.config.ts client/package.json pnpm-workspace.yaml
→ 无输出
```
`client/vite.config.ts` 已不再读取 / 校验 `../desktop/package.json`；`pnpm-workspace.yaml` 仅剩 `client` / `server` / `site` / `shared`。**C16 从 Phase 2 清单中移除。**

---

### C17 ｜`bookAnalysis` 一级导航下沉 —— **仍存在，规模与原估完全一致**

**1. 是否仍存在**：是。

**2. 真实规模**：`client/src/pages/bookAnalysis/` — **30 文件 / 6,568 行**（原方案记 30/6,568，**实测完全一致 ✅**）。
最大 5 个：`hooks/useBookAnalysisWorkspace.ts 644` / `components/BookAnalysisCharacterPanel.tsx 570` / `BookAnalysisCharacterAppearancePanel.tsx 548` / `BookAnalysisDetailPanel.tsx 470` / `BookAnalysisSourceRangePicker.tsx 433`。

路由：`router/index.tsx:20`（lazy）+ `:60`（`book-analysis`）；侧栏 `Sidebar.tsx:56`「拆书」；服务端 `app.ts:126` `/api/book-analysis`。

**3. 真实风险点**：中
- 前端 0 个测试文件（实测），回归无兜底；
- `.sourceNovelBookAnalysis` 能力被 novel 创作侧引用（原方案已标注），下沉导航不等于删能力；
- 🔴 **与 C8 交叉**：`BookAnalysisCharacterRagAdapter.ts:64` 正是 C8 列出的 3 个未降级 RAG 读路径之一。若 C8 先补 try/catch，C17 后续挪动该目录时不会引入新风险 → **C8 应先于 C17**。

**4. 前置依赖与建议批次**：依赖 C8（先补 RAG 降级）+ URL 契约。**建议批次 3**（与 C10 同批，同为"一级导航下沉"，共用同一套 URL 契约）。

**5. 是否涉及 Prisma schema**：**涉及但本轮不动**。`BookAnalysis` / `BookAnalysisSection` / `BookAnalysisCharacter` 3 个模型。本轮只下沉前端导航，不动 schema。

---

### C18 ｜`marketRadar` 降级 —— **仍存在；🔴 关键修正：服务端不可删**

**1. 是否仍存在**：是。

**2. 真实规模**

| 侧 | 文件 | 行数 |
|---|---:|---:|
| 前端 | `client/src/pages/marketRadar/MarketRadarPage.tsx` | **1 / 424** |
| 前端 | `client/src/api/marketRadar.ts` | 1（未单计） |
| 服务端 | `server/src/modules/marketRadar/application/MarketRadarService.ts` | 742 |
| 服务端 | `…/http/marketRadarRoutes.ts` | 95 |
| 服务端 | `…/infrastructure/marketRadarSources.ts` | 160 |
| 服务端 | `…/infrastructure/marketRadarSources.test.mjs` | 61 |
| 服务端 | `server/src/prompting/prompts/marketRadar/`（2 文件） | 225 |
| **合计** | **6 文件（不含 test）** | **~1,706** |

**3. 真实风险点**：**低**（只动前端），但有一条**必须写进方案的硬约束**

🔴 `marketRadarService.getBriefPromptBlock()` 被 **director 主链 3 处直接调用**：

| 调用点 | 行 |
|---|---|
| `services/novel/director/idea/NovelDirectorIdeaConstellationService.ts` | `:31`、`:45` |
| `services/novel/director/NovelDirectorIdeaInspirationService.ts` | `:21` |
| `services/novel/director/phases/novelDirectorCandidateStage.ts` | `:271` |

且 `app.ts:253` 启动即 `void marketRadarService.recoverInterruptedRuns()`。

→ **`MarketRadarService`（742 行）属 director 的 R 线依赖，一行不能删**。C18 的可做范围**只有**"把 424 行的 `MarketRadarPage` 从一级导航降级为灵感输入框内联面板"，服务端 1,282 行全部保留。
→ 前端还有 2 处深链指向 `/market-radar`：`AutoDirectorCreatePage.tsx:667` 与 `:740`，降级时需改写。

**4. 前置依赖与建议批次**：无技术前置，但与 C10/C17 共用"一级导航下沉"模式与 URL 契约。**建议批次 3**。

**5. 是否涉及 Prisma schema**：**涉及但本轮不动**。`MarketScanRun` / `MarketRankingSnapshot` / `MarketRankingItem` / `MarketTrendReport` / `MarketSavedTopic` / `MarketCreativeBrief` 共 6 个模型。本轮只动前端，不动 schema。

---

## 3. 汇总表（一屏版）

| 项 | 仍存在 | 真实规模（实测） | 原估偏差 | 风险 | Prisma | 批次 |
|---|---|---|---|---|---|---|
| C8 RAG 可选化 | 是 | rag/ 15/3,688；真实改动 **< 80 行** | 原估"5 分工作量"偏高；**新建 CapabilityResolver 不需要** | 中（动启动路径） | 有（1 模型），不动 | **1** |
| C9 设置页合并 | 是 | views/ **7/216**；重量在 SettingsPage 517 + ModelRoutesPage 546 | **−94.7%（约 19 倍偏差）** | 低，但**收益为负** | 否 | **降级 P2 / 不做** |
| C10 资产页合并 | 是 | 7 页 **72 文件 / 16,215 行**（+style-engine 18/4,599 未计入原估） | 漏算 style-engine | **中高**（0 测试兜底） | 有（9 模型），不动 | **3** |
| C11 world wizard | 是 | 可删 **10 文件 / 1,670 行** | 低估 68%（漏 components/generator） | 中（**边界未决**：workspace 同挂一个 flag） | 有（World），不动 | **2**（阻塞：PM 确认边界） |
| C12 `/help` | 是 | **1 文件 / 216 行** + 3 处深链 | 一致 ✅ | 低 | 否 | **2** |
| C13 Debug 面板下沉 | 是 | **1 文件 / 311 行** | 一致 ✅ | 低（**净减 0 行**） | 否 | **2** |
| C14 AICockpit 文案 | 是 | 615 行；**3 个挂载点**（原方案只列 1） | 漏 2 个挂载点 | 低（需 PM 出文案） | 否 | **2** |
| C15 零引用依赖 | 是 | **12 个**（原估 9） | +3 | 低（**验收受 node_modules 限制**） | 否 | **1** |
| C16 desktop 解耦 | **否（已完成）** | — | — | — | 否 | **关闭** |
| C17 bookAnalysis 下沉 | 是 | **30 文件 / 6,568 行** | **完全一致 ✅** | 中（0 测试；与 C8 交叉） | 有（3 模型），不动 | **3** |
| C18 marketRadar 降级 | 是 | 前端 **1/424**；服务端 **1,282 行不可删** | **服务端可删性判断错误** | 低（只动前端） | 有（6 模型），不动 | **3** |

---

## 4. 建议执行顺序（3 批）

### 批次 1 ｜基础设施可选化（可并行，约 0.5 天）
**内容**：C8（RAG 可选化）+ C15（12 个零引用依赖 + manualChunks 清理）

**为什么放第一批、且为什么这两项能并行**
- 两者**零交集**（C8 全在 `server/src`，C15 全在 `client/package.json` + `client/vite.config.ts`），可以两个人同时做，互不冲突；
- 两者都是**"让依赖真正可选"**这个同一目标的两半：C8 是运行时可选、C15 是构建与依赖声明层可选（PRD 附录 B 的硬要求）；
- 两者都是**低改动量、高验证价值**：C8 实测改动 < 80 行，C15 是删 12 个包 + 改 1 个 vite 配置，做完立刻能验证"未配置 Qdrant 时全链路是否跑通"。

**验收**：① `tsc --noEmit`（server + client）通过；② `RAG_ENABLED=false` 下 server 能正常启动且不出现 Qdrant 连接错误；③ C15 需 `client build` 通过（**依赖 node_modules 修复**，这是唯一的外部阻塞）。

---

### 批次 2 ｜单点摘除（约 1 天，4 项可流水线做）
**内容**：C12（删 `/help`）+ C13（debug 面板下沉）+ C14（AICockpit 文案）+ C11（world wizard，若 PM 边界已确认）

**为什么放第二批**
- 这 4 项形态高度一致：**摘 1 条路由 / 摘 1 个挂载点 / 改 1 段文案**，改动面都在 200~600 行以内、且都是叶子节点（无下游依赖）；
- 它们**与批次 1 无依赖**，之所以排在后面，是因为批次 1 先建立"可选化"的验证基线（tsc + build 绿），批次 2 的删除才有可信的回归判定；
- 合计净减约 **2,400 行**（C11 1,670 + C12 216 + C14 文案改写 + C13 0），是本轮**性价比最高**的一批。

**验收**：① 路由表从 36 条降到 33 条；② 侧栏项从 18 条降到 15 条；③ `NovelList` / `NovelTaskDrawer` / `DirectorBookAutomationCard` 三处黑话全部消失（不能只改一处）；④ worlds 删除后 `services/world/`（21 文件 / 7,248 行）**必须仍然完整**。

---

### 批次 3 ｜导航结构重构（约 2~3 天，风险最高，单独一批）
**内容**：C10（7 个资产页合并）+ C17（bookAnalysis 下沉）+ C18（marketRadar 降级）

**为什么放最后**
- 这 3 项本质是**同一件事**：把侧栏 18 项收敛为「创作 / 资产 / 系统」三大区 + 二级 tab。它们共用**同一套 URL 契约**（`/creation-assets?zone=xxx` 之类），必须**一次性设计、一次性落地**，分两批做必然返工；
- 它们是本轮**唯一的"重写容器层"型改动**：C10 回归面 16,215 行、C17 6,568 行、C18 424 行，且**三个目录的测试文件数均为 0** —— 没有任何自动化兜底，必须留足手工回归时间；
- C17 依赖批次 1 的 C8 先补完 `BookAnalysisCharacterRagAdapter.ts:64` 的 try/catch，否则挪目录时可能把未降级的 RAG 调用暴露到新路径上。

**前置**：URL 契约文档先定稿（PM + 架构共同签字），否则不要开工。

**验收**：① 侧栏收敛到 ≤ 8 项；② 每个被折叠的原能力都有可直达 URL（含 C18 的 `AutoDirectorCreatePage.tsx:667` / `:740` 两处深链改写）；③ `MarketRadarService`（742 行）与 `services/world/`（7,248 行）**必须原样保留**。

---

## 5. 数据保护声明（本轮）

- 本文件全部结论来自**只读**的 `find` / `wc` / `grep` / Python 文本扫描，**未修改任何源文件、配置或数据库**；
- 上表中标注"有（N 模型），不动"的 6 项（C8 / C10 / C11 / C17 / C18 及其关联），本轮**一律不触碰 `schema.prisma` / `schema.sqlite.prisma` / `migrations/`**；
- 若后续 Phase 4 要删除这些模型，按 AGENTS.md 数据保护规则执行：**先备份 → 用户显式批准 → 恢复演练验证**，本轮不做。

---

## 6. 遗留待确认（需 PM / team-lead 拍板）

| # | 问题 | 影响项 | 我的技术判断 |
|---|---|---|---|
| A1 | C11：`worlds/:id/workspace`（世界工作台）是否与"向导"一起下线？它与 Wizard 共用 `worldWizardEnabled` 开关 | C11 | 建议**只删 `components/generator/`（10 文件 / 1,670 行）**，保留 workspace + visualization；并把 workspace 的开关从 `worldWizardEnabled` 拆成独立 flag |
| A2 | C9：设置项"散"的解法，是合并页面还是删设置项？ | C9 | 建议**降级不做**。7 个壳已各 10~80 行且已 lazy 分割，合并的净收益为负 |
| A3 | C18：`marketRadarService` 被 director 3 处调用，前端降级后服务端 1,282 行保留，是否可接受？ | C18 | 建议接受。删服务端会打断 director 灵感链（R 线） |
| A4 | C14 的三处挂载点是否全部改写？新文案谁出？ | C14 | 建议全部改写（否则简化不完整），文案由 PM 出稿 |
| A5 | C15 验收需要 `client build`，当前 node_modules 不完整（esbuild postinstall 被沙箱拦） | C15 | 需先修环境；或接受"仅依赖声明层删除 + 后续补 build 验证" |

---

## 7. 补录（PM 回复后的二轮实测）

PM 在 `docs/simplification/05-phase2-product-decisions.md` 中对 A1–A5 已作答。按其答复二轮 grep 复核，**其引用行号全部核实无误**，同时发现 2 项 PM 未覆盖的新问题。

### 7.1 PM 引用点逐条复核结果：✅ 全部属实

| PM 引用 | 复核结果 |
|---|---|
| `SettingsOverviewPage.tsx:19-20` 两条模型入口表述雷同 | ✅ 精确命中。`:19`「模型与厂商 / 添加模型厂商、选择模型并管理连接」vs `:20`「模型路由管理 / 为不同创作任务选择模型并检查连接状态」 |
| `WorldList.tsx:380,386` 硬链 workspace | ✅ 精确命中。两枚 Icon Button 分别「查看世界手册」「整理样本」，均 `<Link to={`/worlds/${world.id}/workspace`}>` |
| `NovelWorldHandbookDialog.tsx:554` 硬链来源世界 | ✅ 精确命中。`<Link to={`/worlds/${props.novelWorld.sourceWorldId}/workspace`}>` |
| `NovelEditView.tsx:171` `WorldSetupTab` 承担"本书的世界" | ✅ 命中（`:28` import，`:171` 渲染） |
| `AutoDirectorCreatePage.tsx:649-734` 就地渲染简报 | ✅ 精确命中。`:661-663` summary、`:670-679` selectedSignals 标签、`:725-733` 生产基础；两条深链在 `:667`、`:740` |

→ **A1（C11 边界）解除阻塞**：只删 `components/generator/` 10 文件 / 1,670 行，`components/workspace/`（15/3,283）与 `components/visualization/`（7/1,183）全保留，workspace 拆独立 flag。技术判断与 PM 一致。

### 7.2 🔴 新增 N1 ｜C9 的"10 行补丁"踩在一张字符串分支表上，比看上去危险

PM 计划把 C9 收敛为 `SettingsOverviewPage.tsx` 里约 10 行的 `entries` 目录补丁。**但该文件的渲染逻辑依赖 `title` 这个中文显示串做分支键**：

```
client/src/pages/settings/views/SettingsOverviewPage.tsx:54-64
const summary =
  title === "模型与厂商"      ? (configuredProvider ? … : "尚未配置可用的文本模型")
: title === "模型路由管理"    ? `${routeCount} 条任务路由已设置`
: title === "知识库与写法"    ? (rag?.enabled ? … : "可选增强，暂不影响开始创作")
: title === "桌面与维护"      ? "由部署环境统一处理更新与数据维护"
:                              "设置确认偏好、问题处理和通知方式";   // ← 兜底分支
```

**失败模式**：这是一个 `title`（UI 显示文案）→ `summary`（动态摘要）的**手工翻译表**，与我在此前给出的 M1–M11 手工翻译表同类。任何一次改写 `entries` 里的 `title` 文案 —— 不管是合并两条模型入口，还是改掉"桌面与维护" —— 该分支**静默落到兜底分支**，于是那张卡片会显示成自动导演的摘要文案（"设置确认偏好、问题处理和通知方式"）。**不报错、不崩溃、只是显示错**，因此不会被 tsc / build 拦住。

**给 PM / 工程师的处置建议（仍很小，约 5 行）**：把 `summary` 从"按 title 字符串匹配"改成"`entries` 数组上的一个字段"（如给每项加 `summary: (ctx) => string`），让文案与数据同在一处。这样 PM 的目录补丁和账单 ":" 卡片摘要不会因为改字而错位。若本轮不想动结构，**至少**需要在验收清单里加一条：改完 `entries` 后逐张卡片肉眼核对 6 条摘要。

### 7.3 🔴 新增 N2 ｜desktop 移除后的文案遗留（Phase 1 残留，无人接管）

desktop 已移除，但设置区仍有 3 处把它写在导航标签上，而**内容层其实已经迁移到网页端了**（`SettingsMaintenanceSection.tsx` 的正文已改为「当前使用网页端。更新与数据维护由部署环境统一处理。」），形成"内容已更新、标签没跟上"的错位：

| 位置 | 现状 |
|---|---|
| `client/src/pages/settings/components/SettingsShell.tsx:12` | `{ to: "/settings/maintenance", label: "桌面与维护", icon: MonitorCog }` |
| `client/src/pages/settings/views/MaintenanceSettingsPage.tsx:6` | `title="桌面与维护"` |
| `client/src/pages/settings/views/SettingsOverviewPage.tsx:23` | `title: "桌面与维护", description: "查看适用于当前设备的更新和数据维护。"` |

（注：`AutoDirectorBrowserNotificationSettingsCard.tsx:56,65,102` 里的"桌面提醒"指浏览器系统通知，**不是** desktop 客户端残留，不在本项范围内。）

**建议**：随 PM 的 C9 目录补丁一并改掉（约 4 行），归类为 Phase 1 收尾而非 Phase 2 新增项。

### 7.4 对 PM 开放项（Gauge 隐喻可读性）的技术答复

PM 留的开放项：`NovelProjectCard.tsx:167` 的 Gauge 图标 + "AI 驾驶舱"隐喻对新手是否可读。

实测位置修正为 **`client/src/pages/novels/components/list/NovelProjectCard.tsx:159-182`**（共 317 行）。并发现一个 PM 未提及的、更硬的证据 —— **同一行里有两枚完全相同的 `Gauge` 图标，指向两个不同的目的地**：

| 位置 | 图标 | 可见文案 | 去向 | 标注方式 |
|---|---|---|---|---|
| `:159-172` | `Gauge` | **无** | `props.onOpenCockpit(novel.id)` → 弹出 dialog（即 AICockpit） | `title` / `aria-label` = "打开 AI 驾驶舱" |
| `:175-182` | `Gauge` | **无** | `<Link to="/novels/:id/edit?directorTaskId=…&taskPanel=1">` | `title` / `aria-label` = "查看执行详情" |

同排还有 `Eye`（阅读预览）、`Download`、`Trash2`，全部是 `h-8 w-8 px-0` 的**纯图标按钮**。

**我的判断：图标隐喻确实不可读，但它只是症状；真正的坎是"入口没有任何用户语言"。** 四条依据：

1. **同一个字形承担两个语义**（"驾驶舱" vs "执行详情"）—— 图标已不可能在传达信息，用户只能靠 hover；
2. **零可见文案 + 靠 hover 才能看到 `title`** —— 而仓库里有 `client/src/components/layout/mobile/`（含 `MobileSiteShell`），说明**移动端是受支持的界面**，触屏没有 hover，这些按钮等于无标签；
3. **它是孤立隐喻** —— 全仓搜 `驾驶舱`，产物全部集中在下列 5 个文件共 **9 处**（见下）；项目其余文案是"看起来他在…"式的创作语言，没有第二个航空/机械类词汇；
4. **违反 AGENTS.md UI 文案规则** —— 规则要求回答"用户能做什么 / 系统在帮你做什么 / 下一步是什么"。"打开 AI 驾驶舱"三个都没答，只说了这个东西叫啥；而**紧挨着**的"查看执行详情"是符合规则的。

**若决定改名，"AI 驾驶舱"是一个跨文件词汇，不是一处替换**（实测计数）：

```
components/autoDirector/AICockpit.tsx                                   2 处（:333 :417 面板内自标题）
pages/novels/components/list/NovelProjectCard.tsx                       2 处（:169 :170 入口 tooltip）
pages/novels/components/NovelAutoDirectorProgressPanel.tsx              1 处（:405）
pages/novels/components/NovelExistingProjectTakeoverDialog.tsx          3 处（:334 :336 :337）
pages/novels/NovelList.tsx                                              1 处（:407 dialog 标题）
────────────────────────────────────────────────────────────────────────
合计                                                                    9 处 / 5 文件
```

**建议**：把入口文案改写纳入 **C14** 一并交付（C14 本来就在改同一个 cockpit 的话术），并在 C14 验收里加一条 —— 同一行两枚 Gauge 不得再共存（要么换掉一个字形，要么给其中一个补可见文字标签）。这比单独给 C14 开一条 front 项更省。

### 7.5 对 PM 四档排期的意见

同意 A 档（C13/C14/C12/C9 补丁，client 交互层）与我的**批次 1（C8+C15，server + 依赖层）零冲突、可并行分给两人**。PM 给 C10 排最后补充的产品理由（新手在资产区往往一无所有 → 对第一本完成率影响最小）与我给的工程理由（16,215 行 / 0 测试）叠加，**C10 排最后的结论加固**。

### 7.6 PM 二轮提问的源码核实答复

#### Q1 ｜同一对话框是否存在重复标题 —— **存在，但只在"无 AI 任务"这一个状态，且最多 2 次不是 3 次**

`AppDialogContent` 确实可见渲染标题（`client/src/components/ui/dialog.tsx:100` `<DialogTitle>{title}</DialogTitle>`），所以 `NovelList.tsx:407` 的 `title="AI 驾驶舱"` 是屏上可见的。逐分支核 `AICockpit`（`mode="focusedNovel"` → `isCompact = false`）：

| 分支 | 触发条件 | 是否渲染标题 | 是否重复 |
|---|---|---|---|
| fallback（`:333`） | `!focusProjection` | 渲染硬编码 `AI 驾驶舱` | ✅ **重复** |
| compact（`:417`） | `mode === "compact"` | 渲染 `AI 驾驶舱` | ❌ NovelList 传 `focusedNovel`，**永不进入** |
| 主分支（`:450`） | 有 projection | 渲染 `<h3>{statusHeadline}</h3>`（动态文案） | ❌ 不重复 |

→ 重复恰好发生在 `NovelList.tsx:443-444` `<AICockpit fallbackSummary="这本书没有需要处理的 AI 自动推进任务。" />`，即**这本书还没有任何 AI 任务时** —— 正是新手最可能处的状态。**客观上确实会出现同一标题重复一次，且 PM 猜的"2~3 次"实为最多 2 次。**

**附带结论：修这条不需要新文案。** 因为主分支本来就用 `:450` 的动态 `statusHeadline` 而不渲染硬编码标题 —— 说明这个组件在有数据时**根本不需要自己带标题**。fallback 分支之所以需要那条硬编码标题，只是因为对话框容器无法替它填。所以最省的改法是：**fallback 分支直接删掉 `:333` 那条硬编码标题**，由对话框标题统一承载。这一改同时消掉重复 + 减掉 9 处「驾驶舱」中的 1 处，**零新增文案**。

#### Q2 ｜右侧 Gauge 的跳转是否被主行动按钮覆盖 —— **否，目的地不同，不能据此删**

`NovelProjectCard.tsx:229-299` 的 `renderPrimaryAction` 各分支实测目的地：

| 分支条件 | 目的地 / 行为 |
|---|---|
| `short_story` | `<Link to="/novels/:id/story">` |
| `canContinueChapterBatchAutoExecution` | `onContinueWorkflow({mode:"auto_execute_range"})`（** mutation，非跳转**） |
| `canContinueDirector` | `onContinueWorkflow(...)`（**mutation，非跳转**） |
| `requiresCandidateSelection` | `<Link to={getCandidateSelectionLink(taskId)}>` |
| `canEnterChapterExecution` | `<Link to="/novels/:id/edit">`（**裸 URL，无 query**） |

而右侧 Gauge（`:175-182`）指向 `/novels/:id/edit?directorTaskId=…&taskPanel=1` —— **同一页面但带 query（直接展开任务面板）**。所以两者目的地不同，**不能以"主行动已覆盖"为由删除**。

#### Q2 补充 ｜但存在一个更强的删除理由（需工程师运行时确认）

- 左侧 Gauge（`:159-172`）打开的 cockpit 内部，`:478-482` 已有一枚 **`执行详情`** 按钮 → `handleDetails()` → `detailAction` → `onAction(...)` 或 `onOpenDetails?.()`；
- 而 `detailAction` 的来源（`:349`）是 **`focusProjection.secondaryActions?.find(item => item.type === "open_details")`** —— **由服务端下发**；
- 相对地，卡片右侧那枚 Gauge 是**客户端硬编码**同一个目的的 URL。

→ 真正的病灶不是"两个出口"，而是**同一件事同时存在服务端决定的出口和客户端硬编码的出口**，违反单一真值源（也与 AI-First 规则冲突）。**建议删除右侧 Gauge，把 `?directorTaskId=&taskPanel=1` 的能力收敛到服务端 `open_details` 动作里。**

⚠️ **静态无法证明的前置条件**：`open_details` 的具体目标是服务端数据，`grep` 不能确认它等于该 URL。**工程师需在运行时确认**；若不等于，则保留右侧 Gauge 但补可见文字标签。
另注：二者措辞本身也撞车 —— 卡片 tooltip「查看执行详情」vs cockpit 按钮「执行详情」（`:482`）。

#### Q3 ｜移动端复用确认 —— **PM 判断属实，且比"没有 hover"更具体**

`grep -rln NovelProjectCard client/src` → 仅命中 **2 个文件**：组件自身与 `pages/novels/NovelList.tsx`；`layout/mobile/` 目录下只有 `MobileSiteShell.tsx` / `mobileSiteNavigation.ts` / `useIsMobileViewport.ts`，**没有独立的移动端书目卡片组件**。→ 同一张卡在移动端渲染，属实。

补充一层实测细节：这些图标按钮的可见性由 `opacity-70 transition group-hover:opacity-100 focus-visible:opacity-100`（AI 状态按钮）与 `… group-hover:opacity-100 focus-within:opacity-100`（其余）控制 —— 触屏下它们**不会消失**（停在 70% 透明度），但仍然**没有任何文字**。所以"移动端不可用"更准确的表述是：**移动端看得见、但不知道是什么**。因此 PM 要求"至少给 AI 状态按钮一个可视标签"是对的，且应覆盖同行全部 4 枚纯图标按钮（`Gauge`×2 / `Eye` / `Download` / `Trash2`），否则只修一枚会造成同行认知不齐。

#### Q4 ｜C14 有一条被忽略的现成模板：目标话术与黑话在同一个组件里

同一文件 `AICockpit.tsx` 内，**合规文案与待清理黑话相距不到 60 行、且用同一个 `SummaryMetric` 组件渲染**：

```
:450   <h3>{statusHeadline}</h3>                              ← 动态、合规
:456   <SummaryMetric label="当前状态" …/>                     ┐
:460   <SummaryMetric label="推进概览" …/>                     ├ 合规三元组（用户语言）
:461   <SummaryMetric label="最近记录" …/>                     ┘
……
:502   后台执行                                                ┐
:508   <SummaryMetric label="排队" …/>                         │
:509   <SummaryMetric label="接手" …/>                         ├ C14 目标（后台语义）
:510   <SummaryMetric label="执行" …/>                         │
:511   <SummaryMetric label="恢复" …/>                         │
:515   等待接手 {formatDuration(...)}                           ┘
```

→ **C14 不必发明新词，只需把 `:508-515` 收敛成 `:456-461` 同一套话术粒度与语气**（"当前状态 / 推进概览 / 最近记录"这种"用户视角的结果描述"，而不是"排队 / 接手"这种"后台视角的动作描述"）。同时这也解释了 why 两排并存会显得割裂：**同一屏上下两排指标，上排讲结果、下排讲后台动作**，用户的认知负担来自这个不一致本身，而不只是那四个词。

另修正一处本文件此前的行号精度：:.5 中我曾记四人组在 `:508-511`，实测确认为 **`:508`（排队）/`:509`（接手）/`:510`（执行）/`:511`（恢复）**，原记录正确。
