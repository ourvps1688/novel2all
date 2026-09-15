/**
 * LoadingButton：带 loading 状态的 Button 包装
 * 用法：<LoadingButton loading={isPending} onClick={...}>提交</LoadingButton>
 */

import { Button, type ButtonProps, CircularProgress } from '@mui/material';

export interface LoadingButtonProps extends ButtonProps {
  loading?: boolean;
}

export function LoadingButton({ loading, disabled, children, startIcon, ...rest }: LoadingButtonProps) {
  return (
    <Button
      {...rest}
      disabled={disabled || loading}
      startIcon={loading ? <CircularProgress size={16} color="inherit" /> : startIcon}
    >
      {children}
    </Button>
  );
}
