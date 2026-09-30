# C10 · 资产页合并 — 实测拆分 / 回滚计划

> 作者：Bob（架构师）· 本轮为**只读实测 + 计划**，不修改任何源码
> 基线：`git log --oneline -1` → `db2f13f`（注意：工作摘要 `04-phase2-rescoped.md` 的基线 `74a03b8` 已过时，仓库已前移）
> 关联输入：`docs/simplification/02-architecture-simplification-plan.md` §4.2、`04-phase2-rescoped.md` §C10、`05-phase2-product-decisions.md` §2 / §9

---

## 0. 一句话结论

工作摘要称 C10「资产页合并 ≈ 72 文件 / 16,215 行」。**该估算偏高且已过时，经实测推翻：**

- 真实「资产组」在 `Sidebar.tsx` 里是 **8 个页面路由 + 1 个对话框**，合计 **81 文件 / 19,135 行**（含 `style-engine`）。
- 若按工作摘要原口径只算它列的 7 页（不含 `style-engine`），真实值是 **63 文件 / 14,536 行**，而非 72 / 16,215。
- 偏差的 **9 文件 / 1,679 行** 完全等于已被删除的 `worlds/components/generator/`（C11 的删除目标，已于 commit `2841566` 落地）。**不是数错，是基线漂移。**
- 合并不强迫任何被 AGENTS.md 禁止的「按资产类型分发」分支表；唯一新增的「按类型切换」是 UI 渲染级的 tab→组件映射（允许）。详见 §10。

---

## 1. 测量口径

| 项 | 口径 |
|---|---|
| 行数 | 仅统计 `client/src/pages/{8 目录}` 下的 `.ts` / `.tsx`（`wc -l` 汇总，不含 `.test.*`、不含 `dist/`、不含 `api/`） |
| 文件数 | 同上扩展名 |
| 跨模块耦合 | `grep -rln` 全仓 `client/src` 统计「引用某资产路由的文件数」，并区分「资产组内自引用」与「组外外部引用」 |
| 验证原则 | 所有数字均附带 `命令 + 输出` 证据（见各节与附录），可复现 |

---

## 2. 实测数字 vs 工作摘要估算（含 grep 证据）

### 2.1 逐目录实测

**命令**
```bash
cd AI-Novel-Writing-Assistant-main
for d in worlds knowledge storyModes antiAiRules characters genres titles writingFormula; do
  echo "### $d";
  find "client/src/pages/$d" -type f \( -name "*.ts" -o -name "*.tsx" \) | wc -l;
  find "client/src/pages/$d" -type f \( -name "*.ts" -o -name "*.tsx" \) -exec wc -l {} + | tail -1;
done
```

**输出（当前树）**
```
worlds         25   6243
knowledge       7   2568
storyModes      6   1461
antiAiRules     9   1046
characters      5   1550
genres          6    872
titles          5    796
writingFormula 18   4599
```

**权威聚合（脚本复算）**
```
8 页合计（含 style-engine）：81 文件 / 19135 行
7 页小计（不含 style-engine）：63 文件 / 14536 行   (= 81-18 文件, 19135-4599 行)
```

### 2.2 与工作摘要逐一对账

| 目录 | 工作摘要 `04` 声称 | 本轮实测 | 差异 | 说明 |
|---|---:|---:|---:|---|
| `worlds` | 34 / 7,922 | **25 / 6,243** | −9 文件 / −1,679 行 | 差额 = 已删的 `components/generator/`（见 §2.3） |
| `knowledge` | 7 / 2,568 | 7 / 2,568 | 0 | 一致 ✅ |
| `storyModes` | 6 / 1,461 | 6 / 1,461 | 0 | 一致 ✅ |
| `antiAiRules` | 9 / 1,046 | 9 / 1,046 | 0 | 一致 ✅ |
| `characters` | 5 / 1,550 | 5 / 1,550 | 0 | 一致 ✅ |
| `genres` | 6 / 872 | 6 / 872 | 0 | 一致 ✅ |
| `titles` | 5 / 796 | 5 / 796 | 0 | 一致 ✅ |
| `writingFormula` | 18 / 4,599（**原未计入 7 页小计**） | 18 / 4,599 | 0 | 实测一致，但它**本就在 Sidebar 资产组里**（见 §3） |
| **7 页小计** | **72 / 16,215** | **63 / 14,536** | **−9 / −1,679** | 偏差 100% 来自 `worlds` 的 generator |
| **8 页（含 style-engine）** | 未给（原漏算） | **81 / 19,135** | — | 真实「资产组」全貌 |

> **结论：工作摘要的 72/16,215 是过时的上界估算，不是当前真实规模。真实当前规模 = 63/14,536（7 页）或 81/19,135（8 页全组）。**

### 2.3 `worlds` 偏差归因（已实证，非误数）

工作摘要把 `worlds` 算成 34/7,922，是因为它**在基线 `74a03b8` 时仍包含 `components/generator/` 与 `WorldGenerator.tsx`**（C11 的删除目标）。本轮实测 `worlds` 下已无 generator：

**命令**
```bash
find client/src/pages/worlds -type f | sort
# → 仅 25 个 .ts/.tsx + 1 个 .test.mjs（worldGraphLayout.test.mjs），无 components/generator/
grep -rln "WorldGenerator" client/src          # → 无任何输出（组件已彻底移除）
git log --oneline --all -- "client/src/pages/worlds/components/generator"
# → 2841566 refactor(worlds): remove the world wizard generator
```

差额 9 文件 / 1,679 行与 C11 实测的 generator 体量（10 文件 / 1,670 行，含 `WorldGenerator.tsx`）吻合 → **C11 的 generator 删除已落地，C10 不再与之重叠**（详见 §4.3）。

---

## 3. 资产组边界确认（Sidebar 实证，非推测）

**命令**
```bash
sed -n '59,73p' client/src/components/layout/Sidebar.tsx
```

**输出**
```tsx
{
  title: "资产",
  items: [
    { to: "/genres",         label: "题材基底库",   icon: Tags },
    { to: "/story-modes",    label: "推进模式库",   icon: Workflow },
    { to: "/titles",         label: "标题工坊",     icon: SquarePen },
    { to: "/knowledge",      label: "知识库",       icon: Database },
    { to: "/worlds",         label: "世界样本库",   icon: Globe2 },
    { to: "/style-engine",   label: "写法引擎",     icon: WandSparkles },
    { to: "/anti-ai-rules",  label: "反 AI 规则",   icon: ShieldCheck },
    { to: "/base-characters",label: "基础角色库",   icon: UsersRound },
    { to: "#visual-assets",  label: "视觉资源库",   icon: Images, action: "visual_asset_library" },
  ],
},
```

→ 资产组 = **8 个页面路由 + 1 个对话框**（`#visual-assets` 是 `action` 触发的弹层，不是页面，不在合并范围）。这与 §2 的 8 目录完全对齐。

> ⚠️ 工作摘要 `04` 把 `style-engine` 标为「原方案未计入」——**这是错的**：它在 Sidebar 资产组里明文存在。真实的「资产组全貌」必须把 `writingFormula`（18/4,599）算进去。

---

## 4. 跨模块重叠量化（含 grep 证据）

### 4.1 入站耦合：多少「组外」文件硬链进各资产路由

**命令**（区分组内自引用与组外外部引用）
```bash
for r in "base-characters" "style-engine" "anti-ai-rules" "/genres" "story-modes" "/titles" "/knowledge" "/worlds"; do
  total=$(grep -rln --include=*.tsx --include=*.ts "$r" client/src | wc -l)
  ext=$(grep -rln --include=*.tsx --include=*.ts "$r" client/src \
        | grep -vE "client/src/pages/(worlds|knowledge|storyModes|antiAiRules|characters|genres|titles|writingFormula)/" | wc -l)
  echo "$r -> total=$total external=$ext"
done
```

**输出**
```
base-characters -> total=6  external=6
style-engine    -> total=9  external=8
anti-ai-rules   -> total=7  external=5
/genres         -> total=4  external=4
story-modes     -> total=5  external=5
/titles         -> total=5  external=5
/knowledge      -> total=33 external=24   ← 主导，风险最高
/worlds         -> total=8  external=6
```

**解读与排序（外部耦合越高，折叠时深链断裂风险越大）：**
1. **`/knowledge`（24 外部文件）** — 深链普遍带 query 参数：`?documentId=`、`?analysisId=`、`?tab=settings`；来源含 `bookAnalysis`、`novels`、`settings`。折叠时这些参数必须无损透传，否则新手在「配置检索」「新建拆书」「查看来源拆书」处 404。
2. **`style-engine`（8）** — 含 `useAnalysisPublishing.ts:76` 的 `/style-engine?profileId=...&source=book-analysis`（拆书产出写法后带回跳），以及 `NovelStyleRecommendationCard` 的两处。
3. **`worlds`（6）** — 关键是 `NovelWorldHandbookDialog.tsx`（已迁至 `pages/novels/components/novelWorld/`）的 `/worlds/${id}/workspace` 深链，必须保留 `:id` 参数。
4. **`base-characters`（6）** — `CharacterCreateDialog`（现位于 `pages/novels/components/characterPanel/` 与 `pages/characters/components/`）→ `/base-characters`。
5. **其余（genres/story-modes/titles/anti-ai-rules，各 4–5）** — 耦合低，折叠最安全。

### 4.2 相邻 API 层（**本轮不动**，仅列出以界定范围）

合并只动「页面容器 + 路由 + 侧栏」。**`client/src/api/` 下的资产模块保持原位**（页面组件复用它们，不迁移）：

**命令**
```bash
for f in world knowledge storyModes antiAiRule character genre title writingFormula; do
  p=$(find client/src/api -iname "*$f*" | head -1); [ -n "$p" ] && echo "$p -> $(wc -l < "$p") 行" || echo "NO api: $f";
done
```

**输出**
```
client/src/api/novelWorldSlice.ts -> 79 行
client/src/api/knowledge.ts       -> 283 行   ← 最重，被 24 外部文件消费
client/src/api/character.ts       -> 69 行
client/src/api/genre.ts           -> 89 行
client/src/api/title.ts           -> 86 行
client/src/api/writingFormula.ts  -> 18 行
NO api: storyModes                ← 无独立 api 文件（用通用 fetch）
NO api: antiAiRule                ← 无独立 api 文件（用通用 fetch）
```

→ 相邻 API 合计 ~624 行 / 6 文件，全部**保留**。注意 `storyModes` / `antiAiRules` 没有专属 api 层，合并时不能假设存在统一客户端，需沿用其现有内联请求。

### 4.3 与 C11（world wizard）的历史重叠 —— **已解除**

工作摘要 `04` §C10 写「worlds 与 C11 重叠，必须同批或让 C11 先做」。本轮实测：**C11 的 generator 删除已于 commit `2841566` 落地**，`worlds` 当前只剩 workspace + visualization 两部分（25/6,243），与 C11 不再有任何代码交集。→ **C10 的 C11 前置依赖已自然消解，可独立排期。**

### 4.4 自动化兜底现状

**命令**
```bash
find client/src/pages/{worlds,knowledge,storyModes,antiAiRules,characters,genres,titles,writingFormula} \
     -name "*.test.ts" -o -name "*.test.tsx"
# → NONE（仅 worlds/visualization/worldGraphLayout.test.mjs 一个 .mjs，非页面单测）
```

→ 8 个目录 **0 个页面级 `.test.ts(x)`**。回归无任何自动兜底，必须靠 §11 的手工验收 + 加法式回滚策略抵消风险。

---

## 5. 必须保留的可直达 URL / 深链清单（实测存活情况）

工作摘要 `05` §2 列了 9 条硬链。本轮复核其**当前存活状态**（组件有迁移，URL 契约仍在）：

| # | 深链（URL） | 当前源文件（已迁移） | 状态 |
|---|---|---|---|
| 1 | `/base-characters` | `pages/novels/components/characterPanel/CharacterCreateDialog.tsx` | ✅ 存活（文件已从 `novels/components/` 迁至 `characterPanel/`） |
| 2 | `/style-engine` (+`?mode=imitate`) | `pages/novels/components/NovelStyleRecommendationCard.tsx:82,85` | ✅ 存活 |
| 3 | `/anti-ai-rules` | `pages/writingFormula/components/WritingFormulaRulesPanel.tsx:37` | ✅ 存活 |
| 4 | `/genres` | `WorldGenerator.tsx:345` | 🔴 **已失效** — 源文件随 C11 删除，此条深链已不存在 |
| 5 | `/worlds/:id/workspace` | `pages/novels/components/novelWorld/NovelWorldHandbookDialog.tsx:554` | ✅ 存活（文件已迁至 `novelWorld/`） |
| 6 | `/book-analysis?documentId=` / `?analysisId=` | `pages/knowledge/components/KnowledgeDocumentsTab.tsx:228,232` | ✅ 存活（注意：这是 knowledge→bookAnalysis 的**出站**链） |
| 7 | `/book-analysis?analysisId=` | `components/knowledge/KnowledgeDocumentPicker.tsx:116`（已从 `pages/knowledge/components/` 迁至 `components/knowledge/`） | ✅ 存活 |
| 8 | `/style-engine?profileId=&source=book-analysis` | `pages/bookAnalysis/hooks/actions/useAnalysisPublishing.ts:76` | ✅ 存活 |
| 9 | `/knowledge?tab=settings` | `pages/settings/views/KnowledgeSettingsPage.tsx:25` | ✅ 存活 |

> 结论：9 条里 8 条仍存活，仅第 4 条（`WorldGenerator→/genres`）随 C11 删除而消失——**已在本文 §2.3 / §4.3 说明**。其余 8 条 URL 契约在合并后必须保持「点击不 404、query 参数无损」。

---

## 6. 合并策略：**加法式枢纽（最大化可回滚）**

不采用工作摘要担心的「重写 7 个页面容器层」。改为：

1. **新增**一个 `AssetHubPage`（资产枢纽）作为单页 + 二级 tab 壳；
2. **原样复用** 8 个既有页面组件（直接 `import` 现有 `GenreManagementPage` 等），**不移动、不删除、不重写**它们；
3. **保留全部 8 条旧路由**（`/genres` … `/base-characters`）继续渲染原组件 —— 书签 / 深链 / 外部引用**零中断**；
4. 侧栏只把 9 项折叠为 1 项「创作资产」→ `/assets`；
5. 把「改写旧路由为重定向」这一**不可逆**步骤**延后到 Phase 4**（见 §7 B5）。

→ 此法把回归面从「16k 行重写」降到「仅一个新增壳 + 导航层」，且每个批次独立 `git revert` 即可回滚。

---

## 7. 可回滚子批次（每个独立 commit + 回滚说明）

> 约定：每批一个 commit；回滚 = `git revert <sha>`。所有批次均**不改任何既有页面组件**，仅新增 / 改导航 / 删孤儿。

### B1 — 新增资产枢纽页（加法，零破坏）· 优先级 P0
- 新增 `client/src/pages/assets/AssetHubPage.tsx`（tab 壳，按 `?tab=` query 渲染对应既有组件）
- 新增 `client/src/pages/assets/assetHub.config.ts`（tab 列表：genres / story-modes / titles / knowledge / worlds / style-engine / anti-ai-rules / base-characters）
- `router/index.tsx` **新增**路由 `path: "assets" → <AssetHubPage/>`（不碰 8 条旧路由）
- **回滚**：`git revert`；仅移除新增文件 + `/assets` 路由。8 个旧页面与旧路由完全不动 → 零回归。

### B2 — 侧栏折叠（仅导航层）· 优先级 P0
- `Sidebar.tsx` 资产组 9 项 → 1 项 `{ to: "/assets", label: "创作资产" }`
- 同步 `client/src/components/layout/mobile/mobileSiteNavigation.ts`（实测其亦引用这些路由）
- 8 条旧路由**保留**（书签 / 深链仍可达），仅从一级导航移除
- **回滚**：`git revert`；恢复 9 项侧栏与移动端导航。

### B3 — 深链与旧 URL 验收（验证 commit，不删代码）· 优先级 P0
- 逐一点击 §5 的 8 条存活深链 + 8 条旧 URL + 各自 query 参数，确认 404 = 0、参数透传正确；
- 若某页在 hub 的 tab 框内布局异常（如页面内部用 `useLocation`/`useParams` 假设自己是顶层路由），**只修 hub 的 tab→component 转发**，不碰旧页面；
- **回滚**：无代码改动，或 `git revert` 修复补丁。

### B4 — 删除孤儿 `NovelTitleWorkshop.tsx` · 优先级 P2
- 实测（命令 + 输出）：
  ```bash
  find client/src -name "NovelTitleWorkshop.tsx"
  # client/src/pages/novels/components/titleWorkshop/NovelTitleWorkshop.tsx
  grep -rln "NovelTitleWorkshop" client/src
  # 仅上方自身一行 → 全仓唯一引用是自己
  ```
  → 确属孤儿，删除不影响任何界面（真正被用的是 `NovelCreateTitleQuickFill`）。
- **回滚**：`git revert` 恢复文件。

### B5（延后 · 不可逆 · 归 Phase 4）— 将 8 条旧路由改为 hub 重定向
- 此步把 `/genres` 等旧 URL 形态改为 `/assets?tab=genres` 重定向，**不可逆**（改后旧 URL 行为变化，回滚需同时回退 B2/B3/B5）。
- 前置：B1–B3 验收通过、且确认无外部系统硬编码旧 URL（如邮件模板、文档站）。
- **不在本轮执行。**

---

## 8. 风险清单（尤其新手）

| # | 风险 | 触发条件 | 新手影响 | 缓解（来自本策略） |
|---|---|---|---|---|
| R1 | 深链 404 | 折叠时某条 §5 链接的 query 参数（`?tab=settings` / `?documentId=` / `:id`）未透传 | 新手在「配置检索」「查看来源拆书」「打开来源世界手册」处卡死，第一本书完成率直接归零 | **保留 8 条旧路由**（B1/B2 不动旧路由）+ B3 逐条验收 |
| R2 | `knowledge` 高耦合炸裂 | `/knowledge` 被 24 个外部文件引用，参数最多 | 同上，且影响面最大 | 最后处理 knowledge（B3 重点验 §5 #6/#7/#9）；优先用加法式而非重写 |
| R3 | 页面内部路由假设被破坏 | 某页面用 `useLocation`/`useParams` 假定自己是顶层路由，被套进 hub tab 后路径错位 | 页面渲染空白 / 跳转错乱 | B3 实测；只修 hub 转发层，不动旧组件 |
| R4 | 零自动化兜底 | 8 目录 0 个 `.test.ts(x)` | 任何回归只能靠人眼，新手问题上线后才发现 | 加法式 + 每批可 `git revert`，把爆炸半径锁在新增壳 |
| R5 | 误删不该删的 | `character.ts`/`genre.ts` 等 api 层被当成「页面一部分」顺手迁 | 跨模块引用断裂 | §4.2 明确 api/ 保留不动 |
| R6 | 合并变成「重写」 | 工程师按字面理解「合并为单页」而重写容器 | 16k 行回归面、旧行为丢失 | §6 强制「复用不重写」 |
| R7 | 不可逆重定向过早 | 在 B3 验收前执行 B5 | 旧 URL 失效且难回退 | B5 明确延后到 Phase 4 |

---

## 9. 新手影响评估

**正面（按 AGENTS.md「低认知负荷优先」）：**
- 侧栏资产区从 **9 项 → 1 项「创作资产」**，新手少做 8 次无关决策；
- 第一本书的新手在该区通常一无所有（PM `05` §2 结论），层级收敛对他完成率影响最小、收益最干净；
- 加法式策略下，**所有既有直达 URL 与深链保持可达**，新手在创作流内被就地提供的入口（题材 / 模式 / 标题 / 知识库 / 世界 / 写法 / 反 AI 规则 / 基础角色）一个都不会断。

**负面（必须守住的底线）：**
- 若 R1/R2 发生（深链断裂），新手会**卡在创作中途**（如点「配置检索」进知识库、`NovelWorldHandbookDialog` 打开来源世界手册），比「导航多了几项」严重得多——这是本项对新手唯一的真风险；
- 对策：本计划用「保留旧路由 + 加法式枢纽 + 每批可回滚」把该风险压到接近 0，**前提是不提前做 B5（旧路由重定向）**。

**净判断**：在 §6/§7 策略下，C10 对新手是**纯正向**（更干净导航、零断链）；风险完全来自「是否提前破坏旧 URL」，而本计划已将其隔离为可延后的 B5。

---

## 10. 明确声明：合并不引入被禁分支表

**结论：C10 合并不强迫任何 AGENTS.md 禁止的「按资产类型分发」分支表。**

### 10.1 唯一新增的「按类型切换」是什么
枢纽页需要一个 `tab → 组件` 的映射来决定渲染哪个既有页面。这是 **UI 渲染级** 的「按资产类型切换」，**属于 AGENTS.md 允许的范畴**（规则禁止的是「AI 意图决策路径上的固定关键字 / 正则 / 硬编码分支表」，并未禁止 UI 渲染按类型分支）。

### 10.2 实测：8 个资产页内无 AI 决策分支表
**命令**
```bash
grep -rlnE "assetType|byAssetType|assetDispatch" \
  client/src/pages/{worlds,knowledge,storyModes,antiAiRules,characters,genres,titles,writingFormula}
# → NONE FOUND
grep -rnE "switch\s*\(.*(assetType|asset|zone|tab|type)" \
  client/src/pages/{worlds,knowledge,storyModes,antiAiRules,characters,genres,titles,writingFormula}
# → 无匹配
```
唯一命中的 `antiAiRules:` 是 React **prop 类型注解**（`antiAiRules: AntiAiRule[]`，见 `WritingFormulaAdvancedWorkspace.tsx:21` 等 4 处），**不是分支表**。

### 10.3 给工程师的硬约束（写进验收）
- 枢纽页的 tab 配置**必须是纯 UI 渲染映射**（组件引用数组），例如：
  ```ts
  const ASSET_TABS = [
    { key: "genres", label: "题材基底库", Component: GenreManagementPage },
    // ...
  ] as const;
  ```
- **禁止**出现以下任何形式的「资产类型 → X」硬编码映射（这些才是被禁的「路由 / 分发 / AI 决策分支表」）：
  - `资产类型 → 路由处理器`（如 `handlers[type] = ...`）；
  - `资产类型 → 提示词策略 / AI 分支`（如按 assetType 选择 prompt 或模型）；
  - 用关键字 / 正则匹配判断「这是什么资产类型」再分发。
- 当前 8 个资产页均**不喂任何 AI 决策**，故合并本身不会把任何 AI 路径改成「按资产类型分支」。若未来某页新增 AI 分发，那是该页自身职责，与本次合并无关。

---

## 11. 验收口径

1. `tsc --noEmit`（client）通过；
2. 侧栏「创作资产」点击进入枢纽，8 个 tab 均可直达；
3. §5 的 8 条存活深链 + 8 条旧 URL（含 `?tab=settings` / `?documentId=` / `:id` 等参数）逐一点击 **404 = 0、参数无损**；
4. 视觉资源库对话框（`#visual-assets` / `action: visual_asset_library`）仍可从侧栏触发；
5. `git log` 显示 B1–B4 各自独立 commit，可单独 `git revert`；
6. **未执行 B5**（旧路由重定向延后）；
7. 全仓 `grep -rnE "assetType|byAssetType|assetDispatch"` 仍为 NONE（§10.2 不退化）。

---

## 附录 · 完整命令与输出复现

<details>

**A. 各目录文件数 / 行数（§2.1）**
```bash
for d in worlds knowledge storyModes antiAiRules characters genres titles writingFormula; do
  echo "### $d";
  find "client/src/pages/$d" -type f \( -name "*.ts" -o -name "*.tsx" \) | wc -l;
  find "client/src/pages/$d" -type f \( -name "*.ts" -o -name "*.tsx" \) -exec wc -l {} + | tail -1;
done
# worlds 25/6243  knowledge 7/2568  storyModes 6/1461  antiAiRules 9/1046
# characters 5/1550  genres 6/872  titles 5/796  writingFormula 18/4599
```

**B. 资产组 Sidebar 边界（§3）**
```bash
sed -n '59,73p' client/src/components/layout/Sidebar.tsx
# 8 个 to: 路由 + 1 个 #visual-assets 对话框
```

**C. 外部耦合（§4.1）**
```bash
for r in "base-characters" "style-engine" "anti-ai-rules" "/genres" "story-modes" "/titles" "/knowledge" "/worlds"; do
  total=$(grep -rln --include=*.tsx --include=*.ts "$r" client/src | wc -l)
  ext=$(grep -rln --include=*.tsx --include=*.ts "$r" client/src | grep -vE "client/src/pages/(worlds|knowledge|storyModes|antiAiRules|characters|genres|titles|writingFormula)/" | wc -l)
  echo "$r -> total=$total external=$ext"
done
# /knowledge total=33 external=24 ; style-engine 9/8 ; worlds 8/6 ; base-characters 6/6
# anti-ai-rules 7/5 ; story-modes 5/5 ; /titles 5/5 ; /genres 4/4
```

**D. 相邻 api 层（§4.2）**
```bash
for f in world knowledge storyModes antiAiRule character genre title writingFormula; do
  p=$(find client/src/api -iname "*$f*" | head -1); [ -n "$p" ] && echo "$p -> $(wc -l < "$p")" || echo "NO api: $f";
done
# novelWorldSlice 79 / knowledge 283 / character 69 / genre 89 / title 86 / writingFormula 18 ; storyModes/antiAiRule 无
```

**E. 测试文件（§4.4）**
```bash
find client/src/pages/{worlds,knowledge,storyModes,antiAiRules,characters,genres,titles,writingFormula} -name "*.test.ts" -o -name "*.test.tsx"
# NONE
```

**F. 孤儿 NovelTitleWorkshop（§7 B4）**
```bash
find client/src -name "NovelTitleWorkshop.tsx"
# client/src/pages/novels/components/titleWorkshop/NovelTitleWorkshop.tsx
grep -rln "NovelTitleWorkshop" client/src
# 仅上方自身 → 孤儿
```

**G. 被禁分支表检查（§10.2）**
```bash
grep -rlnE "assetType|byAssetType|assetDispatch" client/src/pages/{worlds,knowledge,storyModes,antiAiRules,characters,genres,titles,writingFormula}
# NONE FOUND
```

**H. git 基线（§0 / §2.3）**
```bash
git log --oneline -1                 # db2f13f
git log --oneline --all -- "client/src/pages/worlds/components/generator"
# 2841566 refactor(worlds): remove the world wizard generator
```

</details>
