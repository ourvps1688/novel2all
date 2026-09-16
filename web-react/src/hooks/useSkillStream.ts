/**
 * useSkillStream: 通用 Skill SSE 流式消费 hook
 *
 * 关键能力 (playbook §4.2):
 *   - EventSource 封装 (axios 不支持 SSE)
 *   - 断线重连 3 次 (递增延迟: 1s, 2s, 4s)
 *   - 3 次后降级 polling GET /api/skills/:name/status 每 2s
 *   - 心跳: 30s 无消息 → 主动关闭重连 (后端 30s 内会发 keep-alive comment)
 *   - Cancel: 调用 POST /api/write/cancel/:taskId
 *
 * 适用场景：
 *   - /skills/:name 页面的 SkillRunner
 *   - 未来 short-write / review 等其它 SSE 通道 (后端 schema 不一致时按需扩展)
 */

import { useCallback, useRef } from 'react';
import axios from 'axios';

import type { ApiError } from '../utils/errors';
import type { SkillOutput } from '../types/skills';

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_DELAYS_MS = [1000, 2000, 4000];
const HEARTBEAT_TIMEOUT_MS = 30_000;
const POLLING_INTERVAL_MS = 2000;

export interface StreamOptions {
  taskId: string;
  skillName: string;
  onChunk?: (text: string) => void;
  onProgress?: (progress: {
    phase?: string;
    charsWritten: number;
    charsPerSecond?: number;
    etaSeconds?: number;
    message?: string;
  }) => void;
  onReconnect?: (attempts: number) => void;
  onError?: (err: ApiError | Error) => void;
  onDone?: (output: SkillOutput) => void;
}

export interface StreamControls {
  /** 启动流 (resolve 在 'done' 或 'error' 时; 也可能在 cancel 时) */
  stream: (opts: StreamOptions) => Promise<void>;
  /** 取消 (关闭 EventSource + 调后端 cancel) */
  cancel: (taskId: string) => Promise<void>;
}

/** 把任意错误转成 Error */
function toError(err: unknown): Error {
  if (err instanceof Error) return err;
  return new Error(String(err));
}

/**
 * useSkillStream: 返回 { stream, cancel } 控制函数
 *
 * 注意：所有内部 timer / EventSource / polling interval 都存在 ref 中，
 * 卸载 / cancel / 重新 stream 时正确清理，避免内存泄漏。
 *
 * 实现细节：用 useRef 存储 handleReconnect 引用, 规避 resetHeartbeat 与
 * handleReconnect 之间的循环依赖 (eslint react-hooks/exhaustive-deps)。
 */
export function useSkillStream(): StreamControls {
  const eventSourceRef = useRef<EventSource | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const currentOptsRef = useRef<StreamOptions | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const isCancelledRef = useRef(false);

  // 用 ref 持有 reconnect 函数, 避免循环依赖
  const reconnectFnRef = useRef<(opts: StreamOptions) => void>(() => {
    /* 默认空实现, startSSE 后被覆盖 */
  });

  /** 清理所有 timer / EventSource / polling */
  const cleanup = useCallback((): void => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (heartbeatTimerRef.current !== null) {
      clearTimeout(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (pollingTimerRef.current !== null) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  /** 启动心跳; HEARTBEAT_TIMEOUT_MS 内无消息则强制重连 */
  const resetHeartbeat = useCallback((opts: StreamOptions): void => {
    if (heartbeatTimerRef.current !== null) {
      clearTimeout(heartbeatTimerRef.current);
    }
    heartbeatTimerRef.current = window.setTimeout(() => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        reconnectFnRef.current(opts);
      }
    }, HEARTBEAT_TIMEOUT_MS);
  }, []);

  /** polling 降级 (3 次重连失败后) */
  const startPolling = useCallback(
    (opts: StreamOptions): void => {
      if (pollingTimerRef.current !== null) {
        clearInterval(pollingTimerRef.current);
      }
      pollingTimerRef.current = window.setInterval(async () => {
        if (isCancelledRef.current) return;
        try {
          const resp = await axios.get<Record<string, unknown>>(
            `/api/skills/${encodeURIComponent(opts.skillName)}/status`,
            { params: { task_id: opts.taskId } },
          );
          const data = resp.data ?? {};
          if (typeof data.chunk === 'string') {
            opts.onChunk?.(data.chunk);
          }
          if (typeof data.progress === 'object' && data.progress !== null) {
            const p = data.progress as Record<string, unknown>;
            opts.onProgress?.({
              phase: typeof p.phase === 'string' ? p.phase : undefined,
              charsWritten: typeof p.chars_written === 'number' ? p.chars_written : 0,
            });
          }
          if (data.status === 'done') {
            cleanup();
            opts.onDone?.({
              text: typeof data.output === 'string' ? data.output : '',
              chunks: [],
              durationMs: 0,
              taskId: opts.taskId,
              metadata: data,
            });
          } else if (data.status === 'failed' || data.status === 'cancelled') {
            cleanup();
            opts.onError?.(new Error(`Task ${String(data.status)}`));
          }
        } catch {
          // polling 失败不阻塞 UI, 下个周期重试
        }
      }, POLLING_INTERVAL_MS);
    },
    [cleanup],
  );

  /** 启动 EventSource (重连入口) */
  const startSSE = useCallback(
    (opts: StreamOptions): void => {
      cleanup();
      const url = `/api/skills/${encodeURIComponent(opts.skillName)}/status?task_id=${encodeURIComponent(opts.taskId)}`;
      const es = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = es;
      currentOptsRef.current = opts;

      // chunk 事件
      es.addEventListener('chunk', (e: Event) => {
        try {
          const me = e as MessageEvent;
          const data = me.data ? (JSON.parse(me.data) as { text?: string }) : {};
          if (typeof data.text === 'string') {
            opts.onChunk?.(data.text);
          }
          resetHeartbeat(opts);
        } catch (err) {
          opts.onError?.(toError(err));
        }
      });

      // progress 事件
      es.addEventListener('progress', (e: Event) => {
        try {
          const me = e as MessageEvent;
          const data = me.data ? (JSON.parse(me.data) as Record<string, unknown>) : {};
          opts.onProgress?.({
            phase: typeof data.phase === 'string' ? data.phase : undefined,
            charsWritten: typeof data.chars_written === 'number' ? data.chars_written : 0,
            charsPerSecond:
              typeof data.chars_per_second === 'number' ? data.chars_per_second : undefined,
            etaSeconds: typeof data.eta_seconds === 'number' ? data.eta_seconds : undefined,
            message: typeof data.message === 'string' ? data.message : undefined,
          });
          resetHeartbeat(opts);
        } catch {
          // 忽略 progress 解析错误 (不致命)
        }
      });

      // done 事件
      es.addEventListener('done', (e: Event) => {
        try {
          const me = e as MessageEvent;
          const data = me.data ? (JSON.parse(me.data) as Record<string, unknown>) : {};
          cleanup();
          opts.onDone?.({
            text: '',
            chunks: [],
            durationMs: typeof data.elapsed_ms === 'number' ? data.elapsed_ms : 0,
            taskId: opts.taskId,
            metadata: data,
          });
        } catch (err) {
          opts.onError?.(toError(err));
        }
      });

      // error 事件: 服务端 error event (有 data) 或网络断开 (无 data)
      es.addEventListener('error', (e: Event) => {
        const me = e as MessageEvent;
        if (me && typeof me.data === 'string' && me.data.length > 0) {
          try {
            const data = JSON.parse(me.data) as { message?: string };
            cleanup();
            opts.onError?.(new Error(data.message ?? 'Skill error'));
            return;
          } catch {
            // fallthrough 视为网络错误
          }
        }
        // 网络断开 → 重连或降级
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
        reconnectFnRef.current(opts);
      });

      // cancelled 事件 (后端主动取消)
      es.addEventListener('cancelled', (e: Event) => {
        try {
          const me = e as MessageEvent;
          const data = me.data ? (JSON.parse(me.data) as { message?: string }) : {};
          cleanup();
          opts.onError?.(new Error(data.message ?? 'Cancelled by user'));
        } catch {
          cleanup();
          opts.onError?.(new Error('Cancelled'));
        }
      });

      resetHeartbeat(opts);
    },
    [cleanup, resetHeartbeat],
  );

  // 把真正的重连函数挂到 ref
  reconnectFnRef.current = (opts: StreamOptions): void => {
    if (isCancelledRef.current) return;
    if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
      // 降级 polling
      opts.onReconnect?.(reconnectAttemptsRef.current);
      startPolling(opts);
      return;
    }
    const delay = RECONNECT_DELAYS_MS[reconnectAttemptsRef.current] ?? 4000;
    reconnectAttemptsRef.current += 1;
    opts.onReconnect?.(reconnectAttemptsRef.current);
    window.setTimeout(() => {
      if (!isCancelledRef.current) {
        startSSE(opts);
      }
    }, delay);
  };

  /** 公开: 启动流 */
  const stream = useCallback(
    async (opts: StreamOptions): Promise<void> => {
      isCancelledRef.current = false;
      reconnectAttemptsRef.current = 0;
      currentOptsRef.current = opts;
      startSSE(opts);
      // 不在 promise 上 resolve; 由 onDone / onError 处理
    },
    [startSSE],
  );

  /** 公开: 取消 */
  const cancel = useCallback(
    async (taskId: string): Promise<void> => {
      isCancelledRef.current = true;
      cleanup();
      try {
        await axios.post(`/api/write/cancel/${encodeURIComponent(taskId)}`);
      } catch {
        // cancel 失败不抛 (用户已主动操作)
      }
    },
    [cleanup],
  );

  return { stream, cancel };
}