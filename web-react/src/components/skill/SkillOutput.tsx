/**
 * SkillOutput: 渲染 SkillRunner 流式输出
 *
 * 支持：
 *   - text 类型: 纯文本 (带换行)
 *   - json 类型: 代码块格式化 (JSON.stringify with 2 缩进)
 *   - file 类型: 文件下载提示
 *
 * 根据 phase 切换 UI 状态 (loading / streaming / success)
 */

import { useMemo } from 'react';
import { Box, Card, CardContent, CircularProgress, Stack, Typography, Chip } from '@mui/material';
import TerminalIcon from '@mui/icons-material/Terminal';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import BlockIcon from '@mui/icons-material/Block';

import type {
  SkillExecutionPhase,
  SkillOutputChunk,
  WriteProgress,
} from '../../types/skills';
import { PHASE_LABELS, phaseProgressPercent } from '../../types/skills';

export interface SkillOutputProps {
  chunks: SkillOutputChunk[];
  phase: SkillExecutionPhase;
  progress?: WriteProgress | null;
  errorMsg?: string | null;
  /** 是否正在写入 (用于显示光标动画) */
  isStreaming?: boolean;
}

const PHASE_COLOR: Record<SkillExecutionPhase, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
  idle: 'default',
  preparing: 'primary',
  running: 'primary',
  success: 'success',
  error: 'error',
  cancelled: 'warning',
};

const PHASE_LABEL: Record<SkillExecutionPhase, string> = {
  idle: '待执行',
  preparing: '准备中',
  running: '运行中',
  success: '已完成',
  error: '失败',
  cancelled: '已取消',
};

export function SkillOutput({
  chunks,
  phase,
  progress,
  errorMsg,
  isStreaming = false,
}: SkillOutputProps) {
  // 聚合 text 片段
  const fullText = useMemo(
    () =>
      chunks
        .filter((c) => c.type === 'text' && typeof c.text === 'string')
        .map((c) => c.text ?? '')
        .join(''),
    [chunks],
  );

  const isEmpty = chunks.length === 0 && phase !== 'preparing' && phase !== 'running';

  return (
    <Card
      variant="outlined"
      sx={{
        minHeight: 320,
        bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.50' : 'grey.900'),
      }}
      aria-label="Skill 输出区"
      aria-busy={phase === 'running' || phase === 'preparing'}
    >
      <CardContent>
        <Stack spacing={1.5}>
          {/* 状态栏 */}
          <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <PhaseIcon phase={phase} />
              <Chip
                size="small"
                color={PHASE_COLOR[phase]}
                label={PHASE_LABEL[phase]}
                variant={phase === 'idle' ? 'outlined' : 'filled'}
              />
              {progress?.phase && phase === 'running' && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${PHASE_LABELS[progress.phase] ?? progress.phase} · ${progress.charsWritten} 字`}
                />
              )}
            </Stack>
            {phase === 'running' && progress?.phase && (
              <Typography variant="caption" color="text.secondary">
                {phaseProgressPercent(progress.phase)}%
              </Typography>
            )}
          </Stack>

          {/* 输出文本 */}
          {isEmpty ? (
            <EmptyHint phase={phase} />
          ) : (
            <Box
              component="pre"
              sx={{
                m: 0,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: '"Source Han Serif", "Songti SC", serif',
                fontSize: 14,
                lineHeight: 1.7,
                color: 'text.primary',
                maxHeight: 600,
                overflow: 'auto',
              }}
            >
              {fullText}
              {isStreaming && (
                <Box
                  component="span"
                  sx={{
                    display: 'inline-block',
                    width: 8,
                    height: 16,
                    bgcolor: 'primary.main',
                    ml: 0.5,
                    verticalAlign: 'text-bottom',
                    animation: 'blink 1s steps(2) infinite',
                    '@keyframes blink': {
                      '0%, 50%': { opacity: 1 },
                      '50.01%, 100%': { opacity: 0 },
                    },
                  }}
                />
              )}
            </Box>
          )}

          {/* 进度详情 */}
          {progress?.message && phase === 'running' && (
            <Typography variant="caption" color="text.secondary">
              {progress.message}
            </Typography>
          )}

          {/* 错误 */}
          {errorMsg && phase === 'error' && (
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{
                p: 1.5,
                bgcolor: (t) => (t.palette.mode === 'light' ? 'error.50' : 'error.900'),
                borderRadius: 1,
              }}
              role="alert"
            >
              <ErrorOutlineIcon color="error" fontSize="small" />
              <Typography variant="body2" color="error.main">
                {errorMsg}
              </Typography>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

function PhaseIcon({ phase }: { phase: SkillExecutionPhase }) {
  if (phase === 'running' || phase === 'preparing') {
    return <CircularProgress size={16} thickness={5} />;
  }
  if (phase === 'success') {
    return <CheckCircleIcon color="success" fontSize="small" />;
  }
  if (phase === 'error') {
    return <ErrorOutlineIcon color="error" fontSize="small" />;
  }
  if (phase === 'cancelled') {
    return <BlockIcon color="warning" fontSize="small" />;
  }
  return <TerminalIcon color="disabled" fontSize="small" />;
}

function EmptyHint({ phase }: { phase: SkillExecutionPhase }) {
  if (phase === 'idle') {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
        输入参数后点击「执行」开始
      </Typography>
    );
  }
  return null;
}