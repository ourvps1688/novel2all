/**
 * SkillRunner: 13 个 skill 复用的通用执行器 (S1 核心)
 *
 * 设计 (playbook §4.1):
 *   - 接收 SkillInfo + 可选 inputSchema + onSuccess 回调
 *   - 内部 state: phase / output / progress / error
 *   - 走 useExecuteSkill (POST /api/skills/{name}/execute)
 *   - 走 useSkillStream (SSE + 3 次重连 + polling 降级)
 *   - Cancel: 调 stream.cancel(taskId)
 *   - Copy / Diff / Download 操作按钮
 *
 * 不关心 skill 业务, 只负责 execute + stream + cancel
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  IconButton,
  LinearProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';

import { SkillOutput } from './SkillOutput';
import { useExecuteSkill } from '../../api/skills';
import { useSkillStream } from '../../hooks/useSkillStream';
import { useSkillExecutionStore } from '../../store/skillExecutionStore';
import { useSnackbar } from '../../hooks/useSnackbar';
import type {
  SkillExecutionPhase,
  SkillInfo,
  SkillOutputChunk,
  WriteProgress,
} from '../../types/skills';
import { phaseProgressPercent } from '../../types/skills';
import { newIdempotencyKey } from '../../utils/idem';

const MAX_RECONNECT_ATTEMPTS = 3;

export interface SkillRunnerProps {
  skill: SkillInfo;
  projectRoot?: string;
  defaultParams?: Record<string, unknown>;
  onSuccess?: (output: { text: string; taskId: string; durationMs: number }) => void;
}

export function SkillRunner({
  skill,
  projectRoot = '.',
  defaultParams,
  onSuccess,
}: SkillRunnerProps) {
  const snackbar = useSnackbar();
  const { mutateAsync: executeSkill, isPending: isExecuting, error: executeError } = useExecuteSkill(skill.name);
  const { stream, cancel } = useSkillStream();

  // 历史 store (本地)
  const startRun = useSkillExecutionStore((s) => s.startRun);
  const finishRun = useSkillExecutionStore((s) => s.finishRun);

  // 表单数据 (简单 textarea 形式; S4 接 DynamicForm)
  const [inputText, setInputText] = useState<string>(() => {
    if (defaultParams && typeof defaultParams === 'object') {
      const first = Object.values(defaultParams)[0];
      if (typeof first === 'string') return first;
    }
    return skill.defaultInput ?? '';
  });

  const [phase, setPhase] = useState<SkillExecutionPhase>('idle');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [output, setOutput] = useState<SkillOutputChunk[]>([]);
  const [progress, setProgress] = useState<WriteProgress | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [isCancelling, setIsCancelling] = useState(false);
  const [pollingMode, setPollingMode] = useState(false);

  // V1.5.1 修复（已知问题 #2）：用 ref 跟踪当前 taskId，避免卸载 cleanup
  // 捕获首次渲染时的 null（旧实现 bug），确保 in-flight task 被正确取消。
  // 设计：state 变化通过 useEffect 同步到 ref；卸载时读 ref 的最新值。
  const taskIdRef = useRef<string | null>(null);
  useEffect(() => {
    taskIdRef.current = taskId;
  }, [taskId]);

  // 计时器
  useEffect(() => {
    if (phase !== 'running' || startedAt == null) return;
    const interval = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [phase, startedAt]);

  // V1.5.1 修复（已知问题 #2）：卸载时取消 in-flight task，避免 backend pipeline orphan。
  // 用 ref 读最新 taskId（不是闭包捕获的旧值），并在依赖里加 cancel 以满足 exhaustive-deps。
  useEffect(() => {
    return () => {
      const currentTaskId = taskIdRef.current;
      if (currentTaskId && (phase === 'running' || phase === 'preparing')) {
        // cancel() 内部会调 /api/write/cancel/{taskId} → 后端 pipeline_task.cancel()
        cancel(currentTaskId).catch(() => {
          /* ignore - unmount 时静默失败 */
        });
      }
    };
    // phase 在卸载时也是稳定值（不再变化），cancel 函数引用稳定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cancel]);

  // 把 executeError 反映到 errorMsg
  useEffect(() => {
    if (executeError && phase === 'preparing') {
      setErrorMsg(executeError.message);
      setPhase('error');
      if (taskId) finishRun(skill.name, taskId, 'error', '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executeError]);

  const fullText = useMemo(
    () =>
      output
        .filter((c) => c.type === 'text' && typeof c.text === 'string')
        .map((c) => c.text ?? '')
        .join(''),
    [output],
  );

  // 启动执行
  const handleStart = useCallback(async () => {
    setPhase('preparing');
    setOutput([]);
    setErrorMsg(null);
    setProgress(null);
    setElapsedSec(0);
    setReconnectAttempts(0);
    setStartedAt(Date.now());
    setPollingMode(false);

    const localTaskId = startRun(skill.name, inputText);

    try {
      const resp = await executeSkill({
        params: { input: inputText, ...defaultParams },
        projectRoot,
        idempotencyKey: newIdempotencyKey(),
      });
      setTaskId(resp.task_id);
      setPhase('running');

      await stream({
        taskId: resp.task_id,
        skillName: skill.name,
        onChunk: (text) => {
          setOutput((prev) => [...prev, { type: 'text', text }]);
        },
        onProgress: (p) => {
          setProgress({
            phase: (p.phase as WriteProgress['phase']) ?? 'writing',
            charsWritten: p.charsWritten,
            charsPerSecond: p.charsPerSecond,
            etaSeconds: p.etaSeconds,
            message: p.message,
          });
        },
        onReconnect: (attempts) => {
          setReconnectAttempts(attempts);
          if (attempts >= MAX_RECONNECT_ATTEMPTS) {
            setPollingMode(true);
            snackbar.warning('网络不稳定,已切换 polling 模式');
          }
        },
        onError: (err) => {
          setPhase('error');
          setErrorMsg(err.message);
          finishRun(skill.name, resp.task_id, 'error', fullText);
          snackbar.error(`Skill 失败: ${err.message}`);
        },
        onDone: (final) => {
          setPhase('success');
          setProgress({ phase: 'done', charsWritten: final.metadata?.content_chars as number ?? 0 });
          const durationMs = Date.now() - (startedAt ?? Date.now());
          finishRun(skill.name, resp.task_id, 'success', fullText);
          onSuccess?.({ text: fullText, taskId: resp.task_id, durationMs });
          snackbar.success(`${skill.name} 完成 (${Math.floor(durationMs / 1000)}s)`);
        },
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setPhase('error');
      setErrorMsg(msg);
      finishRun(skill.name, localTaskId, 'error', '');
      snackbar.error(`执行失败: ${msg}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executeSkill, inputText, projectRoot, skill.name, stream, snackbar, startRun, finishRun, defaultParams, onSuccess]);

  // 取消
  const handleCancel = useCallback(async () => {
    if (!taskId || isCancelling) return;
    setIsCancelling(true);
    try {
      await cancel(taskId);
      setPhase('cancelled');
      finishRun(skill.name, taskId, 'cancelled', fullText);
      snackbar.info('已取消');
    } catch {
      snackbar.error('取消失败');
    } finally {
      setIsCancelling(false);
    }
  }, [taskId, isCancelling, cancel, finishRun, snackbar, skill.name, fullText]);

  // 复制
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      snackbar.success('已复制到剪贴板');
    } catch {
      snackbar.error('复制失败');
    }
  }, [fullText, snackbar]);

  // 下载
  const handleDownload = useCallback(() => {
    const blob = new Blob([fullText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${skill.name}_output_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    snackbar.success('已下载');
  }, [fullText, skill.name, snackbar]);

  // 重置
  const handleReset = useCallback(() => {
    setPhase('idle');
    setTaskId(null);
    setOutput([]);
    setProgress(null);
    setErrorMsg(null);
    setStartedAt(null);
    setElapsedSec(0);
    setReconnectAttempts(0);
    setIsCancelling(false);
    setPollingMode(false);
  }, []);

  const isRunning = phase === 'running' || phase === 'preparing';
  const canStart = !isRunning && inputText.length > 0;

  return (
    <Card variant="outlined" data-testid={`skill-runner-${skill.name}`}>
      <CardContent>
        {/* Header */}
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ mb: 2 }}
        >
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6">{skill.name}</Typography>
            <Typography variant="caption" color="text.secondary">
              v{skill.version}
            </Typography>
            <Chip size="small" label={skill.category} variant="outlined" />
          </Stack>
          {isRunning && (
            <Stack direction="row" alignItems="center" spacing={1}>
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">
                {pollingMode ? 'polling…' : '运行中'} · {elapsedSec}s
              </Typography>
              {reconnectAttempts > 0 && (
                <Chip
                  label={`重连 ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`}
                  size="small"
                  color={pollingMode ? 'warning' : 'info'}
                  variant="outlined"
                />
              )}
            </Stack>
          )}
        </Stack>

        <Grid container spacing={2}>
          {/* Input */}
          <Grid item xs={12} md={5}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              输入
            </Typography>
            <TextField
              fullWidth
              multiline
              minRows={4}
              maxRows={10}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={skill.defaultInput || '输入你的需求…'}
              disabled={isRunning}
              inputProps={{ 'aria-label': 'skill 输入' }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              {isRunning ? (
                <Button
                  fullWidth
                  variant="outlined"
                  color="error"
                  startIcon={<StopIcon />}
                  onClick={handleCancel}
                  disabled={isCancelling}
                  aria-label="取消执行"
                >
                  {isCancelling ? '取消中…' : '取消'}
                </Button>
              ) : (
                <Button
                  fullWidth
                  variant="contained"
                  startIcon={<PlayArrowIcon />}
                  onClick={handleStart}
                  disabled={!canStart || isExecuting}
                  aria-label="执行 skill"
                  data-testid={`execute-${skill.name}`}
                >
                  {isExecuting ? '提交中…' : '执行'}
                </Button>
              )}
              {!isRunning && (phase === 'error' || phase === 'success' || phase === 'cancelled') && (
                <Tooltip title="重置">
                  <IconButton onClick={handleReset} aria-label="重置">
                    <RefreshIcon />
                  </IconButton>
                </Tooltip>
              )}
            </Stack>

            {phase === 'error' && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {errorMsg ?? '执行失败'}
              </Alert>
            )}
          </Grid>

          {/* Output */}
          <Grid item xs={12} md={7}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
              <Typography variant="subtitle2">输出</Typography>
              {output.length > 0 && phase === 'success' && (
                <Stack direction="row" spacing={0.5}>
                  <Tooltip title="复制">
                    <IconButton size="small" onClick={handleCopy} aria-label="复制输出">
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="下载">
                    <IconButton size="small" onClick={handleDownload} aria-label="下载输出">
                      <DownloadIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              )}
            </Stack>

            {progress && isRunning && (
              <Box sx={{ mb: 1 }}>
                <LinearProgress
                  variant="determinate"
                  value={phaseProgressPercent(progress.phase)}
                />
                <Typography variant="caption" color="text.secondary">
                  {progress.phase} · {progress.charsWritten} 字
                  {progress.charsPerSecond !== undefined && ` · ${progress.charsPerSecond.toFixed(1)} 字/秒`}
                </Typography>
              </Box>
            )}

            <SkillOutput
              chunks={output}
              phase={phase}
              progress={progress}
              errorMsg={errorMsg}
              isStreaming={phase === 'running'}
            />
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}