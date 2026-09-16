/**
 * ImportPage — 已有小说导入向导（PRD §5 Sprint 4 第 5 项）
 *
 * 流程（按 PRD + story-import SKILL.md）:
 *   1. 用户输入项目根路径（或点击「选择文件」上传 .txt）
 *   2. 后端调 story-import skill → 切分章节 + 提取 bible
 *   3. SSE 流式输出"项目结构预览"
 *   4. 显示"可从第 N+1 章续写"提示
 *
 * 复用 useExecuteSkill + useSkillStream
 */

import { useEffect, useRef, useState } from 'react';

import {
  Container,
  Typography,
  Box,
  Stack,
  Paper,
  Button,
  TextField,
  Alert,
  Stepper,
  Step,
  StepLabel,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  Tooltip,
  Divider,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

import { useExecuteSkill } from '../api/skills';
import { useSkillStream } from '../hooks/useSkillStream';
import { useSnackbar } from '../hooks/useSnackbar';

const STEPS = ['输入路径', '解析章节', '预览结果', '开始续写'] as const;
type StepIndex = 0 | 1 | 2 | 3;

export function ImportPage() {
  const snackbar = useSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeStep, setActiveStep] = useState<StepIndex>(0);
  const [projectPath, setProjectPath] = useState('');
  const [parsedText, setParsedText] = useState('');
  const [chunkBuffer, setChunkBuffer] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);

  const executeSkill = useExecuteSkill('story-import');
  const stream = useSkillStream();

  // 订阅 SSE 流：taskId 一旦确定，立即开始 stream
  useEffect(() => {
    if (!taskId) return;
    setChunkBuffer('');
    setActiveStep(1);
    void stream
      .stream({
        taskId,
        skillName: 'story-import',
        onChunk: (text: string) => {
          setChunkBuffer((prev) => prev + text);
        },
        onDone: () => {
          setActiveStep(2);
          snackbar.success('导入完成，可从下一章开始续写');
        },
        onError: (err: Error) => {
          snackbar.error(`导入失败: ${err.message}`);
          setActiveStep(0);
        },
      })
      .catch(() => {
        /* onError already handled */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!projectPath) {
      snackbar.warning('请先填写项目根路径');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      setParsedText(text);
      snackbar.success(`已加载文件：${file.name} (${text.length} 字)`);
    };
    reader.readAsText(file, 'utf-8');
  };

  const handleStartImport = async () => {
    if (!projectPath.trim()) {
      snackbar.warning('请填写项目根路径');
      return;
    }
    setChunkBuffer('');
    try {
      const resp = await executeSkill.mutateAsync({
        params: {
          project_root: projectPath.trim(),
          source_text: parsedText || undefined,
        },
        projectRoot: projectPath.trim(),
      });
      setTaskId(resp.task_id);
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : String(err));
      setActiveStep(0);
    }
  };

  const handleReset = () => {
    if (taskId) void void stream.cancel(taskId);
    setTaskId(null);
    setActiveStep(0);
    setChunkBuffer('');
    setParsedText('');
  };

  const handleCopy = () => {
    void navigator.clipboard.writeText(chunkBuffer);
    snackbar.success('已复制到剪贴板');
  };

  // 简易章节数统计
  const chapterCount = (chunkBuffer.match(/^第[一二三四五六七八九十百千0-9]+章|^Chapter\s+\d+/gm) ?? []).length;

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Stack spacing={3}>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <RocketLaunchIcon color="primary" sx={{ fontSize: 32 }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h4">导入已有小说</Typography>
            <Typography variant="body2" color="text.secondary">
              已有 txt / docx / 链接的小说 → 反向解析为 novel2all 项目结构，可从第 N+1 章续写
            </Typography>
          </Box>
          <Tooltip title="重置">
            <span>
              <IconButton onClick={handleReset} disabled={taskId !== null}>
                <RefreshIcon />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>

        <Stepper activeStep={activeStep} alternativeLabel>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {/* Step 0: 输入路径 */}
        {activeStep === 0 && (
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">1. 项目根路径</Typography>
              <TextField
                label="项目根路径"
                value={projectPath}
                onChange={(e) => setProjectPath(e.target.value)}
                placeholder="/path/to/novel2all 或 . (当前目录)"
                fullWidth
                autoFocus
                inputProps={{ 'data-testid': 'import-project-path' }}
              />
              <Typography variant="caption" color="text.secondary">
                必须是 novel2all 已初始化的项目路径（含有 <code>_tracking-state.json</code> 或可初始化）
              </Typography>

              <Divider />

              <Typography variant="subtitle1">可选：上传 txt 文件</Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Button
                  startIcon={<UploadFileIcon />}
                  variant="outlined"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!projectPath}
                  data-testid="import-upload-file"
                >
                  选择 .txt
                </Button>
                <Typography variant="caption" color={parsedText ? 'success.main' : 'text.secondary'}>
                  {parsedText
                    ? `已加载 ${parsedText.length.toLocaleString()} 字`
                    : '（未上传，将由后端自动切分）'}
                </Typography>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,text/plain"
                  style={{ display: 'none' }}
                  onChange={handleFileSelect}
                />
              </Stack>

              <Alert severity="info">
                <strong>支持的输入：</strong>
                <ul style={{ margin: '4px 0 0 16px' }}>
                  <li>本地 <code>.txt</code> 文件（上传）</li>
                  <li>已发布章节粘贴文本（上传后端解析）</li>
                  <li>项目根路径下已有 <code>正文/第NNN章.md</code>（后端自动切分）</li>
                </ul>
              </Alert>

              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button
                  variant="contained"
                  size="large"
                  onClick={() => void handleStartImport()}
                  disabled={!projectPath.trim() || executeSkill.isPending}
                  data-testid="import-start"
                >
                  {executeSkill.isPending ? '启动中...' : '开始导入'}
                </Button>
              </Stack>
            </Stack>
          </Paper>
        )}

        {/* Step 1: 解析中 */}
        {activeStep >= 1 && (
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">2. 解析章节中...</Typography>
              {taskId !== null && (
                <Stack direction="row" alignItems="center" spacing={1}>
                  <CircularProgress size={20} />
                  <Typography variant="body2">stream 接收中...</Typography>
                </Stack>
              )}
              {chunkBuffer.length > 0 && (
                <Box>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                    <Chip
                      size="small"
                      label={`已接收 ${chunkBuffer.length.toLocaleString()} 字`}
                      color="primary"
                    />
                    {chapterCount > 0 && (
                      <Chip size="small" label={`识别 ${chapterCount} 章`} />
                    )}
                  </Stack>
                  <Box
                    sx={{
                      p: 2,
                      bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.100' : 'grey.900'),
                      borderRadius: 1,
                      fontFamily: 'monospace',
                      fontSize: 12,
                      maxHeight: 320,
                      overflow: 'auto',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {chunkBuffer || '（等待后端输出...）'}
                  </Box>
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button
                      size="small"
                      startIcon={<ContentCopyIcon />}
                      onClick={handleCopy}
                      disabled={!chunkBuffer}
                    >
                      复制
                    </Button>
                    {taskId !== null && (
                      <Button size="small" color="warning" onClick={() => taskId && void stream.cancel(taskId)}>
                        取消
                      </Button>
                    )}
                  </Stack>
                </Box>
              )}
            </Stack>
          </Paper>
        )}

        {/* Step 2: 完成 */}
        {activeStep >= 2 && (
          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <CheckCircleIcon color="success" />
                  <Typography variant="h6">3. 导入完成</Typography>
                </Stack>
                <Alert severity="success">
                  项目 <code>{projectPath}</code> 已导入完成，可从下一章开始续写。
                </Alert>
                <Typography variant="subtitle2">生成的项目结构：</Typography>
                <Box
                  sx={{
                    p: 2,
                    bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.100' : 'grey.900'),
                    borderRadius: 1,
                    fontFamily: 'monospace',
                    fontSize: 12,
                  }}
                >
                  {projectPath}/{'\n'}
                  ├── _tracking-state.json (一次性补齐){'\n'}
                  ├── 设定/{'\n'}
                  {'  '}├── 角色/*.md{'\n'}
                  {'  '}└── 世界观/*{'\n'}
                  ├── 大纲/{'\n'}
                  {'  '}└── 细纲_第NNN章.md (反向生成){'\n'}
                  └── 正文/{'\n'}
                  {'  '}└── 第NNN章.md (原文备份)
                </Box>
              </Stack>
            </CardContent>
          </Card>
        )}

        {/* Step 3: 开始续写 */}
        {activeStep >= 2 && (
          <Paper sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">4. 开始续写</Typography>
              <Typography variant="body2" color="text.secondary">
                现在 <code>/write</code> 页面会自动加载所有已有信息，无需重新交代设定。
              </Typography>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={() => (window.location.href = '/write')}
                >
                  打开写作页
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => (window.location.href = '/chapters')}
                >
                  查看章节列表
                </Button>
                <Button onClick={handleReset}>导入另一本</Button>
              </Stack>
            </Stack>
          </Paper>
        )}
      </Stack>
    </Container>
  );
}
