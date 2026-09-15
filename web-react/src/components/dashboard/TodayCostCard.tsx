/**
 * TodayCostCard：今日节省
 *
 * 数据源：/api/cache/prompt-stats (cost_saved_cny + potential_savings_cny)
 */

import {
  Card,
  CardContent,
  Typography,
  Stack,
  Box,
  Skeleton,
  Divider,
} from '@mui/material';
import SavingsIcon from '@mui/icons-material/Savings';

import { usePromptCacheStats } from '../../api/cache';
import { formatNumber } from '../../utils/format';

export function TodayCostCard() {
  const { data: stats, isLoading } = usePromptCacheStats();

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="text" width="80%" height={48} sx={{ my: 2 }} />
          <Skeleton variant="text" width="60%" />
        </CardContent>
      </Card>
    );
  }

  const saved = stats?.cost_saved_cny ?? 0;
  const potential = stats?.potential_savings_cny ?? 0;
  const prefixHits = stats?.prefix_hits ?? 0;
  const total = (stats?.prefix_hits ?? 0) + (stats?.prefix_misses ?? 0);
  const efficiency = total > 0 ? prefixHits / total : 0;

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <SavingsIcon color="success" />
            <Typography variant="h6">今日节省</Typography>
          </Stack>

          <Box>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              已节省（cache 命中）
            </Typography>
            <Typography variant="h3" color="success.main" sx={{ fontWeight: 700 }}>
              ¥{formatNumber(saved)}
            </Typography>
          </Box>

          <Divider />

          <Stack direction="row" justifyContent="space-between">
            <Box>
              <Typography variant="caption" color="text.secondary">
                潜在节省
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                ¥{formatNumber(potential)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                利用率
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {(efficiency * 100).toFixed(1)}%
              </Typography>
            </Box>
          </Stack>

          <Typography variant="caption" color="text.secondary">
            数据来自 <code>/api/cache/prompt-stats</code>
            {stats?.model
              ? ` · 平均 ${formatNumber(stats.model.avg_input_tokens_per_call)} tokens/call`
              : ''}
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}
