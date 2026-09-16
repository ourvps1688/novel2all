/**
 * ExportPage：导出页（Sprint 3 / V1.5.3 完整实现）
 *
 * 功能：
 *   - 单章导出：选择章节 + 格式（md/txt/epub）→ 下载文件
 *   - 整书导出：输入书名/作者 + 格式 → 下载 EPUB（流式）
 *
 * 数据流：
 *   - useChapters(): 章节列表
 *   - axios 直接调 /api/chapter/{n}/export 与 /api/export（responseType: blob）
 *   - URL.createObjectURL + <a download> 触发下载
 */

import { useState } from 'react';
import axios from 'axios';
import {
  Container,
  Typography,
  Box,
  Alert,
  Card,
  CardContent,
  CardActions,
  Button,
  TextField,
  Stack,
  Divider,
  ToggleButtonGroup,
  ToggleButton,
  CircularProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import BookIcon from '@mui/icons-material/Book';

import { useChapters } from '../api/chapters';
import { useSnackbar } from '../hooks/useSnackbar';
import { useCurrentProject } from '../store/projectContext';
import { EmptyState } from '../components/common/EmptyState';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';

type ExportFormat = 'md' | 'txt' | 'epub';
const EXT_MAP: Record<ExportFormat, string> = { md: 'md', txt: 'txt', epub: 'epub' };

/** 触发浏览器下载一个 blob */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // 释放 URL（异步，避免 Safari 立即 revoke 失败）
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportPage() {
  const { show, error } = useSnackbar();
  const currentProject = useCurrentProject();
  const { data: chapters, isLoading: chaptersLoading } = useChapters(currentProject.path);
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [chapterFormat, setChapterFormat] = useState<ExportFormat>('md');
  const [bookFormat, setBookFormat] = useState<ExportFormat>('epub');
  const [bookTitle, setBookTitle] = useState('');
  const [bookAuthor, setBookAuthor] = useState('');
  const [downloadingChapter, setDownloadingChapter] = useState(false);
  const [downloadingBook, setDownloadingBook] = useState(false);

  // 默认选中第一个章节
  const activeChapter = selectedChapter ?? chapters?.[0]?.chapter ?? null;

  /** 单章导出 */
  const handleExportChapter = async () => {
    if (activeChapter == null) return;
    setDownloadingChapter(true);
    try {
      const res = await axios.get(`/api/chapter/${activeChapter}/export`, {
        params: { format: chapterFormat, project_root: currentProject.path },
        responseType: 'blob',
      });
      const filename = `chapter_${activeChapter}.${EXT_MAP[chapterFormat]}`;
      downloadBlob(res.data as Blob, filename);
      show(`已下载：${filename}`, 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '导出失败';
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        error('项目未初始化或章节不存在');
      } else {
        error(msg);
      }
    } finally {
      setDownloadingChapter(false);
    }
  };

  /** 整书导出 */
  const handleExportBook = async () => {
    if (!bookTitle.trim()) {
      error('请输入书名');
      return;
    }
    setDownloadingBook(true);
    try {
      const res = await axios.get('/api/export', {
        params: {
          format: bookFormat,
          project_root: currentProject.path,
          title: bookTitle,
          author: bookAuthor || '未知作者',
        },
        responseType: 'blob',
      });
      // 文件名：<title>.<ext>（去非法字符）
      const safeTitle = bookTitle.replace(/[\\/:*?"<>|]/g, '_');
      const filename = `${safeTitle}.${EXT_MAP[bookFormat]}`;
      downloadBlob(res.data as Blob, filename);
      show(`已下载：${filename}`, 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '导出失败';
      error(msg);
    } finally {
      setDownloadingBook(false);
    }
  };

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        导出
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        导出单章或整书为 Markdown / TXT / EPUB
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
        {/* ==================== 单章导出 ==================== */}
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              单章导出
            </Typography>

            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
              选择章节 + 格式 → 浏览器下载
            </Typography>

            {chaptersLoading ? (
              <LoadingSkeleton variant="card" />
            ) : !chapters || chapters.length === 0 ? (
              <EmptyState title="暂无章节" subtitle="请先初始化项目并写至少一章" />
            ) : (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
                    章节
                  </Typography>
                  <List
                    dense
                    disablePadding
                    sx={{ maxHeight: 240, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1 }}
                  >
                    {chapters.map((ch) => (
                      <ListItem key={ch.chapter} disablePadding>
                        <ListItemButton
                          selected={ch.chapter === activeChapter}
                          onClick={() => setSelectedChapter(ch.chapter)}
                        >
                          <ListItemText
                            primary={`第 ${ch.chapter} 章`}
                            secondary={`${ch.char_count ?? 0} 字`}
                          />
                        </ListItemButton>
                      </ListItem>
                    ))}
                  </List>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                    格式
                  </Typography>
                  <ToggleButtonGroup
                    value={chapterFormat}
                    exclusive
                    onChange={(_, v) => v && setChapterFormat(v as ExportFormat)}
                    size="small"
                    color="primary"
                  >
                    <ToggleButton value="md">Markdown</ToggleButton>
                    <ToggleButton value="txt">TXT</ToggleButton>
                    <ToggleButton value="epub">EPUB</ToggleButton>
                  </ToggleButtonGroup>
                </Box>
              </Stack>
            )}
          </CardContent>
          <Divider />
          <CardActions>
            <Button
              variant="contained"
              startIcon={downloadingChapter ? <CircularProgress size={16} /> : <DownloadIcon />}
              onClick={() => void handleExportChapter()}
              disabled={activeChapter == null || downloadingChapter}
            >
              {downloadingChapter ? '下载中...' : `下载第 ${activeChapter ?? '?'} 章 (${chapterFormat.toUpperCase()})`}
            </Button>
          </CardActions>
        </Card>

        {/* ==================== 整书导出 ==================== */}
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
              <BookIcon />
              <Typography variant="h6">整书导出</Typography>
            </Stack>

            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
              自动发现所有章节 + 拼接 / 打包成完整作品
            </Typography>

            <Stack spacing={2}>
              <TextField
                label="书名"
                required
                value={bookTitle}
                onChange={(e) => setBookTitle(e.target.value)}
                size="small"
                fullWidth
                error={!bookTitle.trim()}
                helperText={!bookTitle.trim() ? '必填' : ''}
              />
              <TextField
                label="作者"
                value={bookAuthor}
                onChange={(e) => setBookAuthor(e.target.value)}
                size="small"
                fullWidth
                placeholder="默认：未知作者"
              />
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                  格式
                </Typography>
                <ToggleButtonGroup
                  value={bookFormat}
                  exclusive
                  onChange={(_, v) => v && setBookFormat(v as ExportFormat)}
                  size="small"
                  color="primary"
                >
                  <ToggleButton value="epub">EPUB（推荐）</ToggleButton>
                  <ToggleButton value="md">Markdown</ToggleButton>
                  <ToggleButton value="txt">TXT</ToggleButton>
                </ToggleButtonGroup>
              </Box>

              <Alert severity="info" sx={{ py: 0.5 }}>
                <Typography variant="caption">
                  EPUB 自动包含导航 + 元数据；Markdown/TXT 是单文件拼接。
                </Typography>
              </Alert>
            </Stack>
          </CardContent>
          <Divider />
          <CardActions>
            <Button
              variant="contained"
              startIcon={downloadingBook ? <CircularProgress size={16} /> : <DownloadIcon />}
              onClick={() => void handleExportBook()}
              disabled={downloadingBook || !bookTitle.trim()}
            >
              {downloadingBook ? '下载中...' : `下载整书 (${bookFormat.toUpperCase()})`}
            </Button>
          </CardActions>
        </Card>
      </Stack>
    </Container>
  );
}
