/**
 * 错误类型 + 解析工具
 *
 * 后端统一错误格式（FastAPI HTTPException）：
 *   { detail: string | { ... }, request_id?: string }
 *
 * 特殊情况：
 *   401 → 未登录 / cookie 失效
 *   403 → 权限不足
 *   404 → 资源不存在
 *   422 → 表单校验失败
 *   429 → LLM 速率限制（含 retry_after_seconds）
 *   500 → 服务器异常（含 request_id）
 */

import { AxiosError } from 'axios';

export interface ApiErrorBody {
  detail: string | Record<string, unknown>;
  request_id?: string;
  /** LLM rate limit 专属字段（V1.0.2 B4） */
  user_id?: number;
  used?: number;
  limit?: number;
  retry_after_seconds?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | undefined;
  readonly requestId: string | undefined;

  constructor(status: number, message: string, body?: ApiErrorBody, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.requestId = requestId;
  }

  /** 是否为鉴权失效（需要清空 store + 跳转 /login） */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** 是否为权限不足 */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** 是否为 LLM 速率限制 */
  get isRateLimited(): boolean {
    return this.status === 429;
  }

  /** 用户友好的展示信息（snackbar 用） */
  get userMessage(): string {
    if (this.isRateLimited && this.body?.retry_after_seconds) {
      const mins = Math.ceil(this.body.retry_after_seconds / 60);
      return `LLM 配额已满，约 ${mins} 分钟后恢复`;
    }
    if (this.isUnauthorized) return '登录已失效，请重新登录';
    if (this.isForbidden) return '权限不足';
    if (this.status === 404) return '资源不存在';
    if (this.status >= 500) {
      const rid = this.requestId ? `（请求ID: ${this.requestId}）` : '';
      return `服务器异常${rid}`;
    }
    return this.message;
  }
}

/**
 * 从 axios error 解析为 ApiError
 * 调用方收到 ApiError 后可根据 status 决定下一步动作
 */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof AxiosError) {
    const status = err.response?.status ?? 0;
    const data = err.response?.data as ApiErrorBody | undefined;
    const requestId = (err.response?.headers?.['x-request-id'] as string | undefined) ?? data?.request_id;

    // 解析 detail：可能是 string 或对象
    let message: string;
    if (typeof data?.detail === 'string') {
      message = data.detail;
    } else if (data && typeof data.detail === 'object') {
      message = JSON.stringify(data.detail);
    } else if (err.message) {
      message = err.message;
    } else {
      message = '网络异常';
    }

    // 网络层错误（status === 0）
    if (status === 0) {
      return new ApiError(0, '网络异常，请检查后端服务', data, requestId);
    }

    return new ApiError(status, message, data, requestId);
  }
  if (err instanceof Error) {
    return new ApiError(0, err.message || '未知错误');
  }
  return new ApiError(0, '未知错误');
}
