# Novel2all 项目长期记忆

## 项目身份
- 原名 AI 小说创作工作台，已改名 **Novel2all**，远端 `git@github.com:ourvps1688/novel2all.git`（SSH 已授权，可直接推送）
- 备份：`D:\workbuddyfiles\_backup\AI-Novel-Writing-Assistant-main-20260929-1802`
- 桌面端已彻底移除（用户决定，简化验证后再重建）
- 内部包名仍为 `@ai-novel/*`，未改

## 硬约束（来自 AGENTS.md）
- **Phase 1–3 全程零数据动作**：不碰 `schema.prisma` / `schema.sqlite.prisma` / `migrations/`。孤儿表只记清单，删表属 Phase 4，需备份 + 恢复校验 + 用户逐个显式批准
- 主要用户是**完全不懂写作的新手**；「专家向灵活性」与「新手完成率」冲突时选后者
- UI 文案必须从用户视角说「你能做什么 / 系统在帮你做什么 / 下一步是什么」，禁止实现说明与改版说明式措辞
- 任务中心（`/tasks`，用户侧叫「运行记录」）是只读列表，不得放继续/重试/取消/修复等状态变更动作

## 环境限制（本沙箱，非项目问题）
- `node_modules` 不完整：`pnpm install` 被沙箱拦（esbuild postinstall 调 `wmic.exe`）。**`.bin` 目录不存在**
- 可用：`node ../node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
- vite：`node ../node_modules/.pnpm/vite@7.3.1_@types+node@25.3.3_jiti@2.6.1_yaml@2.8.2/node_modules/vite/bin/vite.js build`
- lockfile：`pnpm install --lockfile-only` 可跑通
- **prisma CLI 不可用** → 无 `.prisma/client` → **服务端测试永远跑不起来**，只能用 tsc 类型比对 + require 路径可达性 + `node --check` 替代
- 22 个 `@prisma/client has no exported member` 报错是基线噪声

## 验证方法论（血泪教训，务必沿用）
1. **跑 client 测试前必须先构建 shared**：`cd shared && node ../node_modules/typescript/bin/tsc -p tsconfig.json`。
   否则 `src/**/*.test.mjs` 里一批用例会因解析不到 `@ai-novel/shared` 变成**文件级失败**，基线失真。真实基线是 **183 用例 / 8 失败**（不是 171/14）。
2. **server tsc 必须用行号不敏感口径**：删代码会让错误行号整体下移，产生大批假新增。
   做法：`sed -E 's/\([0-9]+,[0-9]+\)//'` 后按 `文件|错误码|计数` 聚合做差集（基线约 215 个 key）。
   基线取法：`git checkout <baseline-commit>` 跑一次再切回分支。
3. **client 测试要抓「失败用例名集合」做差集**（`comm -13` / `comm -23`），不能只比总数。
4. `npm test` 的 glob 由 **node 自己**展开，`src/**/*.test.mjs` 能匹配多层目录。

## 简化改造进度（累计约 −36,210 行）
- Phase 1 模块裁减：drama / comic / astrology / chains / promptWorkbench，−30,403
- T03 导演跟进页裁撤（能力并入 `/tasks`），−1,860
- 钉钉/企微通知链路整体移除，−3,890
- 校验链路渠道来源死分支，−57
- Phase 2 进行中，见 `docs/simplification/04-phase2-rescoped.md`（技术）与 `05-phase2-product-decisions.md`（产品）

## 团队协作注意
- 工程师（software-engineer）**连续三次**在挂账项里沿用过期结论（「index.css 死样式未清」，实测残留 0，已在 `cf4694f` 清掉）。**它报的挂账项必须逐条实测，不能照单全收。**
- 架构师（software-architect）的**行数估算不可信**，必须先 grep 确认依赖再报数字。T03 它估 7 文件/2,769 行可删，实测 12 个文件里 11 个必须保留。
- PM（software-product-manager）会主动读架构师的校准并修正自己判断，结论质量高。
