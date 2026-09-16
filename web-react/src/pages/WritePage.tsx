/**
 * WritePage: 写作主界面 (Sprint 2 / V1.5.2 完整版)
 *
 * 布局 (3 列):
 *   ┌────────────────────────────────────────────────────────┐
 *   │ Header: ← 返回 | 第 N 章 | 状态                          │
 *   ├──────────┬────────────────────────────────────┬───────────┤
 *   │ 章节列表 │ ChapterEditor (Tiptap + 工具栏)    │ 状态卡    │
 *   │ (左 20%) │                                  │ 字数 / 模型│
 *   │          │                                  │ 项目状态  │
 *   │          │                                  │           │
 *   └──────────┴────────────────────────────────────┴───────────┘
 *
 * 功能:
 *   - URL /write → 重定向到 /write/1 (或最后一个章节后一章)
 *   - 章节列表点击切换章节
 *   - AI 重写选区 / AI 插入段落 → 显示 Modal + Diff 预览 → 确认后写入编辑器
 *   - AI 续写 → SSE 流式 (8 阶段)
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Grid,
  Stack,
  Typography,
  CircularProgress,
  Divider,
  Card,
  CardContent,
  Chip,
  Button,
  Alert,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MenuBookIcon from '@mui/icons-material/MenuBook';

import { useChapters, useRewriteChapter, useInsertChapter } from '../api/chapters';
import { useProjectStatus } from '../api/projects';
import { useCurrentModel } from '../api/models';
import { useSnackbar } from '../hooks/useSnackbar';
import { useQueryClient } from '@tanstack/react-query';

import { ChapterList } from '../components/chapter/ChapterList';
import {
  ChapterEditor,
  type ChapterEditorHandle,
} from '../components/write/ChapterEditor';
import { AIRewriteModal } from '../components/write/AIRewriteModal';
import { AIInsertModal } from '../components/write/AIInsertModal';
import { WriteProgress } from '../components/write/WriteProgress';
import { useWriteStream } from '../hooks/useSSE';
import { formatNumber } from '../utils/format';
import type { TextSelection } from '../types/chapters';

export function WritePage() {
  const { chapter: chapterParam } = useParams<{ chapter?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const snackbar = useSnackbar();

  // 数据
  const { data: chapters, isLoading: chaptersLoading } = useChapters();
  const { data: status } = useProjectStatus();
  const { data: currentModel } = useCurrentModel();

  // 当前章节号 (URL 解析)
  const currentChapter = chapterParam ? parseInt(chapterParam, 10) : null;
  const validChapter =
    currentChapter != null && !Number.isNaN(currentChapter) && currentChapter > 0;

  // URL 重定向: /write → /write/1 (或最后一章后)
  useEffect(() => {
    if (!validChapter && chapters && chapters.length > 0) {
      const lastChapter = chapters[chapters.length - 1]?.chapter ?? 0;
      navigate(`/write/${lastChapter + 1}`, { replace: true });
    } else if (!validChapter) {
      navigate('/write/1', { replace: true });
    }
  }, [validChapter, chapters, navigate]);

  // 选区 (传给 AI 工具栏)
  const [selection, setSelection] = useState<TextSelection | null>(null);

  // ChapterEditor ref (暴露给 AI 操作调用)
  const editorRef = useRef<ChapterEditorHandle | null>(null);

  // AI 重写状态
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [rewriteInstruction, setRewriteInstruction] = useState('改写得更生动自然');
  const rewriteMutation = useRewriteChapter();

  // AI 插入状态
  const [insertOpen, setInsertOpen] = useState(false);
  const [insertInstruction, setInsertInstruction] = useState('自然衔接上下文的过渡段落');
  const insertMutation = useInsertChapter();

  // SSE 流 (AI 续写)
  const stream = useWriteStream();

  // 章节列表 statusMap (推断)
  const statusMap = useMemo(() => {
    const map: Record<number, 'idle' | 'writing' | 'reviewed'> = {};
    if (chapters && currentChapter != null) {
      for (const c of chapters) {
        if (c.chapter === currentChapter) map[c.chapter] = 'writing';
      }
    }
    return map;
  }, [chapters, currentChapter]);

  // AI 重写打开
  const handleOpenRewrite = useCallback(() => {
    if (!selection || selection.text.length === 0) {
      snackbar.warning('请先选中要重写的段落');
      return;
    }
    setRewriteOpen(true);
    setRewriteInstruction('改写得更生动自然');
  }, [selection, snackbar]);

  // AI 重写确认应用 (替换编辑器选区)
  const handleApplyRewrite = useCallback(() => {
    if (!rewriteMutation.data) {
      snackbar.error('重写结果为空');
      return;
    }
    editorRef.current?.replaceSelection(rewriteMutation.data.rewritten);
    setRewriteOpen(false);
    void qc.invalidateQueries({ queryKey: ['chapter', currentChapter] });
    snackbar.success('已应用重写');
  }, [rewriteMutation.data, snackbar, qc, currentChapter]);

  // AI 插入打开
  const handleOpenInsert = useCallback(() => {
    if (!selection) {
      snackbar.warning('请先选择插入位置');
      return;
    }
    setInsertOpen(true);
    setInsertInstruction('自然衔接上下文的过渡段落');
  }, [selection, snackbar]);

  // AI 插入确认应用
  const handleApplyInsert = useCallback(() => {
    if (!insertMutation.data || !selection) {
      snackbar.error('插入结果为空');
      return;
    }
    editorRef.current?.insertAtPosition(selection.from, insertMutation.data.inserted);
    setInsertOpen(false);
    void qc.invalidateQueries({ queryKey: ['chapter', currentChapter] });
    snackbar.success('已插入内容');
  }, [insertMutation.data, selection, snackbar, qc, currentChapter]);

  // AI 续写启动
  const handleStartContinue = useCallback(() => {
    if (!currentChapter) return;
    stream.start({
      chapter: currentChapter,
      minChars: 2000,
      projectRoot: '.',
    });
  }, [stream, currentChapter]);

  // SSE done 后自动刷新
  useEffect(() => {
    if (stream.progress.phase === 'done') {
      void qc.invalidateQueries({ queryKey: ['chapter', currentChapter] });
      void qc.invalidateQueries({ queryKey: ['chapters'] });
      void qc.invalidateQueries({ queryKey: ['status'] });
      snackbar.success(`AI 续写完成 · ${formatNumber(stream.progress.charsWritten)} 字`);
    }
    if (stream.progress.phase === 'error') {
      snackbar.error(`AI 续写失败: ${stream.progress.errorMessage ?? '未知错误'}`);
    }
  }, [stream.progress.phase, qc, currentChapter, snackbar, stream.progress.charsWritten, stream.progress.errorMessage]);

  // insert modal 的上下文 (插入位置前后各 100 字) - 必须在 early return 之前
  const insertContext = useMemo(() => {
    if (!selection) return '';
    const text = editorRef.current?.getPlainText() ?? '';
    const start = Math.max(0, selection.from - 100);
    const end = Math.min(text.length, selection.to + 100);
    return text.slice(start, end);
  }, [selection]);

  if (chaptersLoading || !validChapter || currentChapter == null) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 480 }}>
        <CircularProgress />
      </Box>
    );
  }

  // 当前 rewrite modal 的原文 / 上下文 (从编辑器获取)
  const rewriteOriginal = selection?.text ?? '';

  return (
    <Box sx={{ p: 2, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1.5 }}
        data-testid="write-page-header"
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Button
            size="small"
            startIcon={<ArrowBackIcon fontSize="small" />}
            onClick={() => navigate('/chapters')}
            data-testid="write-back-button"
          >
            返回章节列表
          </Button>
          <MenuBookIcon color="primary" />
          <Typography variant="h5" fontWeight={600}>
            第 {currentChapter} 章
          </Typography>
          {stream.streaming && (
            <Chip
              size="small"
              color="primary"
              label="AI 续写中..."
              data-testid="write-streaming-chip"
            />
          )}
        </Stack>
      </Stack>

      {/* 主体 3 列 */}
      <Grid container spacing={1.5} sx={{ flex: 1, minHeight: 0 }}>
        {/* 左: 章节列表 */}
        <Grid item xs={12} md={2.5} sx={{ minHeight: 0 }}>
          <Card variant="outlined" sx={{ height: '100%', overflow: 'auto' }}>
            <CardContent sx={{ pb: 1 }}>
              <Typography variant="overline" color="text.secondary">
                章节 ({chapters?.length ?? 0})
              </Typography>
            </CardContent>
            <Divider />
            <Box sx={{ p: 1 }}>
              <ChapterList
                chapters={chapters ?? []}
                activeChapter={currentChapter}
                statusMap={statusMap}
                onSelect={(ch) => navigate(`/write/${ch}`)}
              />
            </Box>
          </Card>
        </Grid>

        {/* 中: Tiptap 编辑器 */}
        <Grid item xs={12} md={6.5} sx={{ minHeight: 0 }}>
          <ChapterEditor
            ref={editorRef}
            chapter={currentChapter}
            onSelectionChange={setSelection}
            onSaved={() => {
              void qc.invalidateQueries({ queryKey: ['chapters'] });
            }}
          />
          {/* AI 操作触发按钮 (额外快捷入口, 工具栏内已集成) */}
          <Stack direction="row" spacing={1} sx={{ mt: 1 }} justifyContent="flex-end">
            <Button
              size="small"
              variant="outlined"
              onClick={handleOpenRewrite}
              disabled={!selection}
              data-testid="write-page-rewrite-button"
            >
              AI 重写选区
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={handleOpenInsert}
              disabled={!selection}
              data-testid="write-page-insert-button"
            >
              AI 插入段落
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={handleStartContinue}
              disabled={stream.streaming}
              data-testid="write-page-continue-button"
            >
              {stream.streaming ? '续写中...' : 'AI 续写 (8 阶段)'}
            </Button>
          </Stack>
        </Grid>

        {/* 右: 状态卡 */}
        <Grid item xs={12} md={3} sx={{ minHeight: 0 }}>
          <Card variant="outlined" sx={{ height: '100%', overflow: 'auto' }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">
                写作状态
              </Typography>
              <Stack spacing={2} sx={{ mt: 1.5 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    项目
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {status?.project_name ?? '—'}
                  </Typography>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    当前字数 (本章)
                  </Typography>
                  <Typography variant="h6" fontWeight={700}>
                    {formatNumber(status?.character_count ?? 0)}
                  </Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    总字数 (项目)
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {formatNumber(status?.character_count ?? 0)}
                  </Typography>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    当前模型
                  </Typography>
                  <Typography variant="body2" fontWeight={600} data-testid="current-model-label">
                    {currentModel?.model ?? '—'}
                  </Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    文风锚点
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
                    {status?.style_anchor ?? '—'}
                  </Typography>
                </Box>

                <Divider />

                {/* AI 续写进度 */}
                {stream.streaming && (
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                      8 阶段进度
                    </Typography>
                    <WriteProgress progress={stream.progress} detailed />
                  </Box>
                )}

                {!stream.streaming && stream.progress.phase === 'idle' && (
                  <Alert severity="info" variant="outlined">
                    点击 "AI 续写" 启动 8 阶段写作流。
                  </Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* AI 重写 Modal */}
      <AIRewriteModal
        open={rewriteOpen}
        chapter={currentChapter}
        original={rewriteOriginal}
        rewritten={rewriteMutation.data?.rewritten ?? null}
        instruction={rewriteInstruction}
        loading={rewriteMutation.isPending}
        errorMsg={rewriteMutation.error ? (rewriteMutation.error instanceof Error ? rewriteMutation.error.message : '重写失败') : null}
        onInstructionChange={setRewriteInstruction}
        onApply={handleApplyRewrite}
        onReject={() => {
          setRewriteOpen(false);
          rewriteMutation.reset();
        }}
      />

      {/* AI 插入 Modal */}
      <AIInsertModal
        open={insertOpen}
        chapter={currentChapter}
        position={selection?.from ?? 0}
        context={insertContext}
        inserted={insertMutation.data?.inserted ?? null}
        instruction={insertInstruction}
        loading={insertMutation.isPending}
        errorMsg={insertMutation.error ? (insertMutation.error instanceof Error ? insertMutation.error.message : '插入失败') : null}
        onInstructionChange={setInsertInstruction}
        onApply={handleApplyInsert}
        onReject={() => {
          setInsertOpen(false);
          insertMutation.reset();
        }}
      />
    </Box>
  );
}