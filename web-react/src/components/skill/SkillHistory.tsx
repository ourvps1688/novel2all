/**
 * SkillHistory: 最近执行记录列表
 *
 * 显示最近 N 条 (默认 5), 每条包含：
 *   - 时间
 *   - 状态 (success/error/cancelled)
 *   - 时长
 *   - 输入/输出预览
 *
 * 折叠态: 用 MUI Accordion (S1 简化: 仅展示, 不展开详情)
 */

import {
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import BlockIcon from '@mui/icons-material/Block';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';

import { useState } from 'react';

import { useSkillExecutionStore } from '../../store/skillExecutionStore';
import type { SkillExecutionHistoryEntry, SkillExecutionPhase } from '../../types/skills';
import { formatDuration, formatTimestamp } from '../../utils/format';

export interface SkillHistoryProps {
  skillName: string;
  /** 默认折叠 */
  defaultCollapsed?: boolean;
  /** 最多展示条数 (默认 5) */
  limit?: number;
}

const STATUS_ICON: Record<SkillExecutionPhase, React.ReactNode> = {
  idle: <HourglassEmptyIcon fontSize="small" color="disabled" />,
  preparing: <HourglassEmptyIcon fontSize="small" color="disabled" />,
  running: <HourglassEmptyIcon fontSize="small" color="primary" />,
  success: <CheckCircleIcon fontSize="small" color="success" />,
  error: <ErrorOutlineIcon fontSize="small" color="error" />,
  cancelled: <BlockIcon fontSize="small" color="warning" />,
};

const STATUS_LABEL: Record<SkillExecutionPhase, string> = {
  idle: '空闲',
  preparing: '准备中',
  running: '运行中',
  success: '成功',
  error: '失败',
  cancelled: '已取消',
};

export function SkillHistory({ skillName, defaultCollapsed = true, limit = 5 }: SkillHistoryProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const list = useSkillExecutionStore((s) => s.history[skillName] ?? []).slice(0, limit);

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2">最近执行 (最多 {limit} 条)</Typography>
          <IconButton size="small" onClick={() => setCollapsed((v) => !v)} aria-label={collapsed ? '展开历史' : '折叠历史'}>
            {collapsed ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
          </IconButton>
        </Stack>
        <Collapse in={!collapsed}>
          {list.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
              暂无执行记录
            </Typography>
          ) : (
            <Stack spacing={1}>
              {list.map((entry) => (
                <HistoryRow key={entry.taskId} entry={entry} />
              ))}
            </Stack>
          )}
        </Collapse>
      </CardContent>
    </Card>
  );
}

function HistoryRow({ entry }: { entry: SkillExecutionHistoryEntry }) {
  return (
    <Box
      sx={{
        p: 1.25,
        borderRadius: 1,
        bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.50' : 'grey.900'),
        border: 1,
        borderColor: 'divider',
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          {STATUS_ICON[entry.status]}
          <Typography variant="body2" fontWeight={500}>
            {STATUS_LABEL[entry.status]}
          </Typography>
          <Chip size="small" label={formatDuration(entry.durationMs / 1000)} variant="outlined" />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {formatTimestamp(new Date(entry.startedAt).toISOString())}
        </Typography>
      </Stack>
      {entry.inputPreview && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
          输入: {entry.inputPreview}
        </Typography>
      )}
      {entry.outputPreview && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: 'block',
            mt: 0.25,
            whiteSpace: 'pre-wrap',
            maxHeight: 60,
            overflow: 'hidden',
          }}
        >
          输出: {entry.outputPreview}
        </Typography>
      )}
    </Box>
  );
}