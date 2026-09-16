/**
 * WriteProgress: 8 阶段写作进度条 (Sprint 2)
 *
 * 8 阶段 (与后端 pipeline.write_chapter 一致):
 *   init → pre_write_check → writing → save → extract → merge → post_write_check → done
 *
 * 设计:
 *   - 显示当前阶段 + 阶段 Chip 链
 *   - 实时显示已写字数 / 字/秒 / 预计剩余秒数
 *   - 失败 / 取消状态独立显示
 */

import { Box, Stack, Chip, Typography, LinearProgress, Alert, CircularProgress } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';

import {
  PHASE_LABELS,
  PHASE_WEIGHTS,
  type WriteProgressView,
} from '../../types/chapters';
import type { WritePhase } from '../../api/types';

const PHASE_ORDER: WritePhase[] = [
  'init',
  'pre_write_check',
  'writing',
  'save',
  'extract',
  'merge',
  'post_write_check',
  'done',
];

export interface WriteProgressProps {
  /** 当前进度 (null = idle) */
  progress: WriteProgressView | null;
  /** 详细模式 (显示 字/秒 / ETA) */
  detailed?: boolean;
  /** 阶段点击回调 */
  onPhaseClick?: (phase: WritePhase) => void;
}

export function WriteProgress({ progress, detailed = false, onPhaseClick }: WriteProgressProps) {
  // idle 状态: 不显示
  if (!progress || progress.phase === 'idle') {
    return null;
  }

  // error / cancelled: 显示独立 Alert
  if (progress.phase === 'error') {
    return (
      <Alert severity="error" data-testid="write-progress-error">
        {progress.errorMessage ?? '写作失败'}
      </Alert>
    );
  }
  if (progress.phase === 'cancelled') {
    return (
      <Alert severity="warning" data-testid="write-progress-cancelled">
        已取消（已写 {progress.charsWritten} 字）
      </Alert>
    );
  }

  // 找到当前 phase 在 8 阶段链中的位置
  const phase = progress.phase as WritePhase;
  const currentIdx = PHASE_ORDER.indexOf(phase);
  const percent = PHASE_WEIGHTS[phase] ?? 0;

  return (
    <Box data-testid="write-progress">
      {/* 阶段 Chip 链 */}
      <Stack direction="row" spacing={0.5} sx={{ mb: 1, flexWrap: 'wrap', gap: 0.5 }}>
        {PHASE_ORDER.map((p, idx) => {
          const isDone = idx < currentIdx || phase === 'done';
          const isCurrent = idx === currentIdx && phase !== 'done';
          const label = PHASE_LABELS[p];

          return (
            <Chip
              key={p}
              size="small"
              label={label}
              icon={
                isDone ? (
                  <CheckCircleIcon fontSize="small" />
                ) : isCurrent ? (
                  <CircularProgress size={10} color="inherit" />
                ) : (
                  <RadioButtonUncheckedIcon fontSize="small" />
                )
              }
              color={isDone ? 'success' : isCurrent ? 'primary' : 'default'}
              variant={isCurrent ? 'filled' : 'outlined'}
              onClick={onPhaseClick ? () => onPhaseClick(p) : undefined}
              data-testid={`write-progress-phase-${p}`}
            />
          );
        })}
      </Stack>

      {/* 主进度条 */}
      <LinearProgress
        variant="determinate"
        value={percent}
        sx={{ height: 8, borderRadius: 1 }}
        data-testid="write-progress-bar"
      />

      {/* 详细信息 */}
      {detailed && (
        <Stack direction="row" spacing={2} sx={{ mt: 1 }} alignItems="center" flexWrap="wrap">
          <Typography variant="caption" color="text.secondary">
            阶段: <strong>{PHASE_LABELS[phase]}</strong>
          </Typography>
          <Typography variant="caption" color="text.secondary">
            已写: <strong>{progress.charsWritten}</strong> 字
          </Typography>
          {progress.charsPerSecond !== undefined && progress.charsPerSecond > 0 && (
            <Typography variant="caption" color="text.secondary">
              速度: <strong>{progress.charsPerSecond.toFixed(1)}</strong> 字/秒
            </Typography>
          )}
          {progress.etaSeconds !== undefined && progress.etaSeconds > 0 && (
            <Typography variant="caption" color="text.secondary">
              剩余: <strong>~{progress.etaSeconds.toFixed(0)}</strong> 秒
            </Typography>
          )}
          {progress.message && (
            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              {progress.message}
            </Typography>
          )}
        </Stack>
      )}
    </Box>
  );
}