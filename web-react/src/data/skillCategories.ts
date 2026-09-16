/**
 * 13 Skill 硬编码元数据 (playbook §13 兜底)
 *
 * 设计动机：
 *   - 后端 /api/skills 当前仅返回 name/description/user_invocable/model_invocable
 *   - 缺失字段：category / icon / inputSchema / defaultInput
 *   - 前端硬编码 mapping 保证 SkillRunner / DynamicForm / SkillsPage 立即可用
 *   - 若后端后续扩展 inputSchema，可在 api/skills.ts 中合并后端字段
 *
 * 约束：
 *   - 必须保持 13 个 skill 完整覆盖 (V1.5.0 后端实现)
 *   - 不要随便改名 (与后端 src/novel2all/skills/ 目录对齐)
 */

import type { JSONSchema, SkillCategory } from '../types/skills';

export interface SkillMeta {
  /** Skill 名称 (与后端 /api/skills 的 name 对齐) */
  skill: string;
  category: SkillCategory;
  /** MUI 图标组件名 (动态 import 用) */
  icon: string;
  /** emoji 图标 (兜底) */
  emoji: string;
  /** 中文显示名 */
  label: string;
  /** 默认输入 placeholder */
  defaultInput: string;
  /** 输入表单 schema (前端硬编码; 缺失时 SkillRunner 显示 Alert) */
  inputSchema?: JSONSchema;
  /** 版本 */
  version: string;
  /**
   * V1.5.1 Sprint 1.1 修复（已知问题 #5）：内部 skill 标记
   *
   * - true → 该 skill 仅供模型调用（如 browser-cdp），UI 仍展示但加 "内部工具" badge
   * - false/undefined → 正常用户可用 skill
   *
   * 注意：分类 ``category === '内部'`` 是分类维度；本 flag 是行为维度。
   * 后端目前只有 ``browser-cdp`` 是内部 skill；将来若有更多内部 tool，统一在此处标记。
   */
  isInternal?: boolean;
}

/**
 * 13 Skill 完整 mapping (按后端注册顺序排列)
 *
 * 类别分布：
 *   - 入口类 (1): story
 *   - 创作类 (4): story-setup / story-long-write / story-short-write / story-cover
 *   - 分析类 (4): story-long-analyze / story-long-scan / story-short-analyze / story-short-scan
 *   - 工具类 (3): story-deslop / story-review / story-import
 *   - 内部 (1): browser-cdp (不对用户展示)
 */
export const SKILL_CATEGORIES: SkillMeta[] = [
  {
    skill: 'story',
    category: '入口类',
    icon: 'Route',
    emoji: '🧭',
    label: '智能路由',
    defaultInput: '我想写一个关于 XXX 的小说',
    version: '1.0',
  },
  {
    skill: 'story-setup',
    category: '创作类',
    icon: 'Settings',
    emoji: '⚙️',
    label: '项目初始化',
    defaultInput: '',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['project_name', 'genre'],
      properties: {
        project_name: {
          type: 'string',
          title: '项目名',
          description: '笔下作品名',
          minLength: 1,
          maxLength: 50,
        },
        pen_name: { type: 'string', title: '笔名', maxLength: 30 },
        genre: {
          type: 'string',
          title: '题材',
          enum: ['玄幻', '都市', '科幻', '历史', '言情', '悬疑', '武侠', '军事', '其他'],
        },
        platform: {
          type: 'string',
          title: '目标平台',
          enum: ['起点', '番茄', '七猫', '盐言', '不限'],
        },
        style_anchor: {
          type: 'string',
          title: '文风锚点 (可选)',
          maxLength: 200,
          description: '如: 古龙风、网文爽文',
        },
      },
    },
  },
  {
    skill: 'story-long-write',
    category: '创作类',
    icon: 'Edit',
    emoji: '✍️',
    label: '长篇写作',
    defaultInput: '题材 + 主角 + 大纲',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['chapter', 'outline'],
      properties: {
        chapter: { type: 'number', title: '章节号', minimum: 1 },
        outline: { type: 'string', title: '章节大纲', minLength: 50, maxLength: 2000 },
        keypoints: { type: 'string', title: '关键转折点', maxLength: 1000 },
        previous_context: { type: 'string', title: '上文要点', maxLength: 1000 },
        target_chars: {
          type: 'number',
          title: '字数目标',
          default: 2000,
          minimum: 500,
          maximum: 10000,
        },
      },
    },
  },
  {
    skill: 'story-long-analyze',
    category: '分析类',
    icon: 'Analytics',
    emoji: '🔍',
    label: '长篇拆文',
    defaultInput: '书名 + URL',
    version: '1.0',
    inputSchema: {
      type: 'object',
      properties: {
        chapters: {
          type: 'array',
          title: '选章节',
          items: { type: 'number' },
          minItems: 1,
          maxItems: 20,
        },
        aspects: {
          type: 'array',
          title: '分析维度',
          items: {
            type: 'string',
            enum: ['黄金三章', '爽点密度', '节奏曲线', '文风'],
          },
        },
      },
    },
  },
  {
    skill: 'story-long-scan',
    category: '分析类',
    icon: 'Search',
    emoji: '📊',
    label: '长篇扫榜',
    defaultInput: '起点/番茄 等',
    version: '1.0',
    inputSchema: {
      type: 'object',
      properties: {
        genre: { type: 'string', title: '题材' },
        date_range: { type: 'string', title: '时间范围 (YYYY-MM,YYYY-MM)' },
      },
    },
  },
  {
    skill: 'story-short-write',
    category: '创作类',
    icon: 'Article',
    emoji: '✏️',
    label: '短篇写作',
    defaultInput: '主题 + 情绪',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['topic', 'platform'],
      properties: {
        topic: { type: 'string', title: '主题', minLength: 5 },
        emotion_hook: { type: 'string', title: '情绪钩子' },
        platform: {
          type: 'string',
          title: '平台',
          enum: ['盐言', '番茄', '七猫'],
        },
      },
    },
  },
  {
    skill: 'story-short-analyze',
    category: '分析类',
    icon: 'Analytics',
    emoji: '🔬',
    label: '短篇拆文',
    defaultInput: '文章 URL 或正文',
    version: '1.0',
    inputSchema: {
      type: 'object',
      properties: {
        text: { type: 'string', title: '短篇全文', minLength: 100 },
      },
    },
  },
  {
    skill: 'story-short-scan',
    category: '分析类',
    icon: 'Search',
    emoji: '📈',
    label: '短篇扫榜',
    defaultInput: '知乎盐言/番茄短篇/七猫',
    version: '1.0',
    inputSchema: {
      type: 'object',
      properties: {
        platform: {
          type: 'string',
          title: '平台',
          enum: ['盐言', '番茄', '七猫'],
        },
        category: { type: 'string', title: '分类' },
      },
    },
  },
  {
    skill: 'story-cover',
    category: '创作类',
    icon: 'Image',
    emoji: '🎨',
    label: '封面生成',
    defaultInput: '书名 + 题材 + 文风',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['book_title', 'genre'],
      properties: {
        book_title: { type: 'string', title: '书名', minLength: 1, maxLength: 30 },
        genre: { type: 'string', title: '题材' },
        style_keywords: { type: 'string', title: '风格关键词 (逗号分隔)', maxLength: 200 },
      },
    },
  },
  {
    skill: 'story-deslop',
    category: '工具类',
    icon: 'AutoFixHigh',
    emoji: '✨',
    label: '去 AI 味',
    defaultInput: '段落文本（可粘贴章节）',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['text'],
      properties: {
        text: { type: 'string', title: '待去 AI 味的文本', minLength: 50, maxLength: 5000 },
      },
    },
  },
  {
    skill: 'story-review',
    category: '工具类',
    icon: 'RateReview',
    emoji: '📋',
    label: '4 视角审查',
    defaultInput: '章节内容',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['chapter'],
      properties: {
        chapter: { type: 'number', title: '章节号', minimum: 1 },
      },
    },
  },
  {
    skill: 'story-import',
    category: '工具类',
    icon: 'Upload',
    emoji: '📥',
    label: '已有小说导入',
    defaultInput: '文件路径或 URL',
    version: '1.0',
    inputSchema: {
      type: 'object',
      required: ['file_path'],
      properties: {
        file_path: {
          type: 'string',
          title: '文件路径 (相对项目根)',
          description: '如: ./my-novel/全集.txt',
        },
      },
    },
  },
  {
    skill: 'browser-cdp',
    category: '内部',
    icon: 'Lock',
    emoji: '🌐',
    label: '浏览器能力',
    defaultInput: 'URL',
    version: '1.0',
    // V1.5.1 Sprint 1.1 修复（已知问题 #5）：UI 仍展示此 skill 但加 "内部工具" badge
    isInternal: true,
  },
];

/** 快速按 skill name 查询 meta */
export const CATEGORY_MAP: Record<string, SkillMeta> = Object.fromEntries(
  SKILL_CATEGORIES.map((m) => [m.skill, m]),
);

/**
 * V1.5.1 Sprint 1.1 修复（已知问题 #5）：UI 现在展示全部 13 个 skill。
 * 内部 skill (browser-cdp) 加 "内部工具" badge 提示用户。
 *
 * 为了向后兼容，保留 VISIBLE_SKILLS 导出，含义改为「用户可直接手动调用的 skill」
 * (即 isInternal !== true 的 skill)；外部代码若依赖 VISIBLE_SKILLS.length === 12，
 * 请改用 ``INTERNAL_SKILLS`` 或 ``USER_INVOCABLE_SKILLS``。
 */
export const USER_INVOCABLE_SKILLS: SkillMeta[] = SKILL_CATEGORIES.filter(
  (m) => m.isInternal !== true,
);

/** V1.5.1 已弃用：旧定义（排除 category==='内部'），保留以避免破坏依赖方。
 *  实际行为同 USER_INVOCABLE_SKILLS（browser-cdp 同时是 category==='内部' + isInternal===true）。 */
export const VISIBLE_SKILLS: SkillMeta[] = USER_INVOCABLE_SKILLS;

/** 仅内部 skill (目前只有 browser-cdp) — 用于调试 / Admin 视图 */
export const INTERNAL_SKILLS: SkillMeta[] = SKILL_CATEGORIES.filter(
  (m) => m.isInternal === true,
);

/** 默认展示给 Dashboard 快速启动的 4 个高频 skill */
export const QUICK_START_SKILLS: string[] = ['story-setup', 'story-long-write', 'story-long-scan', 'story-cover'];