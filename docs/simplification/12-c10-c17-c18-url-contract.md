# C10 / C17 / C18 统一「侧栏收敛 + 可直达 URL」契约文档

> 作者：team-lead（软件简化专家团）
> 关联输入：`07-c10-split-plan.md`（C10 加法式枢纽）、`05-phase2-product-decisions.md` §7（C17）、§8（C18）、`04-phase2-rescoped.md` §C10/C17/C18
> 性质：**只读实测 + 契约草案**，本文件不含任何代码改动；是 Batch 3（导航结构重构）开工前的签字基线
> 实测基线：`main` @ `433578f`（CI 绿）；本文件所有引用行号均来自当前工作树，已用 grep 复测

---

## 0. 一句话契约

C10（资产组 8 页合并）、C17（`/book-analysis` 一级下沉）、C18（`/market-radar` 降级）**共用同一套原则**：

> **Phase 2（Batch 3）只动「导航入口」，不动「路由与 URL 形态」。**
> 侧栏 / 移动端的一级项被移除后，被移除的页面**仍以原 URL 直接可达**（书签、深链、外部引用零中断）；新增 `/assets` 枢纽只是**额外**的入口层，不替换、不重定向、不改写既有路由。

这与 `07-c10-split-plan.md` §6「加法式枢纽」完全一致，也是 `05` §7.3「路由与 query 参数保持不变」、§8.4「保留 `/market-radar` 路由」的落点。

**唯一例外（C18 形态收敛）**：`AutoDirectorCreatePage.tsx` 内两处 `<Link to="/market-radar">`（`:667`、`:740`）改成「就地展开面板」，这是**两枚具体应用内链的行为改写**，不是删路由——`/market-radar` 路由本身仍为书签 / 跨设备入口保留（详见 §6）。

---

## 1. 现行导航状态（实测，作为对照基线）

`client/src/components/layout/Sidebar.tsx:46-78`：

| 组 | 一级项（实测） | 数量 |
|---|---|---:|
| 创作 | `/`(首页)、`/market-radar`(热门题材雷达)、`/novels`(小说列表)、`/creative-hub`(创作中枢)、`/book-analysis`(拆书) | 5 |
| 资产 | `/genres`、`/story-modes`、`/titles`、`/knowledge`、`/worlds`、`/style-engine`、`/anti-ai-rules`、`/base-characters` + `#visual-assets`(对话框) | 8 路由 + 1 弹层 |
| 系统 | `/tasks`(运行记录)、`/settings`(系统设置) | 2 |

`client/src/router/index.tsx:57`（`book-analysis`）、`:58`（`market-radar`）、`:60-79`（8 条资产路由 + `worlds/:id/workspace` 受 `featureFlags.worldWorkspaceEnabled` 门闸）——**全部保留，本批不碰**。

移动端 `client/src/components/layout/mobile/mobileSiteNavigation.ts`：
- `MOBILE_ROUTE_PATTERNS` 含 `book-analysis`(`:31`)、`market-radar`(`:32`)，均归 `group: "creation"`；
- `moreNavGroups` 的「创作辅助」组含 `book-analysis`(`:63`)、`market-radar`(`:64`)、`chat-legacy`(`:65`)；「资产库」组含 7 条资产路由(`:71-77`)；「世界与系统」组含 `worlds`(`:83`)、`settings`(`:84`)。

---

## 2. 目标侧栏形状（桌面 + 移动）

### 2.1 桌面侧栏（目标）

| 组 | 一级项 | 数量 | 变化 |
|---|---|---:|---|
| 创作 | `/`(首页)、`/novels`(小说列表)、`/creative-hub`(创作中枢) | 3 | 移除 `/market-radar`、`/book-analysis` |
| 资产 | `/assets`(创作资产，枢纽) + `#visual-assets`(对话框) | 1 路由 + 1 弹层 | 8 路由 → 1 枢纽 |
| 系统 | `/tasks`(运行记录)、`/settings`(系统设置) | 2 | 不变 |

- `/assets` 枢纽内 tab（见 §4）：`genres / story-modes / titles / knowledge / worlds / style-engine / anti-ai-rules / base-characters / book-analysis`（共 9 个）。
- `#visual-assets` 对话框**保持现状**（本就是弹层，非页面，不在合并范围）。
- 异常徽标逻辑保留：`Sidebar.tsx:117-148` 对 `/tasks`、`/knowledge` 的失败计数徽标**继续生效**（`/knowledge` 仍是可达路由）。

### 2.2 移动端（目标）

- `primaryNavItems`（`:51-57`）：**不变**（home / novels / creation / tasks / more）。
- `moreNavGroups`：
  - **「创作辅助」组**：移除 `book-analysis`、`market-radar`；`chat-legacy` 超出本契约范围，保留。
  - **「资产库」组**：7 条独立项（`:71-77`）**替换为单一** `{ key:"assets", label:"创作资产", to:"/assets" }`。
  - **「世界与系统」组**：`worlds`(`:83`) 现改由 `/assets` 枢纽承载，移出本组；仅留 `settings`(`:84`)。
  - 若「世界与系统」组仅剩 `settings`，可并入更上层的「更多」聚合，或保留为单一项组——**以不引入新 UI 控件为前提**，具体由工程师在 B2 落地时就近处理。
- `MOBILE_ROUTE_PATTERNS`：保留 `book-analysis`(`:31`)、`market-radar`(`:32`) 两条 pattern（用于深链直达时的页面标题与高亮态），**仅从 nav items 移除，不作为导航项列出**。

---

## 3. 可直达 URL / 深链清单（合并后必须保持 404=0、参数无损）

> 核心保证：所有被移除的**一级导航项，其底层路由原样保留**。因此下列深链无论来自站内 `<Link>`、书签、外部文档还是服务端下发，均直接落到原路由，**不经 `/assets` 中转**。

### 3.1 C10 资产组 8 路由（来自 `07` §5，已剔除失效项）

| # | 深链（URL） | 来源（实测文件:行） | 状态 |
|---|---|---|---|
| 1 | `/base-characters` | `CharacterCreateDialog.tsx`（现 `pages/novels/components/characterPanel/`，原 `07` §5 #1） | ✅ 存活 |
| 2 | `/style-engine`（`?mode=imitate`） | `NovelStyleRecommendationCard.tsx:82,85` | ✅ 存活 |
| 3 | `/anti-ai-rules` | `WritingFormulaRulesPanel.tsx:37` | ✅ 存活 |
| 4 | `/genres` | `WorldGenerator.tsx:345` | 🔴 已随 C11 删除失效（`07` §5 #4 已标注）；`/genres` 路由本身仍存活，仅无此入链 |
| 5 | `/worlds/:id/workspace` | `NovelWorldHandbookDialog.tsx:554` | ✅ 存活（`:id` 必须透传） |
| 6 | `/knowledge?documentId=` / `?analysisId=` | `KnowledgeDocumentsTab.tsx:228,232`（knowledge → bookAnalysis 出站） | ✅ 存活 |
| 7 | `/book-analysis?analysisId=` | `KnowledgeDocumentPicker.tsx:116` | ✅ 存活 |
| 8 | `/style-engine?profileId=&source=book-analysis` | `useAnalysisPublishing.ts:76`（bookAnalysis → style-engine） | ✅ 存活 |
| 9 | `/knowledge?tab=settings` | `KnowledgeSettingsPage.tsx:25` | ✅ 存活 |

→ **8 条存活深链必保**（#4 已失效，不计）。

### 3.2 C17 拆书（`/book-analysis`）

入站（必须可直达）：
- `ReferenceNovelStartDialog.tsx:96` → `/book-analysis`（「导入并分析参考小说」）
- `KnowledgeDocumentsTab.tsx:228` → `/book-analysis?documentId=`、`:232` → `/book-analysis?analysisId=`
- `KnowledgeDocumentPicker.tsx:116` → `/book-analysis?analysisId=`

出站（同上表 #8）：`useAnalysisPublishing.ts:76` → `/style-engine?profileId=&source=book-analysis`

数据消费（非导航、但证明能力不可删）：`useNovelContinuationSources.ts:40`、`ContinuationSourceSection.tsx:116` 把「拆书结果」当数据源。

约束：
- `router/index.tsx:57` 路由保留；`creationSetupState.ts` 中 `GATED_ROUTE_PREFIXES` 的 `/book-analysis` 条目**保留**（下沉≠升为优先级）。
- `BookAnalysisSidebar.tsx:101` 用 `pathname + search` 构造内部跳转，证明页面内部依赖完整 `search`——§5 的参数透传规则对其生效。

### 3.3 C18 热门题材雷达（`/market-radar`）

- `router/index.tsx:58` 路由保留；服务端 `MarketRadarService`（742 行）属 director R 线依赖，**一行不动**（`04` §C18、`05` §8 / A3 已拍板）。
- 应用内两处链接改「就地展开」（`05` §8.2）：`AutoDirectorCreatePage.tsx:667`（调整雷达信号）、`:740`（参考热门题材）——**行为改写，非删路由**。
- `?marketBriefId=` 往返契约保留：`MarketRadarPage.tsx:158`(`briefMutation`) ↔ `AutoDirectorCreatePage` 读 `?marketBriefId=` 还原简报。无论走「整页 `/market-radar`」还是「创作页内联面板」，`marketBriefId` 必须可回填。
- 失败可退化：沿用 `AutoDirectorCreatePage.tsx:663` 兜底措辞「市场简报暂时无法读取，仍可继续按你的想法开书」（`05` §8.6）。

---

## 4. `/assets` 枢纽机制规范（C10 + C17 共用）

> 严格沿用 `07-c10-split-plan.md` §6 / §7（加法式，B1–B4 各自独立 commit 可 `git revert`；B5 重定向延后到 Phase 4）。

### 4.1 新增文件（仅新增，不重写既有页面）
- `client/src/pages/assets/AssetHubPage.tsx`：tab 壳，按 `?tab=` 渲染对应**既有页面组件**（直接 `import` `GenreManagementPage` 等），不移动 / 不删除 / 不重写它们。
- `client/src/pages/assets/assetHub.config.ts`：`ASSET_TABS` 纯 UI 渲染映射数组（见 §5 硬约束）。
- `router/index.tsx` **新增** `{ path: "assets", element: <AssetHubPage /> }`（不碰 8 条旧路由 + `/book-analysis`）。

### 4.2 tab 列表（9 个）
```
genres / story-modes / titles / knowledge / worlds / style-engine / anti-ai-rules / base-characters / book-analysis
```
`book-analysis` 作为第 9 个 tab 落进枢纽（`05` §7.2「进'创作资产'页作为一个二级 Tab」）。

### 4.3 深链 → 枢纽的两条独立路径（关键）
- **路径 A（站内深链 / 书签）**：直接命中原路由（如 `/book-analysis?analysisId=xxx`）。路由未变，页面原样渲染 → **零中断**。
- **路径 B（从侧栏「创作资产」进入）**：命中 `/assets?tab=book-analysis`，枢纽渲染 `BookAnalysisPage` 组件。
- 两路径**互不等价但共存**：路径 A 是契约保底，路径 B 是新入口。本批**不做**「旧路由 → `/assets?tab=` 重定向」（那是 B5，Phase 4 才议）。

### 4.4 R3 风险（页面误以为自己是顶层路由）的化解
枢纽直接渲染既有页面组件（路径 B），若某页用 `useLocation`/`useParams` 假定顶层路由，在 tab 壳内路径会错位。化解：
- B3 逐 tab 实测；
- 只在**枢纽转发层**修 `location`/`search` 透传，绝不改旧页面组件；
- 若某页在壳内确有问题且短期难修，回退为该 tab 用 `<Link>` 跳原路由（路径 A 形态），不动页面。

---

## 5. Query 参数无损透传规则（硬约束）

| 路由 / 枢纽 | 必保参数 | 说明 |
|---|---|---|
| `/book-analysis` | `?documentId=`、`?analysisId=`，及页面内部 `search`（`BookAnalysisSidebar.tsx:101`） | 入站深链带参；枢纽渲染时须把 `search` 原样喂给组件 |
| `/knowledge` | `?tab=`（尤其 `?tab=settings`） | 来自 `KnowledgeSettingsPage.tsx:25`；`/knowledge` 外部耦合最高（24 文件，`07` §4.1） |
| `/style-engine` | `?mode=imitate`、`?profileId=`、`?source=book-analysis` | 来自 `NovelStyleRecommendationCard.tsx`、`useAnalysisPublishing.ts:76` |
| `/worlds/:id/workspace` | `:id` 路径参数 | 来自 `NovelWorldHandbookDialog.tsx:554` |
| `/market-radar` | `?marketBriefId=` | 往返契约；内联面板与整页两条路径都必须能回填 |
| `/assets` 枢纽 | `?tab=<key>` | 选 active tab；**与底层路由参数正交**，互不覆盖 |

**总原则**：枢纽转发层只「读 `?tab` 决定渲染谁」+「把剩余 `search` 透传给被渲染组件」，绝不吞掉、改写、重排任何业务参数。

---

## 6. C18 形态收敛的特殊处理（与枢纽模式不同，单列）

- C18 **不进** `/assets` 枢纽 tab（与 `05` §8 一致：仅做形态收敛，整页下线暂缓）。
- 创作页两处链接（`:667`、`:740`）从「跳 `/market-radar`」改为「就地展开雷达面板」：
  - 展开后榜单数据可读、逐本勾选可用（`MarketRadarPage.tsx:269 toggleAnalysisItem` 等能力内联复用，不重写）；
  - 默认折叠、默认沿用 AI 已勾选信号（`MarketRadarPage.tsx:409`）；
  - 保留 `createMarketCreativeBrief` + `marketBriefId` 往返（`05` §8.4）。
- `/market-radar` 路由与 ` MarketRadarPage` 组件**整页仍保留**（书签 / 跨设备 / 兜底进入），只是不再是一级导航项。

---

## 7. 风险清单（合并 `07` R1–R7 + C17/C18 新增）

| # | 风险 | 触发 | 新手影响 | 化解（本契约） |
|---|---|---|---|---|
| R1 | 深链 404 | 折叠时某参数未透传 | 新手在「配置检索 / 查看来源拆书 / 打开来源世界手册」卡死 | **保留全部原路由** + §3 清单逐条验收 |
| R2 | knowledge 高耦合炸裂 | `/knowledge` 24 外部文件、参数最多 | 面最大 | 最后验 knowledge（§3 #6/#7/#9）；加法式非重写 |
| R3 | 页面内部路由假设被破坏 | 页面用 `useLocation/useParams` 假定顶层 | 渲染空白 / 跳转错乱 | §4.4：只修枢纽转发层，不碰旧组件 |
| R4 | 零自动化兜底 | 8 目录 0 个 `.test.ts(x)` | 回归只能人眼 | 加法式 + 每批可 `git revert` |
| R5 | 误删 api 层 | `character.ts`/`genre.ts` 等被当页面一部分顺手迁 | 跨模块断裂 | `client/src/api/` 明确保留不动（`07` §4.2） |
| R6 | 合并变重写 | 工程师字面理解「合并」而重写容器 | 16k 行回归 | §4 强制「复用不重写」 |
| R7 | 不可逆重定向过早 | B3 验收前做 B5 | 旧 URL 失效难回退 | B5 明确延后到 Phase 4 |
| R8 | C17 GATED 误删 | 把 `/book-analysis` 当主路径处理 | 未配环境新手进不去 | `GATED_ROUTE_PREFIXES` 条目保留（`05` §7.4） |
| R9 | C18 marketBriefId 丢失 | 内联面板改写时未回填 | 带简报的开书链路断 | §3.3 / §6：`marketBriefId` 往返契约保留；失败可退化 |

---

## 8. 验收口径（Batch 3 完工判据）

1. `tsc --noEmit`（client）通过；
2. 侧栏收敛：创作 3 项、资产 1 项（`/assets`）+ 视觉资源库弹层、系统 2 项；`/market-radar`、`/book-analysis` 不再是一级项；
3. `/assets` 枢纽 9 个 tab 均可直达；
4. §3 全部存活深链（C10 的 8 条 + C17 的 5 处入/出站 + C18 的 `?marketBriefId=` 往返）逐一点击 **404 = 0、参数无损**；
5. `/knowledge` 异常徽标仍由 `Sidebar.tsx` 渲染（`/knowledge` 仍是可达路由）；
6. 移动端同步：创作辅助组无 `book-analysis`/`market-radar`；资产库折叠为单一 `/assets`；
7. `git log` 显示各子批次独立 commit，可单独 `git revert`；**未执行 B5**（旧路由重定向延后）；
8. 全仓 `grep -rnE "assetType|byAssetType|assetDispatch"` 仍为 NONE（§5 硬约束不退化）；
9. 服务端零改动：`MarketRadarService`(742)、`services/world/`(7,248)、`knowledge` api(283) 原样保留；
10. C18 存在「不点开任何雷达就完成开书」的路径；点开后面板内能读榜单、能逐本改选；旧 `?marketBriefId=` 链接进入创作页仍能还原简报。

---

## 9. 待确认 / 开放项（开工前需拍板）

| # | 问题 | 本契约建议 | 责任人 |
|---|---|---|---|
| Q1 | 枢纽 tab 用 query 还是 hash？ | **query `?tab=`**（与既有 `/knowledge?tab=settings` 约定一致，`07` §10 已隐含） | 工程 |
| Q2 | market-radar 是否也进枢纽 tab？ | **否**，严格按 `05` §8 仅内联；路由保留 | 已拍板（PM） |
| Q3 | C17 前置 C8（RAG 降级）是否满足？ | 按既有记录 C8 已合并（`04` §C17 前置应已满足）；**实施前复核 `BookAnalysisCharacterRagAdapter.ts:64` 是否已 try/catch 包裹** | 工程 |
| Q4 | 移动端「世界与系统」组在移出 `worlds` 后如何呈现？ | 仅剩 `settings` 时可并入「更多」聚合，不新增控件 | 工程（B2 就近处理） |
| Q5 | `chat-legacy` 在「创作辅助」组仅剩它一项时是否保留？ | 超出本契约范围，保留现状 | 不处理 |

---

## 10. 子批次拆分（可回滚，沿用 `07` §7）

| 子批 | 内容 | 回滚 |
|---|---|---|
| **B1** | 新增 `AssetHubPage` + `assetHub.config.ts` + `router` 增 `/assets`（不碰旧路由） | `git revert`：仅删新增文件 + `/assets` 路由 |
| **B2** | 侧栏 8 路由 → 1（`/assets`）；同步移动端 `moreNavGroups` 与移除一级 `book-analysis`/`market-radar` | `git revert`：恢复侧栏与移动端 |
| **B3** | 深链与旧 URL 验收（验证 commit，不删代码）；发现 R3 问题只修枢纽转发层 | 无代码改动或 `git revert` 补丁 |
| **B4** | 删除孤儿 `NovelTitleWorkshop.tsx`（C10 唯一可整删文件，`07` §7 B4 已实测） | `git revert` 恢复 |
| **B5（延后 · Phase 4）** | 8 条旧路由 + `/book-analysis` → `/assets?tab=` 重定向（不可逆） | 不在本轮 |

> C17 的「下沉」与 C10 在 B1/B2 同批完成（book-analysis 作为第 9 个 tab）。C18 的形态收敛（§6）独立成补丁，与 B1/B2 并行无冲突（C18 只改 `AutoDirectorCreatePage` 两处链接 + 新增内联面板，不改路由表）。

---

## 11. 引用索引

- `07-c10-split-plan.md` — C10 加法式枢纽、B1–B5、8 存活深链、R1–R7、§10 禁分支表
- `05-phase2-product-decisions.md` — §7 C17 下沉判定、§8 C18 形态收敛、§9 执行优先级（C10=C1 最后、C17=B2）、§11 开放项
- `04-phase2-rescoped.md` — §C10/C17/C18 实测规模与风险、Batch 3 共用 URL 契约前置
- 实测文件锚点：`Sidebar.tsx:46-78`、`router/index.tsx:57-79`、`mobileSiteNavigation.ts:31-86`、`KnowledgeDocumentsTab.tsx:228,232`、`KnowledgeDocumentPicker.tsx:116`、`useAnalysisPublishing.ts:76`、`AutoDirectorCreatePage.tsx:663,667,740`、`NovelWorldHandbookDialog.tsx:554`、`BookAnalysisSidebar.tsx:101`
</content>
</invoke>
