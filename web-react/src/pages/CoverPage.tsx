/**
 * CoverPage: 封面 prompt 生成页 (Sprint 3 / V1.5.3)
 *
 * 流程:
 *   1. 输入书名 / 题材 / 文风
 *   2. 提交 → 调 story-cover skill（SSE 流式生成）
 *   3. 显示生成的 prompt + 元数据
 *   4. 一键复制到剪贴板
 */

import { useEffect, useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Stack,
  TextField,
  Button,
  Card,
  CardContent,
  CardActions,
  Alert,
  CircularProgress,
  Divider,
  Chip,
  Tooltip,
  IconButton,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import RefreshIcon from '@mui/icons-material/Refresh';

import { useExecuteSkill } from '../api/skills';
import { useSkillStream } from '../hooks/useSkillStream';
import { newIdempotencyKey } from '../utils/idem';
import { useSnackbar } from '../hooks/useSnackbar';
import { EmptyState } from '../components/common/EmptyState';

const SKILL_NAME = 'story-cover';
const DEFAULT_PROJECT_ROOT = '.';

const GENRE_PRESETS = ['玄幻', '都市', '言情', '悬疑', '科幻', '历史', '武侠', '仙侠', '军事', '体育'];
const STYLE_PRESETS = ['严肃文学', '爽文', '轻松', '文艺', '热血', '治愈', '黑色幽默', '意识流'];

export function CoverPage() {
  const { show } = useSnackbar();
  const [title, setTitle] = useState('');
  const [genre, setGenre] = useState('');
  const [style, setStyle] = useState('');
  const [extra, setExtra] = useState('');
  const [running, setRunning] = useState(false);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [chunks, setChunks] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [idemKey, setIdemKey] = useState<string | null>(null);

  const executeSkill = useExecuteSkill(SKILL_NAME);
  const { stream, cancel } = useSkillStream();

  // 启动 / 关闭时清理
  useEffect(() => {
    return () => {
      if (idemKey) {
        void cancel(idemKey).catch(() => {
          /* ignore */
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idemKey]);

  const handleGenerate = async () => {
    if (!title.trim()) {
      show('请输入书名', 'warning');
      return;
    }
    setRunning(true);
    setPrompt(null);
    setChunks([]);
    setError(null);

    const key = newIdempotencyKey();
    setIdemKey(key);

    try {
      const resp = await executeSkill.mutateAsync({
        params: {
          title: title.trim(),
          genre: genre.trim() || '未指定',
          style: style.trim() || '未指定',
          extra: extra.trim(),
        },
        projectRoot: DEFAULT_PROJECT_ROOT,
        idempotencyKey: key,
      });

      await stream({
        taskId: resp.task_id,
        skillName: SKILL_NAME,
        onChunk: (text) => setChunks((prev) => [...prev, text]),
        onError: (err) => setError(err instanceof Error ? err.message : 'skill 错误'),
        onDone: (output) => setPrompt(output.text),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动封面生成失败');
    } finally {
      setRunning(false);
    }
  };

  const handleCopy = async () => {
    if (!prompt) return;
    try {
      await navigator.clipboard.writeText(prompt);
      show('已复制到剪贴板', 'success');
    } catch {
      show('复制失败，请手动选中', 'error');
    }
  };

  const loading = running || (idemKey != null && prompt == null && error == null);
  const currentText = prompt || chunks.join('');

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <AutoAwesomeIcon color="primary" />
        <Typography variant="h4">封面生成</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        输入书名 + 题材 + 文风 → 调 story-cover skill 生成 Midjourney / SD 友好的封面 prompt
      </Typography>

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <TextField
              label="书名"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              size="small"
              fullWidth
              placeholder="如：长安的荔枝"
            />

            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                题材
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                {GENRE_PRESETS.map((g) => (
                  <Chip
                    key={g}
                    size="small"
                    label={g}
                    onClick={() => setGenre(g)}
                    color={genre === g ? 'primary' : 'default'}
                    variant={genre === g ? 'filled' : 'outlined'}
                  />
                ))}
              </Stack>
              <TextField
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                size="small"
                fullWidth
                placeholder="自定义题材（点击上方 chip 快速选择）"
              />
            </Box>

            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                文风
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                {STYLE_PRESETS.map((s) => (
                  <Chip
                    key={s}
                    size="small"
                    label={s}
                    onClick={() => setStyle(s)}
                    color={style === s ? 'primary' : 'default'}
                    variant={style === s ? 'filled' : 'outlined'}
                  />
                ))}
              </Stack>
              <TextField
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                size="small"
                fullWidth
                placeholder="自定义文风"
              />
            </Box>

            <TextField
              label="补充说明（可选）"
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              size="small"
              fullWidth
              multiline
              rows={2}
              placeholder="如：主角是中年危机男人 / 关键意象：旧单车 / 时代背景：80年代"
            />
          </Stack>
        </CardContent>
        <Divider />
        <CardActions>
          <Button
            variant="contained"
            startIcon={loading ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
            onClick={() => void handleGenerate()}
            disabled={loading || !title.trim()}
          >
            {loading ? '生成中...' : '生成封面 Prompt'}
          </Button>
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => {
              setPrompt(null);
              setChunks([]);
              setError(null);
            }}
            disabled={loading}
          >
            清空
          </Button>
        </CardActions>
      </Card>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {currentText && (
        <Card variant="outlined" sx={{ mt: 2 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
              <Typography variant="h6">生成的 Prompt</Typography>
              <Stack direction="row" spacing={0.5}>
                <Tooltip title="复制到剪贴板">
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => void handleCopy()}
                      disabled={!prompt}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            </Stack>
            <Box
              sx={{
                p: 2,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'grey.50',
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                fontSize: 14,
                minHeight: 120,
              }}
            >
              {currentText}
            </Box>
            {loading && (
              <Alert severity="info" sx={{ mt: 1 }}>
                <Typography variant="caption">流式生成中 · 已收集 {chunks.length} 个 chunk</Typography>
              </Alert>
            )}
            {prompt && (
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip size="small" label={`${prompt.length} 字`} variant="outlined" />
                <Chip size="small" label="可直接用于 Midjourney / Stable Diffusion" variant="outlined" color="success" />
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      {!currentText && !loading && !error && (
        <Box sx={{ mt: 3 }}>
          <EmptyState
            title="开始生成"
            subtitle="填写书名 + 题材 + 文风，点击「生成封面 Prompt」"
          />
        </Box>
      )}
    </Container>
  );
}
