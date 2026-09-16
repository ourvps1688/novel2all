/**
 * LoadingSkeleton: 通用 loading 占位
 *
 * 提供 3 种预设 variant：
 *   - SkillGridSkeleton (3x4 网格占位)
 *   - SkillDetailSkeleton (输入区 + 输出区)
 *   - PageHeaderSkeleton (标题 + 描述)
 *
 * 也可单独使用 <MuiSkeleton variant=...> 配合 sx
 */

import { Box, Card, CardContent, Grid, Skeleton, Stack } from '@mui/material';

export interface LoadingSkeletonProps {
  /** 渲染 variant */
  variant?: 'skillGrid' | 'skillDetail' | 'pageHeader' | 'card';
  /** 卡片数量 (仅 skillGrid / card 生效; 默认 8) */
  count?: number;
}

export function LoadingSkeleton({ variant = 'card', count = 8 }: LoadingSkeletonProps) {
  if (variant === 'skillGrid') {
    return (
      <Grid container spacing={2}>
        {Array.from({ length: count }).map((_, i) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={i}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Skeleton variant="circular" width={36} height={36} />
                    <Skeleton variant="text" sx={{ flexGrow: 1, fontSize: '1.25rem' }} />
                  </Stack>
                  <Skeleton variant="text" />
                  <Skeleton variant="text" width="60%" />
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  }

  if (variant === 'skillDetail') {
    return (
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Skeleton variant="text" sx={{ fontSize: '2rem', width: '40%' }} />
            <Skeleton variant="rectangular" height={120} />
            <Skeleton variant="rectangular" height={240} />
          </Stack>
        </CardContent>
      </Card>
    );
  }

  if (variant === 'pageHeader') {
    return (
      <Stack spacing={1} sx={{ mb: 3 }}>
        <Skeleton variant="text" sx={{ fontSize: '2.5rem', width: 240 }} />
        <Skeleton variant="text" width="60%" />
      </Stack>
    );
  }

  // 默认 card
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Skeleton variant="text" sx={{ fontSize: '1.5rem', width: '50%' }} />
          <Skeleton variant="text" />
          <Skeleton variant="text" width="80%" />
          <Box sx={{ pt: 1 }}>
            <Skeleton variant="rectangular" height={36} width={120} />
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

/** 单个 card 行 (供 skillCard loading state 使用) */
export function SkillCardSkeleton() {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Skeleton variant="circular" width={36} height={36} />
            <Skeleton variant="text" sx={{ flexGrow: 1, fontSize: '1.1rem' }} />
          </Stack>
          <Skeleton variant="text" />
          <Skeleton variant="text" width="65%" />
        </Stack>
      </CardContent>
    </Card>
  );
}