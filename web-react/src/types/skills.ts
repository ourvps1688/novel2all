/**
 * Skill 系统 TypeScript 类型 + Zod Schema 定义
 *
 * 数据来源：
 *   - 后端: GET /api/skills (基础 list, 不含 category / icon / inputSchema)
 *   - 前端: data/skillCategories.ts (硬编码兜底, 见 playbook §13)
 *
 * 设计：
 *   - Skill (api/types.ts) 是后端原始定义 (name/description/flags)
 *   - SkillInfo (本文件) 在 Skill 基础上叠加前端 UI 元数据
 *   - 所有执行态 (task_id/progress/output) 都通过 zod 校验
 */

import { z } from 'zod';

// ============ 分类 ============

/** Skill 分类 (前端 UI 分组用) */
export type SkillCategory = '创作类' | '分析类' | '工具类' | '入口类' | '内部';

/** V1.5.1 Sprint 1.1 修复（已知问题 #5）：UI 现在展示全部 13 个 skill，
 *  内部 skill 加 "内部工具" badge 提示用户。
 *  SKILL_CATEGORY_LIST 包含全部 5 个分类（含 '内部'），让用户能按内部分类筛选/查看。 */
export const SKILL_CATEGORY_LIST: SkillCategory[] = [
  '创作类',
  '分析类',
  '工具类',
  '入口类',
  '内部',
];

// ============ JSON Schema (子集) ============

/**
 * JSON Schema 最小子集 - 够 SkillRunner 的 DynamicForm 用即可
 * 完整 spec 见 https://json-schema.org/draft-07/schema
 */
export interface JSONSchema {
  type: 'object' | 'string' | 'number' | 'integer' | 'array' | 'boolean';
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  properties?: Record<string, JSONSchema>;
  required?: string[];
  items?: JSONSchema;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
}

// ============ Skill Info ============

/**
 * Skill 元信息 - UI 层使用的扩展视图
 *
 * 后端 /api/skills 返回的最小字段 + 前端硬编码的元数据 (category / icon / inputSchema)
 */
export interface SkillInfo {
  /** Skill 标识 (e.g. "story-long-write") */
  name: string;

  /** 人类可读描述 */
  description: string;

  /** 是否允许用户手动触发 */
  userInvocable: boolean;

  /** 是否允许 LLM 自动调用 (tool-use) */
  modelInvocable: boolean;

  /** 分类 (前端硬编码) */
  category: SkillCategory;

  /** 图标 (MUI 图标组件名, 如 "Edit", "Search") */
  icon: string;

  /** emoji 图标 (兜底, 移动端 / emoji 风格场景) */
  emoji: string;

  /** 版本 (前端硬编码兜底 "1.0") */
  version: string;

  /** 输入表单 schema (前端硬编码兜底) */
  inputSchema?: JSONSchema;

  /** 默认输入 (demo / 模板) */
  defaultInput?: string;
}

// ============ 执行态 ============

/** 执行阶段状态机 */
export type SkillExecutionPhase =
  | 'idle' // 初始
  | 'preparing' // 提交 execute 中
  | 'running' // SSE 流中
  | 'success' // 完成
  | 'error' // 失败
  | 'cancelled'; // 取消

/**
 * 写入进度 (story-long-write 8 阶段; 其它 skill 复用同一字段集)
 */
export interface WriteProgress {
  phase: WritePhase;
  charsWritten: number;
  charsPerSecond?: number;
  etaSeconds?: number;
  taskId?: string;
  message?: string;
}

export type WritePhase =
  | 'init'
  | 'pre_write_check'
  | 'writing'
  | 'save'
  | 'extract'
  | 'merge'
  | 'post_write_check'
  | 'done';

/** 单条输出片段 */
export interface SkillOutputChunk {
  /** text / json / file */
  type: 'text' | 'json' | 'file';
  text?: string;
  data?: unknown;
  filename?: string;
}

/** 最终输出 (onDone 时聚合) */
export interface SkillOutput {
  text: string;
  chunks: SkillOutputChunk[];
  durationMs: number;
  taskId: string;
  metadata: Record<string, unknown>;
}

// ============ API 请求 / 响应 Zod Schema ============

/**
 * Skill 任务状态枚举 (后端实际返回的所有 status 值)
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #4）：后端 /api/skills/{name}/execute
 * 立即返回 ``status: "started"``（参见 app.py:1029），旧版本 enum 只含
 * ['queued','running','done','failed','cancelled']，导致前端 zod parse
 * 失败 + SSE 链路整个断掉。补全为后端真实可能返回的 7 个状态：
 *
 *   - ``started``   POST /execute 立即返回（任务已入队，尚未跑）
 *   - ``queued``    异步队列等待（若后端未来加 LLM 限流会用到）
 *   - ``running``   正在执行
 *   - ``done``      成功完成
 *   - ``failed``    失败
 *   - ``cancelled`` 用户取消
 *   - ``timeout``   超时（防御性，未来可加）
 *
 * 任何后端新增状态都应同步加入此 enum，避免 zod parse 失败。
 */
export const SkillStatusEnum = z.enum([
  'started',
  'queued',
  'running',
  'done',
  'failed',
  'cancelled',
  'timeout',
]);
export type SkillStatus = z.infer<typeof SkillStatusEnum>;

/** 执行请求 (POST /api/skills/{name}/execute) */
export const SkillExecuteRequestSchema = z.object({
  /** Skill 调用参数 (skill inputSchema 校验) */
  params: z.record(z.string(), z.unknown()),
  /** 项目根路径 (默认 ".") */
  projectRoot: z.string().default('.'),
  /** 幂等键 (避免重复扣费) */
  idempotencyKey: z.string().optional(),
});
export type SkillExecuteRequest = z.infer<typeof SkillExecuteRequestSchema>;

/**
 * 执行响应 (POST /api/skills/{name}/execute 返回)
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #4）：status enum 已扩展为 SkillStatusEnum
 * （含 ``started``）。后端立即返回 ``{"status": "started", ...}``。
 */
export const SkillExecuteResponseSchema = z.object({
  task_id: z.string(),
  status: SkillStatusEnum,
  started_at: z.number().optional(),
});
export type SkillExecuteResponse = z.infer<typeof SkillExecuteResponseSchema>;

/**
 * 状态查询响应 (GET /api/skills/{name}/status?task_id=...)
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #4）：status enum 已扩展为 SkillStatusEnum。
 * SSE 流首批事件可能为 ``started``，之后是 ``running`` → ``done`` / ``failed`` /
 * ``cancelled``。
 */
export const SkillStatusResponseSchema = z.object({
  task_id: z.string(),
  status: SkillStatusEnum,
  phase: z
    .enum(['init', 'pre_write_check', 'writing', 'save', 'extract', 'merge', 'post_write_check', 'done'])
    .optional(),
  progress: z.number().optional(),
  chars_written: z.number().optional(),
  chars_per_second: z.number().optional(),
  eta_seconds: z.number().optional(),
  chunk: z.string().optional(),
  output: z.string().optional(),
  message: z.string().optional(),
  error: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});
export type SkillStatusResponse = z.infer<typeof SkillStatusResponseSchema>;

// ============ Review (skill = story-review) ============

/**
 * Review Issue - 4-agent 审查输出的单个问题
 * V1.5.0 修复版本（兼容后端 multi_reviewer.py:ConsistencyIssue）
 */
export const ReviewIssueSchema = z.object({
  severity: z.enum(['critical', 'major', 'minor', 'warning', 'info']),
  category: z.string(),
  description: z.string(),
  evidence: z.string().optional(),
  suggestion: z.string().optional(),
  agent: z.string().optional(),
  agent_label: z.string().optional(),
  /** 锚点 (章节 + offset) */
  anchor: z
    .object({
      chapter: z.number(),
      offset: z.number(),
    })
    .optional(),
});
export type ReviewIssue = z.infer<typeof ReviewIssueSchema>;

/**
 * Review Report - 4-agent 审查的最终聚合报告
 * 与 api/types.ts 的 ReviewReportSchema 兼容；本文件为 skill 视图增加 alias
 */
export const ReviewReportSchema = z.object({
  chapter: z.number().optional(),
  chapter_number: z.number().optional(),
  critical_issues: z.array(ReviewIssueSchema),
  major_issues: z.array(ReviewIssueSchema),
  minor_issues: z.array(ReviewIssueSchema),
  quality_score: z
    .union([
      z.number(),
      z.object({
        overall_score: z.number(),
        verdict: z.enum(['pass', 'warn', 'fail']).optional(),
      }),
    ])
    .optional(),
  overall_verdict: z.enum(['pass', 'warn', 'fail']).optional(),
  elapsed_seconds: z.number().optional(),
  content_chars: z.number().optional(),
  timestamp: z.string().optional(),
  _idempotent_replay: z.boolean().optional(),
});
export type ReviewReport = z.infer<typeof ReviewReportSchema>;

// ============ 历史记录 (zustand) ============

/** Skill 执行历史 (skillExecutionStore) */
export interface SkillExecutionHistoryEntry {
  skillName: string;
  taskId: string;
  startedAt: number;
  finishedAt: number | null;
  status: SkillExecutionPhase;
  inputPreview: string;
  outputPreview: string;
  durationMs: number;
}

// ============ 工具函数 ============

/** 阶段权重 → 进度条百分比 (8 阶段写作用) */
export const PHASE_WEIGHTS: Record<WritePhase, number> = {
  init: 0,
  pre_write_check: 5,
  writing: 60,
  save: 75,
  extract: 85,
  merge: 95,
  post_write_check: 99,
  done: 100,
};

/** 给定当前 phase, 计算进度条百分比 0~100 */
export function phaseProgressPercent(phase: WritePhase): number {
  return PHASE_WEIGHTS[phase] ?? 0;
}

/** 阶段中文 label */
export const PHASE_LABELS: Record<WritePhase, string> = {
  init: '初始化',
  pre_write_check: '写作前检查',
  writing: '写作中',
  save: '保存',
  extract: '提取',
  merge: '合并',
  post_write_check: '写作后检查',
  done: '完成',
};