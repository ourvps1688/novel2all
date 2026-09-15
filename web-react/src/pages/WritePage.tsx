/**
 * WritePage：写作页（核心 MVP）
 *
 * MVP 范围（P1-8 修复）：
 *   左：ChapterList（用 useChapters 列出全部章节，点击切换）
 *   中：textarea 编辑器 + 字数统计 + 保存按钮（useSaveChapter）
 *   右：ChapterStatus（字数 / 模型 / 风格 — 从 useProjectStatus 读）
 *
 * 不实现：
 *   - Tiptap 富文本（P1 T06 增量）
 *   - AI 重写 / 插入 / 审查（T06/T07 增量）
 *   - 自动保存 / 拖拽 / undo（T06 增量）
 *
 * URL: /write 或 /write/:chapter
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Grid,
  CircularProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Typography,
  TextField,
  Stack,
  Divider,
  Alert,
} from '@mui/material';

import { useChapters, useChapterContent, useSaveChapter } from '../api/chapters';
import type { Chapter } from '../api/chapters';
import { useProjectStatus } from '../api/projects';
import { useCurrentModel } from '../api/models';
import { useSnackbar } from '../hooks/useSnackbar';
import { LoadingButton } from '../components/common/LoadingButton';
import { formatNumber } from '../utils/format';

export function WritePage() {
  const { chapter: chapterParam } = useParams<{ chapter?: string }>();
  const navigate = useNavigate();
  const { data: chapters, isLoading: chaptersLoading } = useChapters();
  const { data: status } = useProjectStatus();
  const { data: currentModel } = useCurrentModel();
  const snackbar = useSnackbar();

  // 当前章节号（解析 URL 参数）
  const currentChapter = chapterParam ? parseInt(chapterParam, 10) : null;
  const validChapter = currentChapter != null && !Number.isNaN(currentChapter) && currentChapter > 0;

  // 默认跳到第一个章节或最后一章后
  useEffect(() => {
    if (!validChapter && chapters && chapters.length > 0) {
      navigate(`/write/${chapters[chapters.length - 1]!.chapter + 1}`, { replace: true });
    } else if (!validChapter) {
      navigate('/write/1', { replace: true });
    }
  }, [validChapter, chapters, navigate]);

  if (chaptersLoading || !validChapter) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      <Grid container spacing={2} sx={{ minHeight: 'calc(100vh - 96px)' }}>
        <Grid item xs={12} md={2}>
          <ChapterList
            chapters={chapters ?? []}
            activeChapter={currentChapter!}
            onSelect={(ch) => navigate(`/write/${ch}`)}
          />
        </Grid>

        <Grid item xs={12} md={7}>
          <ChapterEditor chapterId={currentChapter!} onSaved={() => snackbar.success('已保存')} />
        </Grid>

        <Grid item xs={12} md={3}>
          <ChapterStatus
            projectName={status?.project_name ?? null}
            styleAnchor={status?.style_anchor ?? null}
            currentModel={currentModel?.model ?? null}
          />
        </Grid>
      </Grid>
    </Box>
  );
}

// ============ ChapterList（左列）============

interface ChapterListProps {
  chapters: Chapter[];
  activeChapter: number;
  onSelect: (chapter: number) => void;
}

function ChapterList({ chapters, activeChapter, onSelect }: ChapterListProps) {
  return (
    <Box
      sx={{
        p: 1,
        bgcolor: 'background.paper',
        borderRadius: 1,
        border: 1,
        borderColor: 'divider',
        height: '100%',
        overflow: 'auto',
      }}
    >
      <Typography variant="subtitle2" sx={{ p: 1, color: 'text.secondary' }}>
        章节列表（{chapters.length}）
      </Typography>
      <Divider />
      {chapters.length === 0 ? (
        <Box sx={{ p: 2 }}>
          <Typography variant="body2" color="text.secondary">
            还没有章节
          </Typography>
        </Box>
      ) : (
        <List dense disablePadding>
          {chapters.map((c) => (
            <ListItem key={c.chapter} disablePadding>
              <ListItemButton
                selected={c.chapter === activeChapter}
                onClick={() => onSelect(c.chapter)}
              >
                <ListItemText
                  primary={`第 ${c.chapter} 章`}
                  secondary={`${formatNumber(c.char_count)} 字`}
                  primaryTypographyProps={{ variant: 'body2' }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}

// ============ ChapterEditor（中列：textarea + 保存）============

interface ChapterEditorProps {
  chapterId: number;
  onSaved: () => void;
}

function ChapterEditor({ chapterId, onSaved }: ChapterEditorProps) {
  const { data: content, isLoading } = useChapterContent(chapterId);
  const saveMutation = useSaveChapter();
  const snackbar = useSnackbar();
  const [text, setText] = useState('');
  const [dirty, setDirty] = useState(false);

  // 当加载新章节时重置本地 state
  useEffect(() => {
    if (content) {
      setText(content.content);
      setDirty(false);
    }
  }, [content?.chapter]); // eslint-disable-line react-hooks/exhaustive-deps

  const charCount = useMemo(() => [...text].length, [text]);

  const handleSave = async (): Promise<void> => {
    try {
      await saveMutation.mutateAsync({ chapter: chapterId, content: text });
      setDirty(false);
      onSaved();
    } catch (err) {
      snackbar.error(err instanceof Error ? err.message : '保存失败');
    }
  };

  if (isLoading) {
    return (
      <Box
        sx={{
          p: 2,
          bgcolor: 'background.paper',
          borderRadius: 1,
          border: 1,
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 400,
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        p: 2,
        bgcolor: 'background.paper',
        borderRadius: 1,
        border: 1,
        borderColor: 'divider',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 400,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="h6">第 {chapterId} 章</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" color={dirty ? 'warning.main' : 'text.secondary'}>
            {dirty ? '● 未保存' : '已保存'} · {formatNumber(charCount)} 字
          </Typography>
          <LoadingButton
            variant="contained"
            size="small"
            onClick={handleSave}
            loading={saveMutation.isPending}
            disabled={!dirty}
          >
            保存
          </LoadingButton>
        </Stack>
      </Stack>

      <TextField
        multiline
        minRows={18}
        maxRows={30}
        fullWidth
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setDirty(true);
        }}
        placeholder="开始写作…（Ctrl+S 保存）"
        sx={{
          flex: 1,
          '& .MuiInputBase-root': {
            alignItems: 'flex-start',
            fontFamily: '"Source Han Serif", "Songti SC", "SimSun", serif',
            fontSize: 16,
            lineHeight: 1.8,
          },
        }}
      />

      <Alert severity="info" sx={{ mt: 1 }} variant="outlined">
        MVP 版本：纯文本编辑。T06 将升级为 Tiptap 富文本 + AI 工具栏（重写 / 插入 / 审查）。
      </Alert>
    </Box>
  );
}

// ============ ChapterStatus（右列）============

interface ChapterStatusProps {
  projectName: string | null;
  styleAnchor: string | null;
  currentModel: string | null;
}

function ChapterStatus({ projectName, styleAnchor, currentModel }: ChapterStatusProps) {
  return (
    <Box
      sx={{
        p: 2,
        bgcolor: 'background.paper',
        borderRadius: 1,
        border: 1,
        borderColor: 'divider',
        height: '100%',
      }}
    >
      <Typography variant="subtitle1" gutterBottom>
        章节状态
      </Typography>
      <Divider sx={{ mb: 2 }} />

      <Stack spacing={2}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            项目
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {projectName ?? '—'}
          </Typography>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary">
            风格锚点
          </Typography>
          <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
            {styleAnchor ?? '—'}
          </Typography>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary">
            当前模型
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {currentModel ?? '—'}
          </Typography>
        </Box>

        <Divider />

        <Typography variant="caption" color="text.secondary">
          写作阶段 / 花费 / 预估时间见 T06
        </Typography>
      </Stack>
    </Box>
  );
}
