/**
 * SkillReportView - 扫榜 + 拆文报告专用视图（Sprint 5 第 1 批）
 *
 * ScanReportView:
 *   - 输入「数据来源 / 题材 / 关注维度」
 *   - 调 useExecuteSkill + useSkillStream
 *   - 流式接收 markdown 输出
 *   - 自动解析 markdown 表格 → Recharts 可视化
 *
 * AnalyzeReportView:
 *   - 输入「拆文对象 / 关注点」
 *   - 同样流式接收
 *   - 按 ## 章节结构化展示
 */

import { useEffect, useState } from 'react';

import {
  Paper,
  Stack,
  TextField,
  Button,
  Typography,
  Box,
  Card,
  CardContent,
  Alert,
  Chip,
  CircularProgress,
  IconButton,
  Tooltip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

import { useExecuteSkill } from '../../api/skills';
import { useSkillStream } from '../../hooks/useSkillStream';
import { useSnackbar } from '../../hooks/useSnackbar';
import { newIdempotencyKey } from '../../utils/idem';
import {
  SprintReportChart,
  parseMarkdownTables,
  tableRowsToChartPoints,
} from './SprintReportChart';
import type { SkillInfo } from '../../types/skills';

// ============ ScanReportView ============

interface ScanReportViewProps {
  skill: SkillInfo;
}

export function ScanReportView({ skill }: ScanReportViewProps) {
  const snackbar = useSnackbar();
  const [source, setSource] = useState('');
  const [genres, setGenres] = useState('玄幻 都市 言情 历史 科幻');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [streaming, setStreaming] = useState(false);

  const executeSkill = useExecuteSkill(skill.name);
  const skillStream = useSkillStream();

  useEffect(() => {
    if (!taskId) return;
    setStreamingText('');
    setStreaming(true);
    void skillStream
      .stream({
        taskId,
        skillName: skill.name,
        onChunk: (text: string) => setStreamingText((p) => p + text),
        onDone: () => {
          setStreaming(false);
          snackbar.success('扫榜完成');
        },
        onError: (err: Error) => {
          setStreaming(false);
          snackbar.error(`失败: ${err.message}`);
        },
      })
      .catch(() => setStreaming(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const handleStart = async () => {
    if (!source.trim()) {
      snackbar.warning('请填写数据来源');
      return;
    }
    try {
      const resp = await executeSkill.mutateAsync({
        params: {
          source: source.trim(),
          genres: genres.split(/\s+/).filter(Boolean),
          idempotency_key: newIdempotencyKey(),
        },
      });
      setTaskId(resp.task_id);
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCancel = () => {
    if (taskId) void skillStream.cancel(taskId);
    setTaskId(null);
    setStreaming(false);
  };

  // 解析 markdown 表格
  const tables = parseMarkdownTables(streamingText);

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          输入参数
        </Typography>
        <Stack spacing={2}>
          <TextField
            label="数据来源（平台 / 链接 / 备注）"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="起点中文网 / 历史趋势参考"
            fullWidth
            inputProps={{ 'data-testid': `scan-${skill.name}-source` }}
          />
          <TextField
            label="关注题材（空格分隔）"
            value={genres}
            onChange={(e) => setGenres(e.target.value)}
            fullWidth
            helperText="默认 玄幻 都市 言情 历史 科幻"
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            {streaming ? (
              <Button
                variant="outlined"
                color="warning"
                startIcon={<StopIcon />}
                onClick={handleCancel}
                data-testid={`scan-${skill.name}-cancel`}
              >
                取消
              </Button>
            ) : (
              <Button
                variant="contained"
                startIcon={
                  executeSkill.isPending ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : (
                    <PlayArrowIcon />
                  )
                }
                disabled={executeSkill.isPending}
                onClick={() => void handleStart()}
                data-testid={`scan-${skill.name}-start`}
              >
                开始扫榜
              </Button>
            )}
          </Stack>
        </Stack>
      </Paper>

      {streaming && (
        <Stack direction="row" alignItems="center" spacing={1}>
          <CircularProgress size={16} />
          <Typography variant="body2">扫榜中...</Typography>
        </Stack>
      )}

      {/* 自动提取的图表 */}
      {tables.length > 0 && (
        <Box>
          <Typography variant="h6" sx={{ mb: 1 }}>
            数据可视化（从 markdown 表格自动提取）
          </Typography>
          {tables.map((table, idx) => (
            <Card key={idx} sx={{ mb: 2 }}>
              <CardContent>
                <SprintReportChart
                  title={`${table.heading} (${table.rows.length} 条)`}
                  data={tableRowsToChartPoints(table.rows)}
                />
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      {/* 原始 markdown 输出 */}
      {streamingText && (
        <Card>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle2" sx={{ flex: 1 }}>
                报告原文 ({streamingText.length.toLocaleString()} 字)
              </Typography>
              <Tooltip title="复制">
                <IconButton
                  size="small"
                  onClick={() => {
                    void navigator.clipboard.writeText(streamingText);
                    snackbar.success('已复制');
                  }}
                >
                  <ContentCopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <Box
              sx={{
                p: 2,
                bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.100' : 'grey.900'),
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                maxHeight: 480,
                overflow: 'auto',
              }}
            >
              {streamingText}
            </Box>
          </CardContent>
        </Card>
      )}

      {!streaming && !streamingText && (
        <Alert severity="info">
          点击「开始扫榜」启动，输出 markdown 报告将自动提取表格渲染为图表。
        </Alert>
      )}
    </Stack>
  );
}

// ============ AnalyzeReportView ============

interface AnalyzeReportViewProps {
  skill: SkillInfo;
}

interface Section {
  heading: string;
  level: number;
  content: string;
}

/**
 * 把 markdown 按 ## / ### 分章节
 */
function splitMarkdownToSections(md: string): Section[] {
  const lines = md.split('\n');
  const sections: Section[] = [];
  let current: Section | null = null;
  for (const line of lines) {
    const m = line.match(/^(#{1,3})\s+(.+)/);
    if (m && m[2] && m[1]) {
      if (current) sections.push(current);
      current = { heading: m[2].trim(), level: m[1].length, content: '' };
    } else if (current) {
      current.content += line + '\n';
    }
  }
  if (current) sections.push(current);
  return sections;
}

export function AnalyzeReportView({ skill }: AnalyzeReportViewProps) {
  const snackbar = useSnackbar();
  const [target, setTarget] = useState('');
  const [focus, setFocus] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [streaming, setStreaming] = useState(false);

  const executeSkill = useExecuteSkill(skill.name);
  const skillStream = useSkillStream();

  useEffect(() => {
    if (!taskId) return;
    setStreamingText('');
    setStreaming(true);
    void skillStream
      .stream({
        taskId,
        skillName: skill.name,
        onChunk: (text: string) => setStreamingText((p) => p + text),
        onDone: () => {
          setStreaming(false);
          snackbar.success('拆文完成');
        },
        onError: (err: Error) => {
          setStreaming(false);
          snackbar.error(`失败: ${err.message}`);
        },
      })
      .catch(() => setStreaming(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const handleStart = async () => {
    if (!target.trim()) {
      snackbar.warning('请填写拆文对象');
      return;
    }
    try {
      const resp = await executeSkill.mutateAsync({
        params: {
          target: target.trim(),
          focus: focus.trim() || undefined,
          idempotency_key: newIdempotencyKey(),
        },
      });
      setTaskId(resp.task_id);
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCancel = () => {
    if (taskId) void skillStream.cancel(taskId);
    setTaskId(null);
    setStreaming(false);
  };

  const sections = splitMarkdownToSections(streamingText);

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          输入参数
        </Typography>
        <Stack spacing={2}>
          <TextField
            label="拆文对象（章节 / 路径 / 标题）"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="第21章 / 正文/第21章.md / 书名 - 章节标题"
            fullWidth
            inputProps={{ 'data-testid': `analyze-${skill.name}-target` }}
          />
          <TextField
            label="关注点（可选）"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="开头钩子 / 人物动机 / 节奏控制"
            fullWidth
            multiline
            rows={2}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            {streaming ? (
              <Button
                variant="outlined"
                color="warning"
                startIcon={<StopIcon />}
                onClick={handleCancel}
              >
                取消
              </Button>
            ) : (
              <Button
                variant="contained"
                startIcon={
                  executeSkill.isPending ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : (
                    <PlayArrowIcon />
                  )
                }
                disabled={executeSkill.isPending}
                onClick={() => void handleStart()}
                data-testid={`analyze-${skill.name}-start`}
              >
                开始拆文
              </Button>
            )}
          </Stack>
        </Stack>
      </Paper>

      {streaming && (
        <Stack direction="row" alignItems="center" spacing={1}>
          <CircularProgress size={16} />
          <Typography variant="body2">拆文中...</Typography>
        </Stack>
      )}

      {/* 结构化报告：按 ## 分章节 */}
      {sections.length > 0 && (
        <Box>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="h6" sx={{ flex: 1 }}>
              报告 ({sections.length} 章节)
            </Typography>
            <Chip
              size="small"
              label={`${streamingText.length.toLocaleString()} 字`}
              color="primary"
            />
            <Tooltip title="复制全文">
              <IconButton
                size="small"
                onClick={() => {
                  void navigator.clipboard.writeText(streamingText);
                  snackbar.success('已复制');
                }}
              >
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>

          {sections.map((section, idx) => (
            <Accordion key={idx} defaultExpanded={idx < 3} sx={{ mb: 1 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography
                  variant={section.level === 1 ? 'h6' : 'subtitle1'}
                  sx={{ fontWeight: section.level === 1 ? 700 : 500 }}
                >
                  {section.heading}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: 13,
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.6,
                  }}
                >
                  {section.content.trim()}
                </Box>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}

      {!streaming && !streamingText && (
        <Alert severity="info">
          点击「开始拆文」启动，输出 markdown 报告将按 ## 章节自动展开。
        </Alert>
      )}
    </Stack>
  );
}
