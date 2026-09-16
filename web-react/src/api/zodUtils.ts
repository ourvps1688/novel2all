/**
 * Zod 解析工具（避免在 hooks 文件里重复定义）
 */

import type { ZodError } from 'zod';

/** 把 ZodError 格式化为单行 message（用于 snackbar） */
export function formatZodError(err: ZodError): string {
  return err.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
}
