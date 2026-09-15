/**
 * SnackbarProvider：消费 snackbarStore 的队列，展示全局提示
 *
 * 放置在 AuthProvider 内层（保证已登录后才显示）
 */

import { Alert, Snackbar } from '@mui/material';
import type { ReactNode } from 'react';

import { useSnackbarStore } from '../../store/snackbarStore';

interface Props {
  children: ReactNode;
}

export function SnackbarProvider({ children }: Props) {
  const current = useSnackbarStore((s) => s.current);
  const dismiss = useSnackbarStore((s) => s.dismiss);

  return (
    <>
      {children}
      <Snackbar
        key={current?.id ?? 'none'}
        open={current != null}
        autoHideDuration={current?.duration ?? 4000}
        onClose={(_e, reason) => {
          if (reason === 'clickaway') return;
          dismiss();
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {current ? (
          <Alert
            onClose={dismiss}
            severity={current.severity}
            variant="filled"
            sx={{ width: '100%', maxWidth: 480 }}
          >
            {current.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </>
  );
}
