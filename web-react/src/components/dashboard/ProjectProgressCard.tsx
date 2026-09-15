/**
 * ProjectProgressCard：项目进度（已写 X / N）
 */

import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  Typography,
  Stack,
  Box,
  Skeleton,
  LinearProgress,
  Button,
} from '@mui/material';
import TimelineIcon from '@mui/icons-material/Timeline';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

import { useChapters } from '../../api/chapters';
import { useProjectStatus } from '../../api/projects';
import { formatNumber } from '../../utils/format';

const COLORS = ['#1976d2', '#9c27b0', '#2e7d32', '#ed6c02'];

export function ProjectProgressCard() {
  const navigate = useNavigate();
  const { data: status, isLoading: statusLoading } = useProjectStatus();
  const { data: chapters, isLoading: chaptersLoading } = useChapters();

  if (statusLoading || chaptersLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="circular" width={120} height={120} sx={{ mx: 'auto', my: 2 }} />
        </CardContent>
      </Card>
    );
  }

  if (!status?.initialized) {
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Stack spacing={2} alignItems="center" justifyContent="center" sx={{ minHeight: 200 }}>
            <TimelineIcon sx={{ fontSize: 48 }} color="disabled" />
            <Typography variant="body2" color="text.secondary" align="center">
              项目未初始化
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  const target = status.total_chapters_target ?? 0;
  const written = chapters?.length ?? 0;
  const pct = target > 0 ? Math.min(100, (written / target) * 100) : 0;

  // 状态分布（按字数分桶示意）
  const list = chapters ?? [];
  const shortCount = list.filter((c) => c.char_count < 2000).length;
  const mediumCount = list.filter((c) => c.char_count >= 2000 && c.char_count < 4000).length;
  const longCount = list.filter((c) => c.char_count >= 4000).length;

  const pieData = [
    { name: '<2000 字', value: shortCount },
    { name: '2000-4000', value: mediumCount },
    { name: '≥4000 字', value: longCount },
  ].filter((d) => d.value > 0);

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <TimelineIcon color="primary" />
            <Typography variant="h6">项目进度</Typography>
          </Stack>

          <Box>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {status.project_name ?? '未命名项目'}
              </Typography>
              <Typography variant="body2">
                <strong>{written}</strong> / {target || '—'} 章
              </Typography>
            </Stack>
            <LinearProgress variant="determinate" value={pct} sx={{ height: 8, borderRadius: 4 }} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              {pct.toFixed(1)}% 完成
            </Typography>
          </Box>

          {pieData.length > 0 && (
            <Box sx={{ height: 140 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={35}
                    outerRadius={55}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => `${v} 章`} />
                </PieChart>
              </ResponsiveContainer>
            </Box>
          )}

          <Stack direction="row" spacing={2}>
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                角色
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {formatNumber(status.character_count)}
              </Typography>
            </Box>
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                活跃伏笔
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {formatNumber(status.active_foreshadowing_count)}
              </Typography>
            </Box>
            <Box flex={1}>
              <Typography variant="caption" color="text.secondary">
                时间线条目
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {formatNumber(status.timeline_count)}
              </Typography>
            </Box>
          </Stack>

          <Button variant="outlined" onClick={() => navigate('/chapters')} size="small">
            查看全部章节
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
