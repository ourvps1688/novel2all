/**
 * useSSE：封装 EventSource，处理流式写作
 *
 * 用法：
 *   const { progress, streaming, start, stop } = useWriteStream();
 *
 *   start({ chapter: 5, model: 'deepseek-chat', minChars: 2000, projectRoot: '.' });
 *
 *   // progress: { phase: 'writing', charsWritten: 1234, ... } 实时更新
 *   // done / error / cancelled 后自动 stop
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { streamSSE } from '../api/client';
import type { WritePhase } from '../api/types';

export interface WriteProgressState {
  phase: WritePhase | 'idle' | 'cancelled' | 'error';
  charsWritten: number;
  charsPerSecond?: number;
  etaSeconds?: number;
  taskId?: string;
  message?: string;
  outputPath?: string;
  /** 错误信息 */
  errorMessage?: string;
  /** 错误码（如 'outline_not_found'） */
  errorCode?: string;
}

export interface StreamStartOptions {
  chapter: number;
  /** 模型名（V1.5 P2：当前 GET 版 SSE 端点不支持，传给后端会被忽略）
   *  模型由后端 AdaptiveRouter 自动选择（V0.30.6 C3） */
  model?: string;
  minChars: number;
  projectRoot: string;
  skill?: string;
  skipPreWrite?: boolean;
  resumeFromChars?: number;
}

interface UseWriteStreamResult {
  progress: WriteProgressState;
  streaming: boolean;
  /** 累积的写入文本（用于实时展示） */
  accumulated: string;
  start: (options: StreamStartOptions) => void;
  stop: () => void;
}

const INITIAL_PROGRESS: WriteProgressState = {
  phase: 'idle',
  charsWritten: 0,
};

/**
 * 计算字符数（中文按字符；避免字节错位）
 */
function countChars(s: string): number {
  return [...s].length;
}

/**
 * 估计字/秒（最近 5s 滑窗）
 */
function calcRate(history: { ts: number; chars: number }[]): number {
  if (history.length < 2) return 0;
  const first = history[0]!;
  const last = history[history.length - 1]!;
  const dt = (last.ts - first.ts) / 1000;
  if (dt <= 0) return 0;
  return (last.chars - first.chars) / dt;
}

export function useWriteStream(): UseWriteStreamResult {
  const [progress, setProgress] = useState<WriteProgressState>(INITIAL_PROGRESS);
  const [streaming, setStreaming] = useState(false);
  const [accumulated, setAccumulated] = useState('');

  const esRef = useRef<EventSource | null>(null);
  const startTimeRef = useRef<number>(0);
  const lastChunkTimeRef = useRef<number>(0);
  const charHistoryRef = useRef<{ ts: number; chars: number }[]>([]);
  const minCharsRef = useRef<number>(0);

  const stop = useCallback((): void => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStreaming(false);
  }, []);

  const start = useCallback(
    (options: StreamStartOptions): void => {
      // 先关掉旧的
      stop();

      // 初始化状态
      setProgress({ phase: 'init', charsWritten: 0 });
      setAccumulated('');
      setStreaming(true);
      startTimeRef.current = Date.now();
      lastChunkTimeRef.current = Date.now();
      charHistoryRef.current = [];
      minCharsRef.current = options.minChars;

      const params = new URLSearchParams({
        chapter: String(options.chapter),
        min_chars: String(options.minChars),
        project_root: options.projectRoot,
      });
      if (options.skill) params.set('skill', options.skill);
      if (options.skipPreWrite) params.set('skip_pre_write', 'true');
      if (options.resumeFromChars) params.set('resume_from_chars', String(options.resumeFromChars));
      // 注：model 参数由后端 AdaptiveRouter 自动选择（V0.30.6 C3），不在 GET 版 SSE 端点暴露

      // SSE 走 GET（/api/write/stream，app.py:2151），用 EventSource 而非 fetch
      // 注：EventSource 仅支持 GET；如需 Form 改用 fetch + ReadableStream（见 fetchSSE）
      // 注 2：GET 版的 started 事件不包含 task_id（V1.5 P2 取消 pipeline 功能前不实现）
      const url = `/api/write/stream?${params.toString()}`;
      const es = streamSSE(
        url,
        {
          started: (data) => {
            const d = data as { task_id?: string; chapter?: number };
            setProgress((p) => ({
              ...p,
              phase: 'init',
              taskId: d.task_id,
            }));
          },
          pre_write_check: (data) => {
            const d = data as { issues?: unknown[] };
            setProgress((p) => ({
              ...p,
              phase: 'pre_write_check',
              message: d.issues && d.issues.length > 0 ? `发现 ${d.issues.length} 个 pre-write 问题` : 'pre-write 检查通过',
            }));
          },
          chunk: (data) => {
            const d = data as { text: string };
            lastChunkTimeRef.current = Date.now();
            setAccumulated((cur) => {
              const next = cur + d.text;
              const chars = countChars(next);
              // 更新速率历史（保留最近 5s）
              charHistoryRef.current.push({ ts: Date.now(), chars });
              const cutoff = Date.now() - 5000;
              charHistoryRef.current = charHistoryRef.current.filter((h) => h.ts >= cutoff);
              const rate = calcRate(charHistoryRef.current);
              const remaining = Math.max(0, minCharsRef.current - chars);
              const eta = rate > 0 ? remaining / rate : undefined;
              setProgress((p) => ({
                ...p,
                phase: 'writing',
                charsWritten: chars,
                charsPerSecond: rate,
                etaSeconds: eta,
              }));
              return next;
            });
          },
          progress: (data) => {
            const d = data as { phase: WritePhase; message?: string };
            setProgress((p) => ({
              ...p,
              phase: d.phase,
              message: d.message ?? p.message,
            }));
          },
          post_write_check: (data) => {
            const d = data as { issues?: unknown[] };
            setProgress((p) => ({
              ...p,
              phase: 'post_write_check',
              message: d.issues && d.issues.length > 0 ? `发现 ${d.issues.length} 个 post-write 问题` : 'post-write 检查通过',
            }));
          },
          done: (data) => {
            const d = data as { output_path?: string; content_chars?: number };
            setProgress((p) => ({
              ...p,
              phase: 'done',
              charsWritten: d.content_chars ?? p.charsWritten,
              outputPath: d.output_path,
            }));
            stop();
          },
          cancelled: (data) => {
            const d = data as { partial_chars?: number; message?: string };
            setProgress((p) => ({
              ...p,
              phase: 'cancelled',
              charsWritten: d.partial_chars ?? p.charsWritten,
              message: d.message,
            }));
            stop();
          },
          error: (data) => {
            const d = data as { message: string; code?: string };
            setProgress((p) => ({
              ...p,
              phase: 'error',
              errorMessage: d.message,
              errorCode: d.code,
            }));
            stop();
          },
        },
        () => {
          // 网络断开
          setProgress((p) => ({
            ...p,
            phase: 'error',
            errorMessage: 'SSE 连接断开，请检查网络',
          }));
          stop();
        },
      );

      esRef.current = es;
    },
    [stop],
  );

  // 卸载时关闭
  useEffect(() => {
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  return { progress, streaming, accumulated, start, stop };
}
