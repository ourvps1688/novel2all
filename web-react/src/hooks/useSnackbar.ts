/**
 * useSnackbar：暴露便捷的 show 方法
 */

import { useSnackbarStore } from '../store/snackbarStore';

export function useSnackbar() {
  const show = useSnackbarStore((s) => s.show);

  return {
    show,
    success: (msg: string, duration?: number) => show(msg, 'success', duration),
    info: (msg: string, duration?: number) => show(msg, 'info', duration),
    warning: (msg: string, duration?: number) => show(msg, 'warning', duration),
    error: (msg: string, duration?: number) => show(msg, 'error', duration),
  };
}
