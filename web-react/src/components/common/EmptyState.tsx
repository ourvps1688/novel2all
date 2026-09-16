/**
 * EmptyState: 通用空状态组件
 *
 * 用法：
 *   <EmptyState
 *     icon={<InboxIcon />}
 *     title="暂无数据"
 *     subtitle="开始你的第一个 skill"
 *     action={{ label: '去试试', onClick: () => navigate('/skills') }}
 *   />
 */

import type { ReactNode } from 'react';
import { Box, Card, CardContent, Stack, Typography, Button } from '@mui/material';
import InboxIcon from '@mui/icons-material/Inbox';

export interface EmptyStateAction {
  label: string;
  onClick: () => void;
  variant?: 'text' | 'outlined' | 'contained';
}

export interface EmptyStateProps {
  /** 顶部图标 (默认 InboxIcon) */
  icon?: ReactNode;
  /** 主标题 */
  title: string;
  /** 副标题 (可选, 支持换行) */
  subtitle?: string;
  /** CTA 按钮 (可选) */
  action?: EmptyStateAction;
  /** 是否嵌入 Card 内 (默认 true) */
  boxed?: boolean;
  /** 自定义高度 (默认 320) */
  minHeight?: number;
}

export function EmptyState({
  icon,
  title,
  subtitle,
  action,
  boxed = true,
  minHeight = 320,
}: EmptyStateProps) {
  const body = (
    <Stack
      spacing={2}
      alignItems="center"
      justifyContent="center"
      sx={{
        minHeight,
        py: 4,
        px: 3,
        textAlign: 'center',
      }}
      role="status"
      aria-label={`空状态: ${title}`}
    >
      <Box sx={{ color: (t) => t.palette.text.disabled, '& svg': { fontSize: 64 } }}>
        {icon ?? <InboxIcon />}
      </Box>
      <Typography variant="h6" color="text.secondary">
        {title}
      </Typography>
      {subtitle && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
          {subtitle}
        </Typography>
      )}
      {action && (
        <Button
          variant={action.variant ?? 'contained'}
          onClick={action.onClick}
          sx={{ mt: 1 }}
        >
          {action.label}
        </Button>
      )}
    </Stack>
  );

  if (!boxed) return body;

  return (
    <Card variant="outlined">
      <CardContent>{body}</CardContent>
    </Card>
  );
}