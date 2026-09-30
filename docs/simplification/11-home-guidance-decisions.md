# 11 · 首页引导简化决策文档（Home Guidance Simplification Decisions）

> 类型：产品决策记录（仅记录，不改动代码）
> 角色：software-product-manager
> 关联：本文件落实 `10-docs-terminology-inventory.md`（裁决 5）与 `03-followup-removal-assessment.md` 中已确认的方向，供工程后续执行。
> 目标用户：完全不会写小说的写作新手。所有 UI 文案须从**用户视角**出发（用户能做什么 / 系统帮用户做什么 / 下一步是什么），**禁止**使用变更叙事措辞（"已经 / 不再 / 原本 / 收纳 / 次级" 等）。

---

## 决策总览

| # | 议题 | 裁决 |
|---|------|------|
| 1 | 首页三处引导（3 → 1） | 删除 `CreationSetupNotice`；保留 `FirstNovelJourneyStrip` 为唯一轻量引导条；保留 `HomeNextActionPanel`（首页主卡片，非冗余引导），不折叠。 |
| 2 | 设置卡片 → 仅计数 | `SettingsOverviewPage` 自动导演卡片改为计数式摘要（如"N 个待确认项"），去掉泄露内部流程名的 `autoApprovalSummary`；`AutoDirectorApprovalPointMultiSelect:52` 同步柔化。 |
| 3 | 按钮文案"查看进度"/名词当按钮 bug | `NovelProjectCard:169-173` 三处 "AI 推进状态" → 动作文案"查看进度"；`NovelExistingProjectTakeoverDialog:332-338` 三处 toast 改为指向「运行记录」的"查看进度"，并移除 `:337` 的"排队和"。 |
| 4 | `director-follow-up.md` 重写不删除 | 重写为指路页（停更说明 + 跳转表 + 唯一正确入口）；**不删除**。删除会破坏 `docsManifest.ts:135/138`、`development-roadmap.md:24`、`sitemap.xml:94`。`routes.ts:205` 注册说法为**误**，已剔除。 |

---

## 1. 首页引导入口整合（3 → 1）

### 决策
- **删除 `CreationSetupNotice`**（冗余的配置提示）。
- **保留 `FirstNovelJourneyStrip`** 作为首页唯一轻量引导条。
- **保留 `HomeNextActionPanel`**（首页主卡片），**不折叠**进引导条。

### 文件与行号（已核实）
- `client/src/pages/Home.tsx:226-228` —— 顺序渲染三处：
  - `:226` `<CreationSetupNotice />`
  - `:227` `<FirstNovelJourneyStrip />`
  - `:228-235` `<HomeNextActionPanel ... />`
- `client/src/components/onboarding/CreationSetupNotice.tsx`（38 行，琥珀色提示，`onClick={openQuickSetup}` 在 `:32`）。
- `client/src/components/onboarding/FirstNovelJourneyStrip.tsx`（按 `kind` 分流，`open_quick_setup` → `<button onClick={openQuickSetup}>` 在 `:50`，否则 `<Link>` 在 `:55`）。
- `client/src/pages/home/components/HomeNextActionPanel.tsx`（首页主卡片：`StarterPanel` 分支在 `:191-226`，有小说时主分支展示"继续你的故事" + 旅程路线图）。

### 裁决理由
- **`CreationSetupNotice` 删除**：对"无小说"新手，它与 `HomeNextActionPanel` 内的 `StarterPanel` 起始路径重复竞争注意力；对已就绪用户，其 `:16` 已 `return null`，本身即条件隐藏。其"完成快捷配置"信息由 `FirstNovelJourneyStrip` 的 `open_quick_setup` 动作与 `StarterPanel` 覆盖，属冗余。从 `Home.tsx:226` 移除该组件调用即可。
- **`FirstNovelJourneyStrip` 保留**：它是针对"创作中首本书"新手的里程碑引导条，带单一主行动（打开快捷配置或跳转），是首书引导的自然落点。
- **`HomeNextActionPanel` 保留（不折叠）**：它是首页核心主卡片/工作台，并非与引导条竞争的提示条，二者**目的不重叠**：
  - `StarterPanel`（无小说）= 真新手的"开始写第一本书"主行动入口；
  - 主分支（有小说）= "继续你的故事" + 进度路线图，面向续写用户。
  - 唯一重合出现在"首本书进行中"状态：此时引导条与主分支都展示进度 + 继续。裁决：**两者都保留，不做代码折叠**；改为统一文案，让新手读到一条连贯的"开始/继续你的第一本书"叙事。

### 用户视角文案意图
- 给新手**一条清晰**的"开始写第一本书"路径。规范入口标签应写成用户可执行的动作（如"写你的第一本书" / "开始你的第一本书"），而非系统状态名词。
- 无小说时：主卡片 `StarterPanel` 即为唯一入口，标签对齐"开始写第一本书"框架。
- 首书进行中时：`FirstNovelJourneyStrip` 为唯一轻量引导条，其主行动即"下一步"（打开快捷配置 / 继续）。

### 待澄清问题
- "首本书进行中"状态下，进度是只在 `HomeNextActionPanel` 展示、引导条降级为轻量里程碑，还是两者并存？本决策定为并存（v1 不折叠），视觉去重留作 UI 打磨。
- `StarterPanel` 现有"自动导演写长篇 / 创作一篇短篇 / 手动创建小说"三按钮，是否改为与"写你的第一本书"一致的框架文案？建议对齐，待文案确认。

---

## 2. 设置卡片 → 仅计数（去掉内部流程名）

### 决策
自动导演设置卡片的摘要，由当前泄露内部流程名的散文（`context.autoApprovalSummary`）改为**仅计数**式摘要（如"N 个待确认项"），不含任何内部流程措辞。

### 文件与行号（已核实）
- `client/src/pages/settings/views/SettingsOverviewPage.tsx`
  - `:32-75` 三张卡片；自动导演卡片 `summary` 函数在 `:57-64`，于 `:62` 消费 `context.autoApprovalSummary`。
  - 现状（`:57-64`）：
    ```
    summary: (context) => {
      if (!context.autoApprovalLoaded) {
        return "正在读取自动确认设置";
      }
      return context.autoApprovalPointCount > 0
        ? `${context.autoApprovalSummary} 会自动通过，其余关键环节等你确认`
        : "每个关键环节都会等你确认";
    },
    ```
- `client/src/components/autoDirector/AutoDirectorApprovalPointMultiSelect.tsx:52`
  - 现状：`${labels.slice(0, 2).join("、")} 等 ${labels.length} 项` —— 泄露内部审批点名称（如"正文生成、章节规划 等 5 项"）。

### 确切改动
- `SettingsOverviewPage.tsx:57-64` 改为计数式、用户视角（**建议文案**）：
  ```
  summary: (context) => {
    if (!context.autoApprovalLoaded) {
      return "正在读取你的确认偏好";
    }
    return context.autoApprovalPointCount > 0
      ? `有 ${context.autoApprovalPointCount} 个待确认项`
      : "关键环节都会等你确认";
  },
  ```
  > 规范示例以"N 个待确认项"为准（N = 需要用户确认的事项数，见下方待澄清）。
- `AutoDirectorApprovalPointMultiSelect.tsx:52` 柔化：去掉内部审批点标签，改为计数式，如 `已选 ${labels.length} 项`。该组件位于设置内，显示"已选 N 项"即可，不列具体流程名。

### 用户视角文案意图
- 设置总览应告诉新手"还有几件事需要你拍板"，用大白话计数，而非点名内部审批环节。
- "N 个待确认项" / "已选 N 项" —— 只给数字，不给流程名词。

### 待澄清问题
- "待确认项"的 N 取哪个值？当前 `autoApprovalPointCount` 是"设为自动通过"的环节数（非待确认数）。工程需明确：N 应取"未设为自动通过、仍需用户确认"的环节数，或新增专用计数字段。请在实现时确认数据源。
- 三张卡片是否保留 `summary` 这一行文案槽位？本决策：保留槽位，内容改为仅计数。

---

## 3. 按钮文案"查看进度" / 名词当按钮 bug

### 决策
进度区域即「运行记录」（任务中心，只读）。按钮与提示文案须写"查看进度"并指向运行记录，**不得**使用内部流程术语（"AI 推进状态""执行""排队"）。

### 文件与行号（已核实）
- `client/src/pages/novels/components/list/NovelProjectCard.tsx:169-173`
  - `:169` `title="AI 推进状态"`
  - `:170` `aria-label="AI 推进状态"`
  - `:173` `<span className="text-xs">AI 推进状态</span>`
  - 该按钮 `:165-168` `onClick` 调 `props.onOpenCockpit(props.novel.id)` → 打开只读任务中心（运行记录）。名词被当成按钮用，属 bug。
- `client/src/pages/novels/components/NovelExistingProjectTakeoverDialog.tsx:332-338`（toast 三分支均含"可在 AI 推进状态查看…进度"）：
  - `:334`（full_book_autopilot）：`自动导演接管任务已提交，可在 AI 推进状态查看全书执行进度。`
  - `:336`（auto_to_execution）：`自动导演接管任务已提交，可在 AI 推进状态查看 ${buildDirectorAutoExecutionPlanLabel(autoExecutionPlan)} 的执行进度。`
  - `:337`（else）：`自动导演接管任务已提交，可在 AI 推进状态查看排队和执行进度。`（须移除"排队和"）

### 确切改动
- `NovelProjectCard.tsx:169-173` 三处 "AI 推进状态" → 动作文案"查看进度"：
  - `:169` `title="查看进度"`
  - `:170` `aria-label="查看进度"`
  - `:173` `<span className="text-xs">查看进度</span>`
  - 理由：它是按钮（动作），不是状态标签；"查看进度"告诉新手按钮做什么。
- `NovelExistingProjectTakeoverDialog.tsx:332-338` 三分支 toast 改为指向「运行记录」的"查看进度"（**建议统一文案**）：
  - `:334` → `自动导演已开始，可在运行记录查看进度。`
  - `:336` → `自动导演已开始，可在运行记录查看进度。`
  - `:337` → `自动导演已开始，可在运行记录查看进度。`（同时移除"排队和"，符合要求）
  - 规范以"可在运行记录查看进度"为准；是否保留"全书/计划"等定制前缀留作可选（见待澄清）。

### 用户视角文案意图
- 按钮应描述**动作**（"查看进度"），而非命名内部管线状态（"AI 推进状态"）。
- 落地处是「运行记录」（只读任务中心）——说出它的名字，不要说"AI 推进状态"。

### 待澄清问题
- toast 是否保留"全书/计划"等定制前缀，还是统一为"可在运行记录查看进度"？建议为新手清晰度**统一**，待文案确认。
- 确认"运行记录"即该按钮打开的任务中心（onOpenCockpit → AICockpit / TaskCenter）。仓库内 Sidebar、TaskCenter 均使用"运行记录"，命名一致，无需额外改动。

---

## 4. `director-follow-up.md` 重写为指路页（不删除）

### 决策
将 `docs/public/modules/director-follow-up.md` **重写**为指路页，**不得删除**。指路页内容：
1. 停更说明：本页现为指路页，其描述的能力仍在「运行记录」中运行。
2. 跳转表：旧主题 → 唯一正确入口。
3. 唯一正确入口链接（运行记录 / 任务中心，及对应流程文档）。

### 文件与行号（已核实）
- `docs/public/modules/director-follow-up.md` —— 待重写的文档站页面。
- `site/src/docsManifest.ts:135,138` —— 注册 `module-director-follow-up` → `docs/public/modules/director-follow-up.md`。**删除文件会使该清单条目失效（文档断链 / 构建门禁失败）。**
- `docs/public/development-roadmap.md:24` —— `[自动导演后续操作](#/docs/module-director-follow-up)` 入链。**删除会断此链。**
- `site/public/sitemap.xml:94` —— `<loc>.../docs/module-director-follow-up</loc>` 外部站点地图入链（新增的第三处依赖，同样反对删除）。
- **（勘误）** 此前" `client/src/lib/router/routes.ts:205` 静态注册了 `/director-follow-up` "的说法为**误**。已核实：`client/src` 下无 `lib/router/` 目录；`**/router/routes.ts` 全仓无此文件；`client/src` 与 `site/src` 中均不存在 `/director-follow-up` 路由字符串。该路径**仅为文档站入口**。此理由须从决策依据中剔除（与 `10-docs-terminology-inventory.md:59` 一致）。

### 裁决理由
删除会破坏 `docsManifest.ts:135/138`（构建门禁）与 `development-roadmap.md:24` 入链，且其描述的能力（自动导演 checkpoint / 暂停恢复）仍运行于「运行记录」。能力尚在，仅文档需"指路"而非"描述"。

### 用户视角文案意图
- 页面应一行告知读者"现在去哪看"（运行记录），而非叙述"改了什么"。
- 禁用变更叙事措辞（"已不再 / 原本"）。示例口吻："导演的后续操作现在在「运行记录」查看。下面是对应入口。"

### 待澄清问题
- 跳转表的具体映射：旧 follow-up 主题分别对应哪个 UI/文档入口（运行记录 + 相关流程文档）。
- 该页是否保留在文档侧边栏（docsManifest 条目）？建议保留但仅作指路页。

---

## 参考
- `docs/simplification/10-docs-terminology-inventory.md`（裁决 5：重写不删；`routes.ts:205` 误述勘误）
- `docs/simplification/03-followup-removal-assessment.md`（follow-up 能力保留评估）
- 仓库内既有命名核查：`运行记录` 为任务中心用户面名称；`查看进度` 在 Sidebar / TaskCenter 等已采用 —— 佐证第 3 项术语。
