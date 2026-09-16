/**
 * API 响应类型契约（Zod schema + 推导 TS 类型）
 *
 * 后端字段无严格 schema 校验（dict[str, Any]）；用 zod 在前端 runtime 校验
 * 失败时打 console.error 但不抛错（让 UI 优雅降级）
 */

import { z } from 'zod';

// ============ User & Auth ============
//
// 后端 User.to_dict() 实际字段（src/novel2all/core/auth.py:75）：
//   id, username, role, created_at, disabled
//   password_hash 仅当 with_hash=True 才返回（前端正常请求不返回）
// 类型对应：
//   created_at → float (Unix timestamp)
//   disabled   → bool (SQLite INTEGER 经 Python bool 转换后 JSON 序列化为 true/false)

export const UserSchema = z.object({
  id: z.number(),
  username: z.string(),
  // 防御性 optional：to_dict() 默认不返回；万一后端开了 with_hash，前端就忽略
  password_hash: z.string().optional(),
  role: z.enum(['admin', 'editor', 'viewer']),
  created_at: z.number(),
  disabled: z.number(),
});
export type User = z.infer<typeof UserSchema>;

export const AuthMeSchema = z.object({
  user: UserSchema.nullable(),
  authenticated: z.boolean(),
});
export type AuthMe = z.infer<typeof AuthMeSchema>;

export const LoginResponseSchema = z.object({
  user: UserSchema,
  message: z.string().optional(),
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;

export const UsersListSchema = z.object({
  users: z.array(UserSchema),
});
export type UsersList = z.infer<typeof UsersListSchema>;

// ============ Admin: User Projects ============

export const ProjectEntrySchema = z.object({
  path: z.string(),
  name: z.string().optional(),
  created_at: z.string().optional(),
  shared: z.boolean().optional(),
  role: z.string().optional(),
});
export type ProjectEntry = z.infer<typeof ProjectEntrySchema>;

export const UserProjectsSchema = z.object({
  user_id: z.union([z.number(), z.string()]).optional(),
  username: z.string().optional(),
  projects: z.array(ProjectEntrySchema),
});
export type UserProjects = z.infer<typeof UserProjectsSchema>;

// ============ Project Status ============

export const ProjectStatusSchema = z.object({
  initialized: z.boolean(),
  project_root: z.string().optional(),
  project_name: z.string().optional(),
  genre: z.string().optional(),
  style_anchor: z.string().optional(),
  total_chapters_target: z.number().optional(),
  total_word_count_target: z.number().optional(),
  last_updated_chapter: z.number().nullable().optional(),
  character_count: z.number().optional(),
  active_foreshadowing_count: z.number().optional(),
  timeline_count: z.number().optional(),
  summary_count: z.number().optional(),
});
export type ProjectStatus = z.infer<typeof ProjectStatusSchema>;

// ============ Skills & Roles ============

export const SkillSchema = z.object({
  name: z.string(),
  description: z.string().optional(),
  user_invocable: z.boolean().optional(),
  model_invocable: z.boolean().optional(),
});
export type Skill = z.infer<typeof SkillSchema>;

export const RoleSchema = z.object({
  name: z.string(),
  description: z.string().optional(),
  preferred_model: z.string().optional(),
});
export type Role = z.infer<typeof RoleSchema>;

// ============ Models ============

export const ModelSchema = z.object({
  name: z.string(),
  anthropic_compat: z.boolean().optional(),
  api_base: z.string().nullable().optional(),
  api_key_env: z.string().nullable().optional(),
});
export type Model = z.infer<typeof ModelSchema>;

export const CurrentModelSchema = z.object({
  model: z.string(),
});
export type CurrentModel = z.infer<typeof CurrentModelSchema>;

export const ModelSwitchResponseSchema = z.object({
  old_model: z.string(),
  new_model: z.string(),
});
export type ModelSwitchResponse = z.infer<typeof ModelSwitchResponseSchema>;

// ============ Cache ============
//
// 后端 src/novel2all/core/prompt_cache_tracker.py + cache.py 字段对齐：
//   PromptPrefixStats.to_dict(): prefix_hits, prefix_misses, total, hit_rate,
//     unique_sys_prompts, cost_saved_cny, potential_savings_cny, enabled, model
//   CacheBase.stats(): enabled, backend, size, max_size, hits, misses,
//     hit_rate, ttl_seconds, persist_path, lock_backend, + prompt_prefix

const PromptPrefixModelSchema = z.object({
  avg_input_tokens_per_call: z.number(),
  cache_hit_price_cny_per_m: z.number(),
  cache_miss_price_cny_per_m: z.number(),
});

export const PromptPrefixStatsSchema = z.object({
  prefix_hits: z.number(),
  prefix_misses: z.number(),
  total: z.number(),
  hit_rate: z.number(),
  unique_sys_prompts: z.number(),
  cost_saved_cny: z.number(),
  potential_savings_cny: z.number(),
  enabled: z.boolean(),
  model: PromptPrefixModelSchema.nullable(),
});
export type PromptPrefixStats = z.infer<typeof PromptPrefixStatsSchema>;

export const CacheStatsSchema = z.object({
  enabled: z.boolean(),
  backend: z.string(),
  size: z.number(),
  max_size: z.number(),
  hits: z.number(),
  misses: z.number(),
  hit_rate: z.number(),
  ttl_seconds: z.number(),
  persist_path: z.string().nullable(),
  lock_backend: z.string(),
  prompt_prefix: PromptPrefixStatsSchema,
});
export type CacheStats = z.infer<typeof CacheStatsSchema>;

export const CacheRecommendSchema = z.object({
  current: z
    .object({
      backend: z.string(),
      max_size: z.number(),
      ttl_seconds: z.number(),
    })
    .optional(),
  recommended: z.record(z.string(), z.unknown()).optional(),
  actions: z.array(z.record(z.string(), z.unknown())).optional(),
  health_score: z.number().optional(),
  issues: z.array(z.string()).optional(),
  confidence: z.enum(['high', 'medium', 'low']).optional(),
  notes: z.array(z.string()).optional(),
});
export type CacheRecommend = z.infer<typeof CacheRecommendSchema>;

// ============ Chapters ============

export const ChapterSchema = z.object({
  chapter: z.number(),
  filename: z.string(),
  char_count: z.number(),
  first_line: z.string(),
});
export type Chapter = z.infer<typeof ChapterSchema>;

export const ChapterContentSchema = z.object({
  chapter: z.number(),
  filename: z.string(),
  content: z.string(),
  char_count: z.number(),
  first_line: z.string(),
});
export type ChapterContent = z.infer<typeof ChapterContentSchema>;

export const ChapterSaveResponseSchema = z.object({
  chapter: z.number(),
  char_count: z.number(),
  output_path: z.string(),
});
export type ChapterSaveResponse = z.infer<typeof ChapterSaveResponseSchema>;

export const ChapterRewriteResponseSchema = z.object({
  chapter: z.number(),
  start: z.number(),
  end: z.number(),
  original: z.string(),
  rewritten: z.string(),
  before_len: z.number(),
  after_len: z.number(),
  model: z.string(),
});
export type ChapterRewriteResponse = z.infer<typeof ChapterRewriteResponseSchema>;

export const ChapterInsertResponseSchema = z.object({
  chapter: z.number(),
  position: z.number(),
  inserted: z.string(),
  before_ctx_len: z.number(),
  after_ctx_len: z.number(),
  model: z.string(),
});
export type ChapterInsertResponse = z.infer<typeof ChapterInsertResponseSchema>;

// ============ Review ============
//
// 后端字段（src/novel2all/core/memory/multi_reviewer.py）：
//   ReviewIssue(ConsistencyIssue): severity in ['critical','warning','info']
//     + category / description / evidence / suggestion + agent / agent_label
//   QualityScore: overall_score / pacing / emotion / readability /
//     immersion / ai_smell / verdict / summary
//   ReviewReport: chapter_number / critical_issues / major_issues /
//     minor_issues / quality_score / total_* / overall_verdict /
//     elapsed_seconds / content_chars / content_preview

export const ReviewIssueSchema = z.object({
  severity: z.enum(['critical', 'warning', 'info']),
  category: z.string(),
  description: z.string(),
  evidence: z.string().optional(),
  suggestion: z.string().optional(),
  agent: z.string().optional(),
  agent_label: z.string().optional(),
});
export type ReviewIssue = z.infer<typeof ReviewIssueSchema>;

const QualityScoreSchema = z.object({
  overall_score: z.number(),
  pacing: z.number(),
  emotion: z.number(),
  readability: z.number(),
  immersion: z.number(),
  ai_smell: z.number(),
  verdict: z.enum(['pass', 'warn', 'fail']),
  summary: z.string(),
});
export type QualityScore = z.infer<typeof QualityScoreSchema>;

export const ReviewReportSchema = z.object({
  chapter_number: z.number(),
  critical_issues: z.array(ReviewIssueSchema),
  major_issues: z.array(ReviewIssueSchema),
  minor_issues: z.array(ReviewIssueSchema),
  quality_score: QualityScoreSchema.nullable(),
  total_critical: z.number(),
  total_major: z.number(),
  total_minor: z.number(),
  overall_verdict: z.enum(['pass', 'warn', 'fail']),
  elapsed_seconds: z.number(),
  content_chars: z.number(),
  content_preview: z.string(),
  _idempotent_replay: z.boolean().optional(),
});
export type ReviewReport = z.infer<typeof ReviewReportSchema>;

// ============ Outlines ============

export const OutlineSchema = z.object({
  chapter: z.number(),
  filename: z.string(),
});
export type Outline = z.infer<typeof OutlineSchema>;

// ============ Audit ============

export const AuditEventSchema = z.object({
  event_type: z.string(),
  user_id: z.number().nullable().optional(),
  username: z.string().nullable().optional(),
  ip: z.string().optional(),
  success: z.boolean().optional(),
  detail: z.string().optional(),
  timestamp: z.string(),
});
export type AuditEvent = z.infer<typeof AuditEventSchema>;

export const AuditLogSchema = z.object({
  events: z.array(AuditEventSchema),
  count: z.number(),
});
export type AuditLog = z.infer<typeof AuditLogSchema>;

// ============ SSE Write Progress ============

export const WritePhaseSchema = z.enum([
  'init',
  'pre_write_check',
  'writing',
  'save',
  'extract',
  'merge',
  'post_write_check',
  'done',
]);
export type WritePhase = z.infer<typeof WritePhaseSchema>;

export const WriteStartedEventSchema = z.object({
  task_id: z.string().optional(),
  chapter: z.number(),
  skill: z.string().optional(),
  model: z.string().optional(),
  min_chars: z.number().optional(),
  project_root: z.string().optional(),
});

export const WriteChunkEventSchema = z.object({
  text: z.string(),
});

export const WriteProgressEventSchema = z.object({
  phase: WritePhaseSchema,
  message: z.string().optional(),
});

export const WriteDoneEventSchema = z.object({
  task_id: z.string().optional(),
  output_path: z.string().optional(),
  content_chars: z.number().optional(),
  resumed_from_chars: z.number().optional(),
  post_issue_count: z.number().optional(),
  pre_issue_count: z.number().optional(),
});

export const WriteCancelledEventSchema = z.object({
  task_id: z.string(),
  chapter: z.number(),
  partial_chars: z.number(),
  output_path: z.string(),
  preview: z.string().optional(),
  message: z.string().optional(),
});

export const WriteErrorEventSchema = z.object({
  message: z.string(),
  code: z.string().optional(),
});
