/**
 * UUID v4 生成（idempotency key / task id）
 */

import { v4 as uuidv4 } from 'uuid';

/**
 * 生成新的 idempotency key（每次 mutate 都新生成，确保同 key 仅触发一次 LLM 调用）
 */
export function newIdempotencyKey(): string {
  return uuidv4();
}

/**
 * 短 ID（用于 task_id / 调试；与后端 uuid4().hex[:8] 对齐）
 */
export function shortId(): string {
  return uuidv4().replace(/-/g, '').slice(0, 8);
}
