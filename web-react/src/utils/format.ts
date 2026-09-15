/**
 * 格式化工具函数
 */

/** 数字加千分位 */
export function formatNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('zh-CN');
}

/** 百分比（保留 1 位小数） */
export function formatPercent(value: number | null | undefined, total: number | null | undefined): string {
  if (value == null || total == null || total === 0) return '0.0%';
  return `${((value / total) * 100).toFixed(1)}%`;
}

/** 字节大小（KB / MB / GB） */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** 时长（秒 → "Xm Ys"） */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

/** 时间戳 → "YYYY-MM-DD HH:mm"（Asia/Shanghai） */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

/** 截断字符串（中文按 1 字符算） */
export function truncate(s: string | null | undefined, max: number): string {
  if (!s) return '';
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

/** "第 N 章" 格式化 */
export function formatChapter(n: number | null | undefined): string {
  if (n == null) return '—';
  return `第 ${n} 章`;
}
