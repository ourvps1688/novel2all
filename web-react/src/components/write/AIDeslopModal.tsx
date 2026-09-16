/**
 * AIDeslopModal: AI 去 AI 味 Diff 预览 Modal (Sprint 3 / V1.5.3)
 *
 * 流程:
 *   1. open=true 触发, useExecuteSkill('story-deslop') 启动 task
 *   2. 拿 task_id 后, useSkillStream() 订阅 SSE 流
 *   3. chunk 事件累积到 deslopped 文本
 *   4. done 事件 → loading=false
 *   5. 用户 [应用] → onApply(deslopped) 替换原文
 *      用户 [拒绝] → onClose()
 *
 * 自管 API 调用（useExecuteSkill + useSkillStream），父组件只需传 props。
 */

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Stack,
  Typography,
  CircularProgress,
  Alert,
  Divider,
  Chip,
} from '@mui/material';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';

import { useExecuteSkill } from '../../api/skills';
import { useSkillStream } from '../../hooks/useSkillStream';
import { newIdempotencyKey } from '../../utils/idem';

const SKILL_NAME = 'story-deslop';

export interface AIDeslopModalProps {
  open: boolean;
  onClose: () => void;

  /** 章节号 (用于显示) */
  chapter: number;

  /** 原文 (只读) */
  original: string;

  /** 项目根 (默认 '.') */
  projectRoot?: string;

  /** 应用改写 */
  onApply: (deslopped: string) => void;
}

export function AIDeslopModal({
  open,
  onClose,
  chapter,
  original,
  projectRoot = '.',
  onApply,
}: AIDeslopModalProps) {
  const [deslopped, setDeslopped] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chunks, setChunks] = useState<string[]>([]);

  const executeSkill = useExecuteSkill(SKILL_NAME);
  const { stream, cancel } = useSkillStream();

  // 启动 / 关闭时清理
  useEffect(() => {
    if (open) {
      // 重置状态
      setDeslopped(null);
      setChunks([]);
      setError(null);
      setTaskId(null);
      // 启动 task + 订阅 SSE
      void (async () => {
        try {
          const resp = await executeSkill.mutateAsync({
            params: { text: original, chapter },
            projectRoot,
            idempotencyKey: newIdempotencyKey(),
          });
          setTaskId(resp.task_id);
          await stream({
            taskId: resp.task_id,
            skillName: SKILL_NAME,
            onChunk: (text) => {
              setChunks((prev) => [...prev, text]);
            },
            onProgress: () => {
              // 不展示具体进度（deslop 主要是 chunk 累积）
            },
            onError: (err) => {
              setError(err instanceof Error ? err.message : 'skill 错误');
            },
            onDone: (output) => {
              // onDone 的 output.text 是累积的最终结果
              setDeslopped(output.text);
            },
          });
        } catch (err) {
          setError(err instanceof Error ? err.message : '启动去 AI 味失败');
        }
      })();
    } else {
      // 关闭时取消正在跑的 task
      if (taskId) {
        void cancel(taskId).catch(() => {
          /* cancel 失败忽略 */
        });
      }
    }
    // 不在 deps 加 taskId（避免循环）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const loading = executeSkill.isPending || (taskId != null && deslopped == null && error == null);
  const origLen = original.length;
  const newLen = deslopped?.length ?? 0;
  const delta = newLen - origLen;
  const deltaPct = origLen > 0 ? (delta / origLen) * 100 : 0;

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoFixHighIcon color="primary" />
          <Typography variant="h6">去 AI 味 · 第 {chapter} 章</Typography>
          {loading && <CircularProgress size={20} />}
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="body2">{error}</Typography>
          </Alert>
        ) : null}

        {loading && !deslopped ? (
          <Stack alignItems="center" spacing={2} sx={{ py: 4 }}>
            <CircularProgress />
            <Typography variant="body2" color="text.secondary">
              story-deslop skill 跑两层检测：本地规则扫描 + LLM 软判断...
            </Typography>
            {chunks.length > 0 && (
              <Typography variant="caption" color="text.secondary">
                已收集 {chunks.length} 个 chunk · {chunks.join('').length} 字
              </Typography>
            )}
          </Stack>
        ) : (
          <Stack spacing={2}>
            <Box>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                <Typography variant="subtitle2" color="text.secondary">
                  原文
                </Typography>
                <Chip size="small" label={`${origLen} 字`} variant="outlined" />
              </Stack>
              <Box
                sx={{
                  p: 2,
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  bgcolor: 'grey.50',
                  maxHeight: 240,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: 14,
                }}
              >
                {original}
              </Box>
            </Box>

            <Stack direction="row" alignItems="center" spacing={1} justifyContent="center">
              <Divider sx={{ flex: 1 }} />
              <CompareArrowsIcon color="action" />
              <Divider sx={{ flex: 1 }} />
            </Stack>

            <Box>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                <Typography variant="subtitle2" color="primary">
                  去 AI 味后
                </Typography>
                {deslopped && (
                  <Chip
                    size="small"
                    label={`${newLen} 字 (${delta >= 0 ? '+' : ''}${delta} / ${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(1)}%)`}
                    color={Math.abs(deltaPct) < 30 ? 'success' : 'warning'}
                    variant="outlined"
                  />
                )}
                {loading && <Chip size="small" label="流式生成中..." color="info" />}
              </Stack>
              <Box
                sx={{
                  p: 2,
                  border: 1,
                  borderColor: 'primary.main',
                  borderRadius: 1,
                  bgcolor: 'background.paper',
                  maxHeight: 240,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: 14,
                }}
              >
                {deslopped || chunks.join('') || (
                  <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    （等待 AI 输出...）
                  </Typography>
                )}
              </Box>
            </Box>

            {!loading && deslopped && Math.abs(deltaPct) > 30 && (
              <Alert severity="warning">
                <Typography variant="body2">
                  改写后字数变化超过 30%（删除/增加较多内容），建议人工检查后应用。
                </Typography>
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
          拒绝
        </Button>
        <Button
          variant="contained"
          onClick={() => deslopped && onApply(deslopped)}
          disabled={loading || !deslopped}
          startIcon={<AutoFixHighIcon />}
        >
          应用改写
        </Button>
      </DialogActions>
    </Dialog>
  );
}
