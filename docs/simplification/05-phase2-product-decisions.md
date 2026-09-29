# Phase 2 界面合并 —— 产品判定口径

| 项 | 内容 |
| --- | --- |
| 责任人 | 许清楚（Xu）· 产品经理 |
| 基线 | Phase 1 已推送（`main` @ `74a03b8`，净减约 −36,210 行） |
| 上游输入 | `docs/simplification/01-product-simplification-prd.md`、`02-architecture-simplification-plan.md` 第 4.2 节 |
| 判定标准 | **新手完成率**：一个从零开始的用户，能否在最少决策下把第一本书写完。任何改动若让新手多一次无关决策、多一次跳出主路径、或多一个看不懂的词，即判负。 |
| 边界 | 本篇只出产品判定，不涉及行数与技术风险（架构师并行校准中）。结论均已读源码验证，行号可复核。 |

---

## 0. 一句话总判

八项里 **六项做、一项只做一半、一项降级为小补丁，另外明确建议不要做一项**。

合并页面本身既不提升也不损害新手完成率。真正影响完成率的是三件事：

1. **主创作区混进了不属于用户任务的元素** —— C13 的调试按钮、C14 的系统术语四联；
2. **同一个"下一步该做什么"有两个出口** —— C12 的双引导；
3. **合并时把硬链接删掉，造成静默断链** —— C10 / C17 的风险点。

因此 Phase 2 的排期不应按"页面数由多到少"排，而应按 **"这个改动是否作用在用户必经的那个动作上"** 排。详见第 9 节。

---

## 1. C9 · 设置的两道门槛（原"6 个子页合并"）

**判定（已按架构师 `04-phase2-rescoped.md` 修订）：不做"页面合并"，改做一个只有两步的目录级补丁 —— 把"模型与厂商""模型路由管理"两个入口并成一个，并把模型配置放在设置首页第一屏。6 条 URL 全部原样保留。**

> 修订说明：初判写的是"合并为单页分区"。架构师实测指出，`views/` 下 7 个壳合计只有 216 行，而真正的重量在 `SettingsPage.tsx` 517 行 + `ModelRoutesPage.tsx` 546 行；把壳并进 `SettingsPage` 只会把它撑到 700+ 行并额外引入一套 tab 状态机，净减 216 行。**这个数据说服了我**：从产品角度看也一样 —— 新手的痛点从来不是"设置分了 6 个页面"，而是"设置里有太多我看不懂的项"。合并页面不减少任何一项设置，反而把 517 行的页面做得更难维护。因此本项从 B 档降为一个小补丁。

### 为什么这样判

模型与厂商配置是**开书前的硬前置**：没有可用的文本模型，新手点什么按钮都不会有正文产出。这是整条新手链路里唯一的"不配就 0 完成率"节点。

而"模型与厂商"和"模型路由管理"并列两个同级入口（`SettingsOverviewPage.tsx` 第 19–20 行），对新手几乎无法区分 —— 它们的描述分别是"添加模型厂商、选择模型并管理连接"与"为不同创作任务选择模型并检查连接状态"。这是典型的专家视角切分，是新手进设置后遇到的第一道门槛。

### 代码证据

- `SettingsOverviewPage.tsx` 第 18–24 行的 `entries` 已经是现成的卡片网格，五个入口与其运行态摘要文案均已存在（`ViewsSettingsPage` 等 7 个路由壳只有 10–80 行，见架构师实测）；
- 第 6 个入口 `/settings/appearance` 不在概览卡片里，只在 `SettingsShell.tsx` 第 11 行的侧边导航里；
- `SettingsOverviewPage.tsx` 第 52 行已经渲染 `SettingsReadinessCard` —— 即"当前环境是否就绪"这件新手最需要的事，产品早就做了，只是排在卡片网格之前而不是之后。

### 具体做法（只有两步）

1. 把 `entries` 里"模型与厂商"与"模型路由管理"**两条并成一条**，标题取"模型与供应商"，描述改成用户能判断的那句话；两条 URL `/settings/models` 与 `/settings/model-routes` **都保留**（后者通过 `SettingsShell` 侧边导航仍可达）；
2. 让这张卡片排在卡片网格**第一位**（它现在已经是第一位，注意不要在后续改动中下沉）；顶部 `SettingsReadinessCard` 保留。

### 🔴 动手前必看：这里踩着一张"拿中文显示串当分支键"的表

架构师复核发现（`SettingsOverviewPage.tsx:54-64`）：这段卡片摘要是一个四级三元，**用 `title` 的中文文案当匹配键**来决定每张卡显示哪句动态摘要，末位是兜底 —— 而兜底那句恰好是自动导演的摘要"设置确认偏好、问题处理和通知方式"。

后果是：**只要改 `entries` 里任何一条的 `title`（也就是本次要做的合并），分支会静默落到兜底，不报错、不崩溃、`tsc` 和 `build` 都拦不住**，只是那张模型卡片会显示成"设置确认偏好、问题处理和通知方式"。对一个正在找"模型配好没"的新手，这比功能坏掉更难察觉 —— 他会以为自己在看通知设置。

**处置（采纳架构师方案，约 5 行）**：把 `summary` 从"按 `title` 字符串匹配"改成 `entries` 每项自带一个 `summary: (ctx) => string` 字段，让**文案与数据同处一地**。

这不只是代码卫生问题：**它意味着任何一次产品文案改动都可能静默破坏 UI 内容**，等于把产品文案的正常发布通道堵死了。此类装订应与已识别的 M1–M11 手工翻译表一并纳入清理。

### 合并后的卡片文案（可直接落地）

| 字段 | 现在 | 改成 |
| --- | --- | --- |
| `title` | 模型与厂商 / 模型路由管理（两条） | **模型与供应商**（一条） |
| `description` | "添加模型厂商、选择模型并管理连接。" / "为不同创作任务选择模型并检查连接状态。" | **接一个能写正文的模型，并指定哪些创作步骤用它。** |
| `summary` | 按 title 字符串分支 | 未配置 → **还没接上模型，接上就能开始写**；已配置 → `${name} · ${currentModel || "未选择模型"}` ，若 `routeCount > 0` 追加 **· 已指定 N 个创作步骤** |
| `to` | 两条各有 URL | `/settings/models`（保留）；`/settings/model-routes` 由 `SettingsShell` 导航兜住 |

### 顺带放进本补丁：Phase 1 的"桌面"残留（约 4 行）

桌面端已在 Phase 1 移除，但设置里仍有 3 处标签写着"桌面与维护"（`SettingsShell.tsx:12`、`MaintenanceSettingsPage.tsx:6`、`SettingsOverviewPage.tsx:23`；后者连描述"查看适用于当前设备的更新和数据维护"也是旧的）。而内容层 `SettingsMaintenanceSection.tsx` 早就改成"当前使用网页端。更新与数据维护由部署环境统一处理。"

**判定：这不是改名问题，是这条入口该从设置首页的卡片网格里移除。** 理由：`SettingsMaintenanceSection.tsx` 全文 18 行、只有一段说明、**没有任何可操作控件**。把它放在唯一职责是"让用户把模型配好"的这张格里，等于在一个全是动作的页面上放一个写着"你什么都不用做"的卡片 —— 而且它现在还在对一个根本没有桌面的部署形态撒谎。

具体处置（保留能力可达）：

1. 从 `SettingsOverviewPage` 的 `entries` 里删掉这条（卡片网格从 5 张降到 3 张）；
2. `SettingsShell.tsx:12` 与 `MaintenanceSettingsPage.tsx:6` 的标签/标题改为 **"数据与备份"**（路由 `/settings/maintenance` 不变，`SettingsShell` 侧边导航里仍可达）；
3. 保留备份提示原文（"需要备份或迁移数据时，请保留服务端数据目录中的数据库文件与导出文件。"）—— 这是真有用的信息，只是不该占一格。

⚠️ 不要顺手改 `AutoDirectorBrowserNotificationSettingsCard.tsx` 里的"桌面提醒"，那里指的是浏览器系统通知，不是本残留。

### 验收口径

新手在任意页面点击"系统设置"后，**零滚动、零搜索**能看到"模型是否已配好"的结论；点一次进入即到模型的输入框。

### 不要做的部分

不要为了让 URL 变短而删掉 `/settings/models` 与 `/settings/model-routes`。它们是外部文档、书签、以及 `SettingsNavigationCards.tsx` 第 56 行等处的引用目标。

---

## 2. C10 · 资产组 9 个页面合并为单页 + 二级 Tab

**判定：做，但这是全流程风险最大的一项，必须最后做；并且 9 条路由一条都不能删 —— 唯一可以整块删掉的是孤儿文件 `NovelTitleWorkshop.tsx`。**

### 为什么这样判

这 9 个能力对新手的价值，**几乎全部已经在创作流程内被消费掉了**。新手不是在"资产页面"里用它们，而是在开书、写正文的过程中被就地提供。所以：

- 把它们从一级导航降到二级 Tab，新手的完成路径不会变长；
- 但把它们的 URL 删掉会立刻断链 —— 因为流程内的那些入口，绝大多数是**硬链接跳转**。

### 这些能力在写作流程里排第几

| 能力 | 流程内何时用到 | 流程内入口（证据） | 降级建议 |
| --- | --- | --- | --- |
| 题材基底 `/genres` | 开书第 1 步就要选 | `AutoDirectorCreatePage.tsx` 第 319 / 478 行的创建地基选择器 | 降二级 Tab |
| 推进模式 `/story-modes` | 同上，与题材并列选择 | `AutoDirectorCreatePage.tsx` 第 161–206、478–495 行 | 降二级 Tab |
| 标题 `/titles` | 填书名时 | `NovelCreate.tsx` 第 218 行、`BasicInfoTab.tsx` 第 37 行（`NovelCreateTitleQuickFill`） | 降二级 Tab |
| 知识库 `/knowledge` | 绑定资料到本书 | `NovelEditView.tsx` 第 16 行、`RuntimeSidebar.tsx` 第 3 行 | 降二级 Tab，但**保留异常徽标** |
| 世界样本 `/worlds` | 世界设定步骤 | `NovelEditView.tsx` 第 171 行（`WorldSetupTab`）、`NovelWorldManagerCard` | 降二级 Tab |
| 写法引擎 `/style-engine` | 推荐写法时 | `NovelStyleRecommendationCard.tsx` 第 82 / 85 行 | 降二级 Tab |
| 反 AI 规则 `/anti-ai-rules` | 规则面板内跳转 | `WritingFormulaRulesPanel.tsx` 第 37 行 | 降二级 Tab |
| 基础角色 `/base-characters` | 新建角色时 | `CharacterCreateDialog.tsx` 第 179 行 | 降二级 Tab |
| 视觉资源 | 侧边栏对话框 | `Sidebar.tsx` | 维持现状（本就是对话框） |

结论：**没有一项位于"第一本书能否完成"的关键路径上**。第一本书的新手通常没有任何存量资产，这个区域对他而言是空的。所以它的信息架构层级对新手完成率影响最小，而改动面最大 —— 这是它必须排最后的理由。

### 必须保留直达 URL 的硬链接清单

合并只能改这些地方指向的**形态与层级**，不能让它们失效：

- `CharacterCreateDialog.tsx:179` → `/base-characters`
- `NovelStyleRecommendationCard.tsx:82, 85` → `/style-engine`（含 `?mode=imitate`）
- `WritingFormulaRulesPanel.tsx:37` → `/anti-ai-rules`
- `WorldGenerator.tsx:345` → `/genres`
- `NovelWorldHandbookDialog.tsx:554` → `/worlds/{id}/workspace`
- `KnowledgeDocumentsTab.tsx:228, 232` → `/book-analysis`（带 `?documentId=` / `?analysisId=`）
- `KnowledgeDocumentPicker.tsx:116` → `/book-analysis?analysisId=`
- `useAnalysisPublishing.ts:76` → `/style-engine?profileId=&source=book-analysis`
- `KnowledgeSettingsPage.tsx:25` → `/knowledge?tab=settings`

### 唯一建议直接删掉的

`client/src/pages/novels/components/titleWorkshop/NovelTitleWorkshop.tsx` —— 全项目检索只出现在它自己的文件里，没有任何引用。真正被使用的是 `NovelCreateTitleQuickFill`。删它不影响任何界面。

反过来，**不建议删 `/titles` 页面本身**：它的 `TitleLibraryPanel`（已保存标题库）是流程外的管理能力，与流程内的即时取名不是一回事。

### 验收口径

侧边栏"创作资产"点击后进入单页，`genres` / `story-modes` / `titles` / `knowledge` / `worlds` / `style-engine` / `anti-ai-rules` / `base-characters` 八个 Tab 均可直达；上表 9 条硬链接逐条点击不 404。

### 不要做的部分

不要在合并时顺手清掉 `/knowledge` 的异常徽标 —— `Sidebar.tsx` 第 135 行在索引失败数大于 0 时会给它打标。资产页若把这个信号藏掉，索引失败的新手会静默地拿到更差的检索质量而不知道。

---

## 3. C11 · 世界样本 Wizard 下线，保留只读列表

**判定：做。Wizard 下线，"想手写世界观"的路径仍然存在，就在小说工作台里，不需要任何额外开发。**

### 为什么这样判

Wizard 是一个多步骤的世界观生成器。对新手而言它是负资产：**在第一本书之前，新手并不知道自己的世界该有哪些字段**，Wizard 让他先回答一组自己答不上来的问题。真正的完成路径是让自动导演在 `world_setup` 阶段先产出一份，新手看到实体后再改。

但"完全手写"必须有出口 —— 否则产品就从"简化"滑向"限制"。这个出口已经存在。

### 代码证据

- `WorldList.tsx` 第 258–260 行与第 297–299 行：Wizard 的两个入口（包含空态里的"生成第一个世界样本"）已经由 `featureFlags.worldWizardEnabled` 包着；
- `router/index.tsx` 第 78 / 82 行：`/worlds/generator` 与 `/worlds/:id/workspace` 在开关关闭时会 `Navigate` 重定向到 `/worlds`，已经是现成行为；
- `NovelEditView.tsx` 第 171 行：小说工作台内已渲染 `WorldSetupTab`；另有 `NovelWorldManagerCard` 挂在同一个小说卡片区；
- `components/onboarding/creationSetupState.ts` 第 6 行：`/worlds/generator` 本就在 `GATED_ROUTE_PREFIXES` 里，即产品早先已把它定性为"次级目的地"。

也就是说：**关掉开关不需要写任何新代码，也不会留下死链接。**

### 具体做法

1. 关闭 `featureFlags.worldWizardEnabled`，删掉 `components/generator/` 这 10 个文件（架构师实测 1,670 行）与 `WorldGenerator` 路由；
2. **保留 `/worlds` 只读列表与 `/worlds/:id/workspace` 详情**（含 `components/workspace/` 与 `components/visualization/`）。这一点必须显式写死 —— 见下方 A1 答复；
3. 把 workspace 的开关从 `worldWizardEnabled` **拆成独立 flag**，否则关向导会连带关掉工作台；
4. 在列表页的手写入口上补一句用户视角说明，告诉用户这本书的世界可以在工作台里调整（文案不得出现"原本/不再/已下线"这类变更叙述）。

### 验收口径

新手在一本小说的设定区里能直接编辑世界内容；`/worlds/generator` 访问时落在 `/worlds` 且不报错。

### 不要做的部分

不要顺手删 `/worlds` 列表页。它是唯一能让用户跨书复用世界观的地方，也是 `NovelWorldHandbookDialog.tsx` 第 554 行"打开来源世界手册"的落点。

### 补充（本轮）：删生成器不会让 `/worlds` 变成死库，但会让它变成"看不见来源"

team-lead 发现 `client/src/api/world.ts:118` 的 `createWorld` 全仓唯一调用方就是要删的 `WorldGenerator.tsx:259`，担心删掉后样本库只能读、填不进去。**结论：这个担心不成立，但由此暴露的问题必须一并处理。**

**为什么不会变成死库。** 不需要依赖 `onSaveToLibrary` —— 那条是**次要路径**，`NovelWorldLibrarySaveService.ts:23-25` 在已有 `sourceWorldId` 时会直接抛错，只服务于"历史上建过但没入库"的兜底。真正的写入是自动的：

- `NovelWorldManualService.ts:76-110`：小说内手建世界时，同一 `prisma.$transaction` 内 `tx.world.create`（:77）→ `tx.worldSnapshot.create`（:96）→ `tx.novel.update({ worldId })`（:103）→ insert `NovelWorld` 带 `sourceWorldId = world.id`（:111-134）；
- `docs/wiki/architecture/world-context-gateway.md:31` 是成文规则：新建本书世界必须**在同一事务内**创建外部 `World` 样本，**不再要求用户额外执行"保存到世界库"**；`:38` 补明 `saveToLibrary` 仅为兼容字段。

即 `WorldSetupTab` 的 `onCreateManual` 与 `onGenerate` 任一条都能把样本灌进 `/worlds`，**用户无需任何点击**。A1 边界成立，不重划。

**但因此多出来的产品债务。** 沉淀是完全隐式的：用户在小说里搭世界，`/worlds` 默默多一条。删掉 `WorldList.tsx` 两个 CTA 后，页面变成"只看得见结果、看不见来源"，而新部署的 `/worlds` 恰恰是空的 —— 空态就是新手对这一整块的第一印象。必须同批次落三处文案：

| 位置 | 现文案 | 替换文案 |
| --- | --- | --- |
| `WorldList.tsx:295` | 还没有世界样本 | **还没有可复用的世界** |
| `WorldList.tsx:296` | 生成一个可复用世界，为后续小说准备规则、舞台和冲突来源。 | **在你的小说里搭好一场世界观，它会自动收进这里，下一本书可以直接接着用。** |
| `WorldList.tsx:297-301` | `<Link to="/worlds/generator">生成第一个世界样本</Link>`（被 `worldWizardEnabled` 包着） | **`<Link to="/novels">去看看我的小说</Link>`**（`variant="outline"`），并去掉 flag 包裹 —— `worldWizardEnabled` 随本次一起下线 |
| `WorldList.tsx:257-263` | 顶部操作区容器 | **整块删除**，不留空容器（右上角留视觉空洞比没有按钮更像坏了） |
| `WorldList.tsx:252-254` | 页面说明 | 追加一句：**这里收录的是随小说沉淀下来的世界。想再加一个，去小说设定区搭就好，它会自动出现在这里。** |

`:266-276` 的"如何把样本用于小说"折叠块不动，第 2 步"从小说基础信息页导入"依旧成立。

### 补充（本轮）：反向链路已存在，C11 后它是新手认知样本库的唯一入口

`NovelWorldHandbookDialog.tsx:552-556` 在 `sourceWorldId` 存在时渲染 `<Link to={`/worlds/${sourceWorldId}/workspace`}>打开来源世界手册</Link>`。由于 `sourceWorldId` 在建世界的事务里**必然写入**，这个按钮必然出现 —— 小说 → workspace 的路从未断过，反证 A1 里"workspace 必须保留"的判断，它不是孤岛而是这条链路的落点。

可选（P2）：标签改为 **"在世界样本库中打开"**。C11 后这条链接会成为新手唯一一次意识到样本库存在的机会，"来源"是内部视角的词。

### 补充（本轮）：独立 flag 拆分要给工程师的去风险说明

同意 team-lead 新增 `worldWorkspaceEnabled`（`VITE_WORLD_WORKSPACE_ENABLED`）。补充一条证据让他放心删生成器：**`WorldWorkspace.tsx:15-16` 只 import `createWorldLibraryItem` 与 `createWorldSnapshot`（对已有 World 加条目 / 打快照），不 import `createWorld`** —— 工作台的编辑能力不依赖被删的那个函数，不会退化成只读壳。

---

## 4. C12 · `/help` 与首页 `HomeNextActionPanel` 的双引导

**判定：保留首页卡片作为唯一主引导，`/help` 降级为无一级导航项的"完整路线"页。但这一项不能只做"删一个"，真正的病灶是两套数据各自算了一遍"当前进度"。**

### 为什么这样判

问题不是"有两页"，而是**同一时刻两处会给出不同的"你现在该做什么"**：

- `HomeNextActionPanel` 用 `pages/home/homeJourney.ts` 的 `buildHomeJourney(task)`，从**任务的 workflow 展示阶段**本地推导 6 组进度（项目设定 / 故事规划 / 世界与角色 / 卷与章节 / 正文创作 / 质量完善）加一条百分比；
- `HelpPage` 用 `getFirstNovelOnboarding`（服务端 `FirstNovelOnboardingService`），拿的是**里程碑 + 主行动按钮 + `optionalEnhancements`**，且 `HelpPage.tsx` 第 52 行会在任务运行时轮询刷新。

数据源不同偏差必现。对新手而言，"两个地方都说我在第 3 步"比"只有一个地方说"更糟 —— 他要去判断哪个准。这才是双引导真正扣新手完成率的地方。

### 首页卡片能承载 5 步展开态吗

**能，而且已经在承载。** `HomeNextActionPanel.tsx` 已经渲染 `buildHomeJourney(task)` 给出的 6 组 `ol` 列表加百分比条（`homeJourney.ts` 第 13–24 行定义了这 6 组）。它缺的不是容器，而是 `HelpPage` 独有的两件东西：`primaryAction`（例如 `open_quick_setup`）与 `optionalEnhancements` 的自证说明。

### 具体做法

1. 从一级导航移除 `/help`（`Sidebar.tsx` 第 52 行、`mobileSiteNavigation.ts` 第 24 / 65 行）；
2. **保留 `/help` 路由**：`FirstNovelJourneyStrip.tsx` 第 20 行与 `QuickSetupDialog.tsx` 第 243 行都硬链到它，这两处出现在新手还不认识侧边栏的时刻，删了会留下看得见的死胡同；
3. 首页卡片的"下一步"统一取服务端 `FirstNovelOnboardingService` 的 `primaryAction`，路线图作为可展开的详情；`buildHomeJourney` 退化为只画"这本书写到第几步"的进度条，不再承担行动推荐；
4. 两处文案措辞必须可区分：首页卡片说"现在该做什么"，`/help` 说"完整路线怎么看"。

### 修订（本轮）：同意删路由，但两处深链必须按 `kind` 分派，不能按 `route`

team-lead 决定删掉 `/help` 路由而不只是导航，并实测到两处深链。我原方案（保留路由）被他自己 find 的更好解法替代：**不去泛泛的向导页，直接跳服务端算出的下一步**。这个解法比我原方案准，**改判：同意删路由**。

但这个组合有一个会在最糟场景炸掉的陷阱，读源码才发现：

`server/src/modules/setup/onboarding/application/FirstNovelOnboardingService.ts:122-126`，默认分支（即 setup 未就绪、没配模型）下发的是

```
{ label: "快捷配置模型", route: "/help", kind: "open_quick_setup" }
```

—— **全新用户拿到的 `primaryAction.route` 就是 `/help` 本身**。所以 `to={journey.primaryAction.route ?? "/novels/create"}` 这种改法，会让**恰好是新手**的用户跳到刚删掉的路由上。这是整条链路最前端的一个节点，比任何别的位置都不能断。

正确做法不是读 `route`，是**先读 `kind`** —— 模板就在要删的那个页面里：`HelpPage.tsx:76` 判 `kind === "open_quick_setup"` → 调 `openQuickSetup()` 弹配置框、**不跳转**；否则 `:84` 才用 `route`。两处深链（`FirstNovelJourneyStrip.tsx:20`、`QuickSetupDialog.tsx:243`）照抄这套分派即可，行为与被删页面完全一致，零回归。

两条附带确认：① `client/src` 全仓**只有 `HelpPage.tsx:84` 一处**消费 `primaryAction.route`，删页后无漏网点；② 建议顺手清掉服务端 `:124` 那个硬编码 `route: "/help"`（`open_quick_setup` 本就不需要 route），否则后续任何人再读这个字段都会踩同一个坑。

**落地状态（读源码确认，本轮）：三项全部已落地** —— `shared/types/onboarding.ts:78` 已为 `route?: string`；服务端默认分支已不再下发 `route`；`FirstNovelJourneyStrip.tsx:50-60` 已按 `kind` 分派。上一轮报告的 `bec1f2d` 硬编码死胡同**已消除**，此项可封。

### 补充（本轮）：快捷配置成功态只留一个出口

`QuickSetupDialog.tsx:241-243` 的 `showFirstNovelHandoff` 分支原有两个并列按钮（`开始创建第一本小说` → `/novels/create`，`用一句话开始第一本小说` → `/novels/auto-director`）。**删前者，保留后者。**

理由不是"手动 lanes 不重要"，而是**它已经有一个权重正确的家**：`HomeNextActionPanel.tsx:220` 的 `StarterPanel` 把 `/novels/create` 放在三级 ghost 位（一级 `/novels/auto-director`、二级短篇、三级"手动创建小说"）。在服务端已经算好"下一步"的成功态里再并列一个平级 CTA，等于把"矩阵决策"提前到用户刚配完模型的那一秒 —— 而那一秒用户只有一个问题：我现在能写了吗。

### 补充（本轮）：`FirstNovelJourneyStrip` 的文案口径

现文案三个问题：**① "向导"是系统构件的名字，不是用户要做的事；② "步" + 分数是过程性叙述**，AGENTS.md UI Copy Rules 明令不许；③ 右侧只有一个 `ArrowRight` 图标，**没有动词**，新手不知道点下去会发生什么。按下表替换（`:30` / `:31` / `:36-47`）：

| 位置 | 现文案 | 替换文案 | 为什么 |
| --- | --- | --- | --- |
| 标题 `:30` | 第一本书向导 | **写你的第一本书** | 说用户能做什么；且六个服务端分支全程不变，不会随进度跳字（避免造变更叙述） |
| 上方计数 `:31` | `{completedCount}/{totalCount} 步完成` | **删掉** | "步"是过程叙述；进度由下方 5 个点承载，视觉信号不丢 |
| 正文 `:33` | `journey.headline` | 保持读服务端 `headline` | 分支文案本身已达用户视角（"用一句灵感开始第一本小说" / "AI 正在完成第一章" / "第一章可以阅读"） |
| 右侧动词 `:36-46` | 只有 `ArrowRight` | **在箭头左侧渲染 `journey.primaryAction.label`**（`sm` 以上显示文字，移动端只留箭头） | 用服务端已算好的动词，客户端不新增分支表，符合 AI-First |

配套的服务端标签微调（`FirstNovelOnboardingService.ts`，P1，可与 C14 文案批次合并做）：`:124` `快捷配置模型` → `接入写作模型`（与已落地的设置卡"模型与供应商"措辞同源）；`:157` `选择生产方式` → `选择怎么写正文`；`:176/192` `查看并恢复` → `处理并继续写`（"恢复"在技术词移除清单里）。

---

## 5. C13 · `DirectorFactDebugDialog` 移出主操作区

**判定：做，但不要用 URL 参数作为它的唯一入口 —— 挪进已经存在的"项目工具"对话框，保持生产环境可达。**

### 为什么这样判

`NovelEditView.tsx` 第 288 行把它**裸露**挂在 StepHero 操作行里，夹在导出对话框和"项目工具"之间。`DirectorFactDebugDialog.tsx` 渲染的是一枚带 Bug 图标、写着"调试检查"的按钮 —— 在这个位置上，它与旁边的"导出""项目工具"视觉权重完全相同。

新手写第一本书时，主操作行里出现一个他不该点、点了也看不懂的东西，是纯粹的决策税：**每一次他都要先判断"这个跟我有关吗"**。

### 为什么不建议 URL 参数

URL 参数一旦作为唯一入口，就变成用户可以粘贴、可以误存书签、可以分享给别人的半公开入口。调试面板给错了人，成本不是"多一个按钮"，而是"用户拿着调试结论来问为什么我的书是这样"。相比之下放进一个本来就存在的次级收纳位，既不给它新的可见度，也不增加传播面。

### 具体做法

1. 从 `NovelEditView.tsx` 第 288 行移除裸挂载；
2. 把它作为「项目工具」对话框内的一个折叠区块 —— 这个对话框自己的描述就是"收纳次级信息"（第 298 行），语义完全吻合；
3. 保持在生产环境可见：开发者与技术支持仍然两次点击可达；
4. 顺手修掉第 298 行那段描述文案，它同时犯了两条 AGENTS.md 的高优先级规则：把内部布局意图写给了用户（"避免主工作区被项目辅助信息挤满"），以及用了系统术语（"恢复接管"）。

### 验收口径

新建/任意小说的编辑页主操作行只剩"导出"与"项目工具"；调试入口在"项目工具"内可见可用，无需改环境变量或加 URL 参数。

---

## 6. C14 · `AICockpit` 后台执行四联的文案改造

**判定：做。删掉"接手"与"恢复"两格，其余逐句改成用户视角。**

### 先修正一处范围误判

这四联**不在 `NovelList` 卡片上**。它们在 `AICockpit.tsx` 第 497–519 行，而 `AICockpit` 是从 `NovelProjectCard.tsx` 第 167 行那个仪表盘图标按钮（`title="打开 AI 驾驶舱"`）点开的对话框里。也就是说它已经**折叠在用户主动点开的第二层**里。

这个区别决定了改造尺度：**它不需要删掉重做，只需要改词 + 收掉两格**。真正需要注意的反而不是这里，而是这枚 Gauge 图标按钮本身 —— 如果它在卡片上的隐喻对新手不可读，"驾驶舱"这个比喻就是新的负债。

### 修正一处挂载点口径

架构师实测指出同类文案有 **3 个挂载点**，不止初判里的 1 个：

| 挂载点 | 说明 |
| --- | --- |
| `pages/novels/NovelList.tsx:432` / `:443` | 初判已覆盖 |
| `pages/novels/components/NovelTaskDrawer.tsx:357` | 初判漏了 |
| `components/autoDirector/DirectorBookAutomationCard.tsx:39` | 初判漏了，且这个卡片自身还被别处复用 |

**第 6 节的替换表适用于全部三处，必须一次改完**，否则同一组黑话会在任务抽屉里继续出现，等于没改。

改动前还需确认一处约束：`NovelTaskDrawer` 是任务中心。按 AGENTS.md 的任务中心规则，它是**只读运行记录**，不得在其中新增任何控制按钮 —— 本次只改文案，不得趁机加动作。

### 补充：这枚 Gauge 图标不可读，并入本项交付

架构师判断"驾驶舱"隐喻不可读，我复核后**同意，并给出落地口径**。补充三条我看到的证据：

1. **同一行真的有两枚完全相同的 `Gauge`** —— `NovelProjectCard.tsx:159-174`（弹 Cockpit 对话框）与 `:177-183`（跳 `/novels/:id/edit?directorTaskId=…`）。且两者都只在 `narrativeForm !== "short_story"` 时渲染、后者还要求存在任务 —— **即"正在用自动导演写书"这个典型新手场景，恰恰是两枚同时出现的时候**；
2. **对话框中已经有一句完全合规的现成文案**：`NovelList.tsx:408-412` 的描述是"查看这本书的 AI 推进状态和下一步动作。"它既不孤立也不违规，却被一个与之无关的按钮文案盖住。改按钮时直接沿用这套词汇即可，不需要发明新词；
3. 全仓"驾驶舱"共 **9 处 / 5 个文件**（`AICockpit.tsx:333,417`、`NovelList.tsx:407`、`NovelProjectCard.tsx:169,170`、`NovelAutoDirectorProgressPanel.tsx:405`、`NovelExistingProjectTakeoverDialog.tsx:334,336,337`）。这是跨文件词汇替换，不是改一处 tooltip —— 请工程按此估工作量。

**落地口径（两件事，都要做）**

其一，**换词，并沿用产品已有词汇**：

| 位置 | 现在 | 改成 |
| --- | --- | --- |
| `NovelProjectCard.tsx:169,170` | 打开 AI 驾驶舱 | **查看 AI 推进状态** |
| `NovelList.tsx:407`（对话框标题） | AI 驾驶舱 | **这本书的 AI 推进状态** |
| `AICockpit.tsx:333` / `:417` | AI 驾驶舱 | **AI 推进状态** |
| `NovelAutoDirectorProgressPanel.tsx:405` | 可在 AI 驾驶舱查看进度 | **可在「AI 推进状态」查看进度** |
| `NovelExistingProjectTakeoverDialog.tsx:334,336,337` | 可在 AI 驾驶舱查看… | **可在「AI 推进状态」查看…** |

注：`NovelExistingProjectTakeoverDialog` 那三句原文含"排队""接管任务"等本轮正在清理的术语（例：`:337` "查看排队和执行进度"），统一改为 **"查看还没写完的内容和下一步"**，与本文档第 6 节的替换表保持一致。

其二，**同一行的两枚重复图标必须消掉，但不是改 tooltip 了事**。这枚 duplicate 与 C12 是同一个病灶 —— 同一件事给了两个出口。优先方案是把两枚合并为一枚并给可见文案；若工程确认主行动按钮已覆盖右侧那枚跳转目的地，则直接去掉右侧那枚（`?directorTaskId=&taskPanel=1` 的 URL 能力保留）。

另外提醒工程：`NovelProjectCard` 在移动端也在用（没有独立的移动端书目卡片），而这些图标按钮靠 hover 才显形 —— 触屏无 hover。所以这里的修复**不能只改 `title`**，至少要给这枚 AI 状态按钮可视标签。

### ⏳ 落地状态（读源码确认，本轮）

**第 6 节主体替换表已经在代码里落地了** —— `AICockpit.tsx` 现行为：`workerStateLabel`（`:242-251`）十条改词全部就位、`workerStateDetail`（`:261/264/267`）三句改词就位、区块标题 `:502` 已是「自动写作状态」、四联已收成 `:507-510` 的**两格**（待写内容 / 正在写）、`:513` 已是「已等待 {时长}」。

**还剩四件事没做**：9 处"驾驶舱"换词、fallback 重复标题、右侧 Gauge、移动端可视标签。

**并修正一条我自己的口径**：此前写的"3 个挂载点要分别改词"是错的 —— 三处（`NovelList.tsx:432`、`NovelTaskDrawer.tsx:357`、`DirectorBookAutomationCard.tsx:39`）渲染的都是同一个 `AICockpit` 组件，改词在这个组件内部，**改一处自动覆盖三处**。工程估时按"一个文件"算，不要按三处乘。

### 补充一：fallback 分支的重复标题（架构师定位清楚，采纳，补两个前置）

`AppDialogContent`（`ui/dialog.tsx:100`）会把 `title` 渲染成可见的 `<DialogTitle>`，而 `AICockpit` 的 fallback 分支自己在 `:333` 又渲染一次硬编码「AI 驾驶舱」。该分支仅在 **没有 projection** 时走 —— 也就是 `NovelList.tsx:443` 那句 fallbackSummary「这本书没有需要处理的 AI 自动推进任务」，**恰恰是新手最可能处的状态**。主分支用动态 `statusHeadline`，不重复。

采纳架构师方案：**fallback 分支删掉 `:333` 那个标题节点，由容器标题统一承载**，零新增文案。两个前置条件：

1. **必须确认三个挂载容器都有各自的可见标题** —— `NovelList` 的对话框有（`{...title}`），但 `NovelTaskDrawer`（抽屉）与 `DirectorBookAutomationCard`（卡片）也需要各有一个；否则删掉后 fallback 态会变成一块无标题的内容。
2. **顺带删掉整个 `compact` 分支**：`mode` 默认值是 `"focusedNovel"`（`AICockpit.tsx:314`），全仓静态检索**没有任何一处传 `mode="compact"`**，其余两处挂载分别显式传 `focusedNovel` 或走默认值 → `isCompact` 恒为 false，`:417` 是死代码。删分支比改名更彻底，同时再消掉 1 处"驾驶舱"。请架构师确认没有动态字符串传值。

同区块还漏了一处：`AICockpit.tsx:337` 的 Badge 兜底写着「未开启」，与本 replacements 词汇不一致，改成 **还没开始自动写作**。

**换词后全仓"驾驶舱"归零**（9 处去向：`AICockpit:333` 删、`:417` 删分支、`NovelProjectCard:169,170` 改、`NovelList:407` 改、`NovelAutoDirectorProgressPanel:405` 改、`NovelExistingProjectTakeoverDialog:334,336,337` 改）。

### 补充二：右侧 Gauge 的处置口径（我上一轮的定性不准，已修正）

我此前把两枚 Gauge 归因为"同一件事两个出口"。架构师把 `renderPrimaryAction`（`NovelProjectCard.tsx:229-299`）各分支逐个读过后证明**目的地不同**：主行动要么 mutation、要么跳 `getCandidateSelectionLink`、要么跳裸 `/novels/:id/edit`；而右侧 Gauge 跳的是**同页但展开任务面板**的 `?directorTaskId=…&taskPanel=1`。所以"重复出口"的说法不成立，**撤回**。

真正的缺陷更重：cockpit 里 `:479-484` 那枚「执行详情」按钮，走的是 `:349` 的 `focusProjection.secondaryActions?.find(type === "open_details")` —— **服务端下发**；而卡片右侧这枚是**客户端硬编码同一目的的 URL**。同一件事同时存在服务端决定的出口与客户端写死的出口，违反单一真值源，也撞 AI-First 规则。

### 右侧 Gauge：前置条件已验证通过，按路线一执行

team-lead 做了运行时验证，我要求的那个前置条件满足：服务端 `buildNovelHref(novelId, { taskId, taskPanel: true })` 产出 `/novels/{id}/edit?directorTaskId={taskId}&taskPanel=1`，与卡片右侧硬编码的 URL **逐字符一致**；且 cockpit 里那枚「执行详情」确实会渲染（`AICockpit.tsx:348-350` 从 `secondaryActions` 取 `open_details`，`showDetailsAction` 默认 true）。

→ **执行路线一：删掉 `NovelProjectCard.tsx:177-183` 这枚 Gauge，左侧那枚保留并补可见文案。** 补一条验收：`?directorTaskId=&taskPanel=1` 此后必须只由服务端产出，**卡片里不许再留客户端拼的同款 URL**。

### 「AI 驾驶舱」换词立即执行（不等状态词重测）

采纳 team-lead 的判断与理由：工程师已把这个词做成**可见文案**（`<span>AI 驾驶舱</span>`），黑话现在直接印在小说卡片上，比只做 tooltip 时更糟；且容器标题不依赖状态词，不存在"改两遍"的问题。所以第 6 节那张替换表**现在就做**，不与其他改动排队。

### 补充三：这行图标的可读范围，我同意扩大到整行，并补三条工程要害

架构师把"移动端没有 hover"修正得更准：这些按钮是 `opacity-70 group-hover:opacity-100`，触屏下**不会消失（停在 70%）**，所以问题不是看不见，而是**看得见但不知道是什么**。这个定性比我的准。

**同意把可视标签扩大到整行**（同意他的理由：只修一枚会让这一行看起来更不齐）。三条要害：

1. **先确认同类卡片不是只有一张**：`NovelList.tsx` 同时渲染 `NovelProjectCard`（`:352`）、`NovelShelfCard`（`:344`）、`NovelContinueCard`（`:335`）。只改其中一张，会让同一个书架出现两种规格。**三张都要过一遍**，哪怕最后只改有问题的那张。
2. **不要为此引入下拉菜单**：`client/src/components/ui/` 下**没有 `dropdown-menu` primitive**，做"更多"菜单要新增依赖与控件，与简化目标相反。就用图标 + 2 字短标签。
3. **"看不清"不是安全措施** —— 我原本担心给删除加标签会增加触屏误删，查证后撤回：`NovelList.tsx:205` 的 `handleDelete` 已有 `window.confirm` 兜底，风险不存在。所以删除也给标签，按整行同规格处理。

### 具体文案建议

位置均在 `client/src/components/autoDirector/AICockpit.tsx`（另两处按同一份表同步）：

| 位置 | 现在 | 改成 | 理由 |
| --- | --- | --- | --- |
| 第 502 行区块标题 | 后台执行 | 自动写作状态 | "后台"讲的是系统在哪儿跑，用户关心的是"我的书还在写吗" |
| `labels.idle`（第 242 行） | 未运行 | 还没开始自动写作 | 补上主体 |
| `labels.queued_waiting_worker`（243） | 等待接手 | 马上接着写 | "接手"是内部调度词 |
| `labels.leased_starting`（244） | 正在接手 | 正在开始写 | 同上 |
| `labels.running_step`（245） | 自动推进中 | 正在自动写作 | 指向产出而非机制 |
| `labels.waiting_gate`（246） | 等待确认 | 等你确认后继续 | 指向用户的下一步动作 |
| `labels.auto_recovering`（247） | 恢复中 | 正在接着上次没写完的写 | "恢复"讲机制，用户要知道的是结果 |
| `labels.cancelled`（248） | 已停止 | 已停止自动写作 | 补主体 |
| `labels.failed_recoverable`（249） | 等待恢复 | 遇到问题，会自己重试 | 明确"你不用做什么" |
| `labels.failed_hard`（250） | 需要处理 | 需要你处理一下 | 明确"这次要你来" |
| `labels.succeeded`（251） | 已完成 | 已完成 | 保留 |
| `workerStateDetail` 第 261 行 | 任务已排队，后台执行接手后会继续推进。 | 前面还有几步，轮到这本书会继续写。 | 去掉 lease 术语 |
| 第 264 行 | 后台执行正在处理当前任务。 | 正在写当前内容，写完会自动往下推进。 | 同上 |
| 第 267 行 | 后台执行中断后会从最近进度尝试恢复。 | 中途断掉的内容会从上次写到的地方接着写。 | 同上 |
| 第 508–511 行四联 | 排队 / 接手 / 执行 / 恢复 | 只留两格：**待写内容** = `queuedCommandCount`；**正在写** = `runningCommandCount + leasedCommandCount` | 接手与恢复是用户不可见的内部态；展示它只会诱导用户以为自己该做点什么 |
| 第 515 行 | 等待接手 {时长} | 已经等待 {时长} | 同上 |

### 必须保留的部分

第 489–495 行的 `circuitBreaker` 区块（"自动推进已暂停" + 恢复建议）**一个字都不要动**。这是自动链路上唯一给用户的自救出口，删掉它等于让新手在卡住时既看不到原因也看不到动作 —— 会直接打穿完成率。

---

## 7. C17 · 拆书从一级导航下沉到"创作资产"

**判定：做下沉，但下沉的是导航层级不是能力；`/book-analysis` 路由与其 query 参数必须原样保留。**

### 为什么这样判

拆书对新手的全部价值在于"照着一本书写"，而这个入口**已经在主创作流的第一屏**：`AutoDirectorCreatePage.tsx` 第 739 行的「照着一本书写」按钮，开的就是 `ReferenceNovelStartDialog`（第 568 行挂载）。

把它再挂一个一级导航项，等于给新手制造一道无意义的选择题：**"我要写书，是先去'拆书'，还是先去'创作向导'？"** 正确答案是后者，但导航的顺序暗示它们同级。

同时它本来就被产品自己定性为次级：`creationSetupState.ts` 第 4 行，`/book-analysis` 在 `GATED_ROUTE_PREFIXES` 里 —— 未配好环境的新手进这个路由会被弹回去配模型。

### 代码证据：这些深链一条都不能断

- `ReferenceNovelStartDialog.tsx:96` —— 「导入并分析参考小说」跳转到 `/book-analysis`；
- `KnowledgeDocumentsTab.tsx:228` → `/book-analysis?documentId=`、`232` → `/book-analysis?analysisId=`；
- `KnowledgeDocumentPicker.tsx:116` → `/book-analysis?analysisId=`；
- `useAnalysisPublishing.ts:76` → `/style-engine?profileId=&source=book-analysis`（拆书产出写法后要带着 `source` 参数跳走）；
- `useNovelContinuationSources.ts:40` 与 `ContinuationSourceSection.tsx:116` —— 手工创建与续写链路都把"拆书结果"当作数据源消费。

### 具体做法

1. 从一级导航移除（`Sidebar.tsx` 第 56 行、`mobileSiteNavigation.ts` 第 32 / 66 行）；
2. 进"创作资产"页作为一个二级 Tab；
3. 路由与 query 参数保持不变；
4. 保留 `GATED_ROUTE_PREFIXES` 里的 `/book-analysis` 条目，不因为它下沉了就把它当成主路径。

### 验收口径

从创作页「照着一本书写」→ 导入原书 → 回到创作页这条闭环一步不少；上面五处深链逐个点击仍落到正确的 Tab 且参数生效。

### 不要做的部分

不要因为"新手会忽略它"就把它删到只剩创作页入口。已经拆过书的用户需要一个能回看、能复用、能导出分析结果的地方；那是写第二本书时的真实需求。

---

## 8. C18 · 热门题材雷达下沉为灵感输入内的行内面板

**判定：只做一半 —— 先把形态收敛成"创作页内的就地展开，不再跳出"，保留 `/market-radar` 路由与 `marketBriefId` 往返契约；整页下线暂缓，先补数据。**

### 为什么这样判

当前雷达与开书之间是一次**页面往返**：创作页 → 雷达页 → 挑信号 → 生成简报 → 带着 `?marketBriefId=` 跳回创作页（`MarketRadarPage.tsx` 第 158 行的 `briefMutation`）。每一次往返都是一次离开主路径，且没有任何东西保证新手会回来。

更关键的是，雷达真正产出的价值已经在创作页里被完整消费掉了：`AutoDirectorCreatePage.tsx` 第 649–734 行，当带着 `marketBriefId` 时，创作页自己就渲染信号标签、核心优势、开书思路、核心卖点、前 30 章承诺、题材基底与推进模式。**新手真正读的东西从来不在雷达页上。**

而雷达页本身的负担不轻：三个视图 Tab（榜单 / 分析 / 收藏）、平台筛选、逐本勾选（`toggleAnalysisItem`，第 269 行）、一次必须先跑完的榜单扫描（第 341 行会出现"等待榜单获取完成"）。这是一个在开书之前要用户先完成一轮异步任务的流程。

### 关于"新手真的用吗"

**没有埋点可以回答，我不编数据。** 但可以确认的是：第 409 行写着"AI 推荐已自动勾选，你可以替换后再开书" —— 说明默认路径不需要用户做任何选择。因此把它做成行内面板时，零操作的默认值完全可以保留，下沉不会增加新手的学习成本。

### 具体做法

1. 砍掉往返：创作页「参考热门题材」（第 740 行）与「调整雷达信号」（第 667 行）不再跳转，改为就地展开面板；
2. 展开后**榜单数据可读、逐本勾选可用** —— 这两项是真实能力，不能被合并掉，但它们是"展开后才加载"的加法，不是开书前置；
3. 默认折叠、默认沿用 AI 已勾选的信号，新手不改也能继续；
4. 保留 `/market-radar` 路由、`createMarketCreativeBrief` 与 `marketBriefId` 参数，供书签与跨设备进入；
5. 失败必须可退化：沿用第 663 行已有的兜底措辞"市场简报暂时无法读取，仍可继续按你的想法开书"。

### 验收口径

存在一条不点开任何雷达就完成开书的路径；点开后面板里能读榜单、能逐本改选；旧链接带 `marketBriefId` 进入创作页仍能还原简报。

### 不要做的部分

**不要让雷达变成写书的必经门禁。** 新手完成率的最短路是"写一句话就开始"，雷达应当是加法。如果下沉之后它出现在第 1 步且不可跳过，那比保留页面更糟。

---

## 9. 执行优先级排序

排序原则：**这个改动是否作用在用户必经的那个动作上。** 越靠近"每本书、每个人、每次都会经过的那个点击"，越先做。

### A 档 · 必须先做（改动面小、几乎无回归风险、直接作用在创作主路径上）

| 顺序 | 项 | 一句话 | 为什么先做 |
| --- | --- | --- | --- |
| A1 | **C13** | 把调试按钮从主操作行挪进「项目工具」对话框 | 改一处挂载；主操作行是每本书每次都会经过的位置，多一个伪装成操作的按钮就是每次收一次过路费 |
| A2 | **C14**（主体已落地，剩余：Gauge 换词 + 重复标题 + 可视标签） | 主体替换表**已在代码中落地**，剩余四件事见第 6 节：9 处"驾驶舱"换词、删 fallback 重复标题与 compact 死分支、右侧 Gauge 收敛、整行纯图标按钮补标签 | 剩余部分仍是纯前端改动；需要注意的是"3 个挂载点"其实是同一个 `AICockpit` 组件，改一处覆盖三处，按一个文件估时 |
| A3 | **C12** | 首页卡片为唯一主引导，`/help` 去掉一级导航项但保留路由 | 双引导是新手在第一步就遇到的问题，拖到后面意味着这段时间的新手都在被分流 |
| A4 | **C9** | 只做"合并两个模型入口 + 保住就绪卡片"，不碰页面容器 | 已按架构师实测降级（见第 1 节修订）。这是唯一"不配就 0 完成率"的节点，改动约 10 行，可与 A1 并行 |

前四项的共同点：**不删任何能力，只清掉干扰**。这也是它们应当先于所有"合并"动作的理由 —— 合并要等产品口径稳定后做，否则会返工。

> 注：A 档与架构师建议的"批次 1（C8 + C15）"没有冲突，两批可并行分给不同的人（A 档全在 client 交互层，批次 1 在 server 与依赖层）。

### B 档 · 次批做（导航层级改动，需同步多处，有跨端回归面）

| 顺序 | 项 | 一句话 | 前置与注意 |
| --- | --- | --- | --- |
| B1 | **C11** | 删 `components/generator/` 10 文件，工作台与可视化全保留并拆出独立 flag | 边界已拍板（见 A1 答复）；注意 `WorldList.tsx:380, 386` 与 `NovelWorldHandbookDialog.tsx:554` 仍指向 workspace |
| B2 | **C17** | 拆书下沉到二级 Tab，路由与 query 参数不动 | 五处深链要逐个回归测试；架构师要求先于本项完成 C8 的 `BookAnalysisCharacterRagAdapter.ts:64` 降级 |

（`views` 原来的 B1「C9」已降级到 A 档。）

### C 档 · 最后做（改动面最大，对第一本完成率影响最小）

| 顺序 | 项 | 一句话 | 为什么最后 |
| --- | --- | --- | --- |
| C1 | **C10** | 资产组 9 页合并为单页 + 二级 Tab | 9 条硬链接要保、要逐个验证 `?` 参数；而第一本书的新手在这个区域里往往一无所有，对它最先投入的性价比最低 |

### D 档 · 建议不做，或只按上述限定做

| 项 | 建议 | 理由 |
| --- | --- | --- |
| C18 整页下线 | **不做**，只做第 8 节的形态收敛；服务端 1,282 行一行不动 | 没有埋点证明新手不用它；服务端被 director 主链三处调用，删它会打断灵感链 |
| C9 合并 7 个设置页 | **不做**，降级为第 1 节的两步补丁 | 架构师实测净收益为负；且它不减少任何一项设置，不解决新手的真实门槛 |
| 连同世界工作台一起下线 | **不做**，只删 `components/generator/` | workspace 是已在写书的用户回看世界的落点，且有两条深链指向它 |
| 删 `/titles` 整页 | **不做**，降为二级 Tab | `TitleLibraryPanel` 是流程外管理能力，与流程内即时取名不是一回事 |
| Debug 只藏到 URL 参数 | **不做**，改放「项目工具」 | URL 可被粘贴与分享，等于给了非目标用户一个入口 |
| 删 `/help` 页面 | **不做**，只去一级导航 | `FirstNovelJourneyStrip` 与 `QuickSetupDialog` 在用户还不认识侧边栏时就指向它 |
| 删 `/worlds` 列表页 | **不做** | 跨书复用世界观的落点 |

---

## 10. 怎么验收"对新手完成率有没有帮助"

Phase 2 结束时不看减了多少页面，看这四条能否成立：

1. **不配模型之外，没有任何前置** —— 新手从首页到"书正在自动写"之间，不需要填任何用户不知道为什么要填的表；（对应 C9 / C11 / C18）
2. **主路径上不出现非用户任务的元素** —— 写作页顶部与书卡片的第一屏内，没有调试、没有接手/恢复/排队计数、没有第二套"下一步"；（对应 C13 / C14 / C12）
3. **曾经能到达的地方现在还能到达** —— 第 2 节与第 7 节列出的 14 条深链逐条点击不失效；（对应 C10 / C17）
4. **卡住时有出口** —— 自动推进暂停时，用户能看到原因与建议动作，且这个出口没有被"简化"掉。（对应 C14 保留 `circuitBreaker` 的红线）

---

## 11. 留给架构师与工程的待确认问题

1. `featureFlags` 是否有服务端下发通道？C11 若只能本地改，需要确认新人环境默认取值。（→ 架构师）
2. C10 合并后，二级 Tab 是用 query 参数还是 hash？需要和路由策略统一，并在 `mobileSiteNavigation.ts` 里同步。（→ 工程）
3. C12 的单一数据源改造涉及把 `FirstNovelOnboarding` 接入首页视图模型，是否有性能或缓存影响？（→ 架构师）
4. C18 若要补埋点，最小可行的事件是什么？（→ 产品 + 工程）
5. `NovelProjectCard.tsx` 第 167 行那个打开 AI 驾驶舱的 Gauge 图标，隐喻是否对新手可读？本次未定，建议单独做一次可理解性验证。（→ 产品）

---

## 12. 对架构师 `04-phase2-rescoped.md` 遗留问题（A1–A5）的正式答复

架构师的实测推翻了几处估算，也纠出了我初判里的两个盲点（C9 的重量不在 views、C14 的挂载点不止一处）。以下五条是拍板结论，工程可以直接据此排期。

### A1 · C11 边界：世界工作台是否与向导一起下线？

**答：不下线 —— 读法要明确为「不再需要下线这个选项」，工作台是产品的固定组成部分，不是"本轮暂缓删除"。**

理由是它承担两件向导替代不了的事：

1. `WorldList.tsx:380, 386` 与 `NovelWorldHandbookDialog.tsx:554` 都把「打开来源世界手册」指向 `/worlds/{id}/workspace` —— 这是**已经在写书的用户**回看自己世界的落点，不是向导的一部分；
2. 第 3 节已说明，`NovelEditView.tsx:171` 的 `WorldSetupTab` 提供的是"这本书的世界"，而 workspace 提供的是"可跨书复用的世界本体"。两者不是同一个东西。

> **改判记录（本轮）。** A1 初版写的是"不下线……并把它的开关拆成独立 flag"，字面偏"暂时保留"。那是基于"这个 flag 也许被真实部署关过"的前提。**现在前提被推翻，结论同步改判为「开关退役」（team-lead 方案 d）**：
>
> - `WORLD_WIZARD_ENABLED` / `VITE_WORLD_WORKSPACE_ENABLED` 在 `.env.example`、Dockerfile、yml、scripts 中**零引用**（已核：`.env.example` 里没有任何 `WORLD_*` 行），从来不是真实部署把手；
> - 该开关的 off 状态**不是降级而是半残**：客户端照常渲染页面，服务端全部返回 `404`（`worldHttpContext.ts:17-20`），前端无法识别"这是被关了"，只能白屏；
> - 最关键的一条：**它不是成本止血阀**。`worldGenerationRoutes.ts:96` 的 `POST /generate`（模块内唯一 SSE 流式、最贵的端点）与 `:204` 的 `PUT /:id/refine` **根本没有 `requireWorldWizard`** —— 按下开关账单照烧，功能先残一半。真要控成本应在 provider / 限流层返回 429 并给出可读提示，那是另一个设施的立项，不是复用这个开关。
>
> 退役的只是"能不能关"这一动作，**29 条路由一条不删**。

### A1 附 · 同一个缺陷的最后一份活体：`requireWorldVisualization`

`worldHttpContext.ts:23-32` 的 `requireWorldVisualization` 与 wizard 守卫结构完全一致（同样返回 `404`），且 `worldVisualizationRoutes.ts:13` 现在是两层守卫叠加。batch4 摘掉 wizard 层之后它会成为该模式的唯一幸存者。

**产品判断同 A1：可视化是 workspace 内的固定能力，同样适用"开关退役"，不走"保留 flag"。** 现在一并裁决，避免 batch5 为同一道理重开。

### A1 附 · 退役时的三条执行注记

1. `client/src/vite-env.d.ts:8` 残留 `readonly VITE_WORLD_WIZARD_ENABLED?: string;` 死类型声明 —— `client/src/config/featureFlags.ts` 已改为 `worldWorkspaceEnabled`，客户端 runtime 侧已无此 flag，退役时删掉；
2. 4 条 wizard-only 孤儿端点（`/templates`、`/inspiration/analyze`、`/inspiration/analyze/stream`、`/skeleton/generate`）必须在退役**之前**先删，否则会变成永久存活却无任何 UI 的端点；
3. **`GET` / `POST` /worlds/library` 与 `POST /worlds/library/:libraryId/use` 不在此列** —— `WorldWorkspace.tsx:15-16` 依赖它们（`api/world.ts:389/400/430` 有活的调用方），别跟着一起删。

### A2 · C9 的解法：合并页面还是删设置项？

**答：都不是。改成一个两步的目录补丁（见修订后的第 1 节），从 B 档降级为 A 档里顺手做掉的小改动。**

架构师的判断是对的：合并页面不减少任何一项设置。真正对新手构成门槛的只有两件事 —— 入口重名（模型 / 模型路由）和不知道配没配好。`entries` 合并两条 + 保住已有的 `SettingsReadinessCard`，这两件事就解决了，不需要碰任何页面容器。

至于"删设置项"：本轮**不建议**。`/settings/director`、`/settings/knowledge`、`/settings/maintenance` 三项分别对应用户已经建立的配置，删掉会影响存量用户，且它们都不在第一本书的必经路径上。留到有使用数据时再议。

### A3 · C18：服务端 1,282 行保留是否可接受？

**答：完全接受，而且这本来就是唯一正确的做法。**

`marketRadarService.getBriefPromptBlock()` 被 director 主链三处调用，这条灵感链是自动导演产出"开书思路"的输入。砍掉它不是做减法，是把已经能跑的主链路打断。

我在第 8 节的边界也是同一条：**只动前端形态，不动服务端**。具体即"创作页内就地展开 + 保留 `marketBriefId` 往返契约"。

### A4 · C14 三处挂载点是否全改？文案谁出？

**答：三处全改，文案由我出 —— 已出，见第 6 节替换表，直接可以落地。**

已在 C14 段落里同步了挂载点修正。另外提醒工程：`NovelTaskDrawer` 属任务中心，按 AGENTS.md 只读规则，改文案时可删可合，但不得新增任何操作按钮。

### A5 · C15 验收依赖 `client build`

非产品问题，不介入。仅提示：若最终只能做"依赖声明层删除"，建议在 PR 描述里显式标注"未执行 build 验证"，避免后续误以为已验证。
