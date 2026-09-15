/**
 * CacheStatusCard：缓存命中率 + 大小
 */

import {
  Card,
  CardContent,
  Typography,
  Stack,
  Box,
  Skeleton,
  LinearProgress,
  Chip,
} from '@mui/material';
import StorageIcon from '@mui/icons-material/Storage';

import { useCacheStats } from '../../api/cache';
import { formatBytes, formatNumber, formatPercent } from '../../utils/format';

export function CacheStatusCard() {
  const { data: stats, isLoading } = useCacheStats();

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="rectangular" height={80} sx={{ my: 2 }} />
          <Skeleton variant="text" width="60%" />
        </CardContent>
      </Card>
    );
  }

  const hitRate = stats?.hit_rate ?? 0;
  const hits = stats?.hits ?? 0;
  const misses = stats?.misses ?? 0;
  const size = stats?.size ?? 0;
  const maxSize = stats?.max_size ?? 1;
  const usage = maxSize > 0 ? Math.min(100, (size / maxSize) * 100) : 0;
  const prefixRate = stats?.prompt_prefix?.hit_rate ?? 0;

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <StorageIcon color="primary" />
            <Typography variant="h6">Cache 状态</Typography>
            <Box flex={1} />
            <Chip size="small" label={stats?.backend ?? 'unknown'} variant="outlined" />
          </Stack>

          <Box>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                命中率
              </Typography>
              <Typography variant="h5" color={hitRate > 0.5 ? 'success.main' : 'warning.main'}>
                {(hitRate * 100).toFixed(1)}%
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={hitRate * 100}
              sx={{ height: 8, borderRadius: 4 }}
              color={hitRate > 0.5 ? 'success' : 'warning'}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              {formatNumber(hits)} 命中 / {formatNumber(hits + misses)} 总请求
            </Typography>
          </Box>

          <Box>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                占用
              </Typography>
              <Typography variant="body2">
                {formatBytes(size)} / {formatBytes(maxSize)}
              </Typography>
            </Stack>
            <LinearProgress variant="determinate" value={usage} sx={{ height: 6, borderRadius: 3 }} />
          </Box>

          {prefixRate > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Prompt prefix 命中率
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {(prefixRate * 100).toFixed(1)}%
              </Typography>
            </Box>
          )}

          <Typography variant="caption" color="text.secondary">
            数据来自{' '}
            <code>/api/cache/stats</code> · {formatPercent(hits, hits + misses)} 命中
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}
