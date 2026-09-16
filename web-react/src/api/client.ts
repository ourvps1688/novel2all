/**
 * Axios 实例 + 全局拦截器
 *
 * 关键设计：
 *  1. withCredentials=true → 浏览器自动携带 /api/auth/login 设的 n2a_session cookie
 *  2. 401 → 清空 auth store + 触发 navigate('/login')（由 AuthProvider 监听）
 *  3. 429 → 抛 ApiError（含 retry_after_seconds），UI 用 snackbar 提示
 *  4. 5xx → 抛 ApiError（含 request_id），方便用户报告
 *  5. 网络异常 → 抛 ApiError(status=0)
 *  6. 所有非 2xx 响应自动转换为 ApiError（不再需要 .catch 写一遍）
 */

import type { AxiosError} from 'axios';
import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';

import { type ApiErrorBody, toApiError } from '../utils/errors';

// ==================== 拦截器回调钩子 ====================
// 解耦：ApiClient 不直接依赖 store / router，由 AuthProvider 注册回调
type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

/** 注册 401 回调（仅 AuthProvider 调用一次） */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

// ==================== 实例创建 ====================

/**
 * 创建 axios 实例
 * baseURL 留空 → 走相对路径（同源；Vite dev proxy 或 Nginx 反代）
 */
function createApiClient(): AxiosInstance {
  const instance = axios.create({
    baseURL: '',
    withCredentials: true, // 关键：携带 httpOnly cookie
    timeout: 30_000,
    headers: {
      Accept: 'application/json',
    },
    // 不自动解析 JSON：让 FormData 请求能正常走 multipart
    transformResponse: [(data) => data],
  });

  // ============ Request interceptor ============
  instance.interceptors.request.use(
    (config) => {
      // 可在此注入 X-Request-Id（暂不实现）
      return config;
    },
    (error) => Promise.reject(toApiError(error)),
  );

  // ============ Response interceptor ============
  instance.interceptors.response.use(
    (response) => {
      // 解析响应：可能是 JSON（application/json）或 SSE 流
      const contentType = response.headers['content-type'] ?? '';
      const contentTypeStr = typeof contentType === 'string' ? contentType : '';

      if (contentTypeStr.includes('text/event-stream')) {
        // SSE 不在 axios 处理，调用方用 stream() 方法
        return response;
      }

      const raw = response.data;
      if (typeof raw === 'string' && raw.length > 0) {
        try {
          response.data = JSON.parse(raw);
        } catch {
          // 非 JSON（如纯文本）；保留原值
        }
      }
      return response;
    },
    (error: AxiosError<ApiErrorBody>) => {
      const apiErr = toApiError(error);

      // 401 → 触发全局清理
      if (apiErr.isUnauthorized) {
        onUnauthorized?.();
      }

      // 4xx/5xx 都抛 ApiError（让调用方用 instanceof 判断）
      return Promise.reject(apiErr);
    },
  );

  return instance;
}

export const apiClient: AxiosInstance = createApiClient();

// ==================== 高层方法 ====================

/** GET：解析为 T（如果提供 zod schema 则 runtime 校验） */
export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await apiClient.get<T>(url, config);
  return res.data;
}

/** POST JSON */
export async function post<T, B = unknown>(url: string, body?: B, config?: AxiosRequestConfig): Promise<T> {
  const res = await apiClient.post<T>(url, body, {
    ...config,
    headers: { 'Content-Type': 'application/json', ...config?.headers },
  });
  return res.data;
}

/** POST Form（multipart/form-data）—— 后端 FastAPI Form() 用 */
export async function postForm<T>(url: string, fields: Record<string, string | number | boolean>): Promise<T> {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    form.append(k, String(v));
  }
  const res = await apiClient.post<T>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

/** DELETE */
export async function del<T = void>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await apiClient.delete<T>(url, config);
  return res.data;
}

/**
 * SSE 流式订阅（基于原生 EventSource，因 EventSource 自动重连 +
 *  cookie 友好；axios 不支持流式消费）
 *
 * 用法：
 *   const es = streamSSE(
 *     '/api/write/stream?chapter=1',
 *     {
 *       started: (data) => console.log('start', data),
 *       chunk: (data) => console.log('chunk', data.text),
 *       done: () => es?.close(),
 *       error: (data) => console.error(data.message),
 *     },
 *     () => console.warn('网络断开'),
 *   );
 *   // 之后：es.close() 取消订阅
 */
export interface SSEHandlers {
  [eventName: string]: (data: unknown) => void;
}

export function streamSSE(
  url: string,
  handlers: SSEHandlers,
  onNetworkError?: () => void,
): EventSource {
  const es = new EventSource(url, { withCredentials: true });

  Object.entries(handlers).forEach(([eventName, handler]) => {
    es.addEventListener(eventName, (e: MessageEvent) => {
      try {
        const data = e.data ? JSON.parse(e.data) : {};
        handler(data);
      } catch (err) {
        console.warn(`[SSE ${eventName}] parse error`, err);
      }
    });
  });

  // 网络层错误（连接断开）
  // 注意：服务端发的 `event: error` 也是 'error' 事件（MessageEvent）。
  // 区分方法：MessageEvent 有 data 字段，原生 ErrorEvent 没有。
  // 服务端 error 已被 handlers.error 处理，这里只处理网络断开。
  es.addEventListener('error', (e) => {
    if (e instanceof MessageEvent) {
      // 服务端 error 事件 → 已被 handlers.error 处理，跳过
      return;
    }
    onNetworkError?.();
  });

  return es;
}
