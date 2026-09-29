# AI 小说创作工作台英文命名与兼容边界

## Background

项目中文名为“AI 小说创作工作台”，早期英文展示使用 `AI Novel Production Engine`，仓库使用 `AI Novel Writing Assistant`。英文名称能说明品类，但缺少可被复述和持续积累的品牌识别；同时，产品能力已经从单次写作辅助扩展到自动导演、长篇规划、章节生产、状态回灌、质量修复和叙事资产管理。

## Decision

中文正式名继续使用 **AI 小说创作工作台**，英文正式名更新为 **Novel2all**。

命名分工如下：

- “AI 小说创作工作台”保持现有中文认知与功能定位。
- `Novel2all` 是唯一英文正式名，负责品牌记忆与对外识别。
- `AI Novel Production Engine` 与 `AI Novel Writing Assistant` 作为旧英文展示名和仓库搜索词继续保留在公开元数据中。

## Current Rule

用户可见界面、公开介绍站和当前文档应优先组合显示：

> AI 小说创作工作台 / Novel2all

本次仅更新英文名，不应将“AI 小说创作工作台”描述为原名或旧名。空间有限的中文界面优先显示中文名，并在副标题或页面元数据中显示 `Novel2all`。

仓库已迁移到 `https://github.com/ourvps1688/novel2all`，公开介绍站 Pages 地址为 `https://ourvps1688.github.io/novel2all/`（站点 base 路径为 `/novel2all/`）。

应用数据目录、环境变量、内部 workspace 包名和旧数据库识别信息继续保留既有技术名称。这些标识承担链接、升级、数据和自动化兼容职责，不应仅为视觉统一而修改。

仓库介绍、页面元数据和公开文档应继续保留 `AI Novel Writing Assistant`、`AI novel writing`、`长篇小说创作` 等品类关键词，让新品牌负责记忆，品类描述负责搜索发现。

## Failure Modes

- 只显示 `Novel2all` 而不说明小说品类，首次访问者可能无法判断产品服务什么。
- 把“AI 小说创作工作台”标成旧名，会让中文用户误以为产品连中文品牌也发生了迁移。
- 为追求名称统一而修改本地数据目录或旧数据库标记，可能让升级后的用户看不到已有作品。
- 继续把旧仓库地址写进公开入口，会产生 404 并分散权重；旧地址只出现在历史变更记录和兼容说明中。
- 把两个旧英文名长期放在导航主标题中，会削弱 `Novel2all` 的记忆度；旧名只用于兼容说明和搜索元数据。

## Related Modules

- `README.md`
- `client/src/components/layout/`
- `site/`
- `docs/public/`
- `server/src/runtime/appPaths.ts`
