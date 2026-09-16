/**
 * ChapterListPage: 章节列表页 (Sprint 2 / V1.5.2 完整版)
 *
 * 范围:
 *   - 显示所有章节 (useChapters)
 *   - 显示当前项目状态 (useProjectStatus): character_count, last_updated_chapter
 *   - 点击章节 → 跳转 /write/:chapter
 *
 * 设计:
 *   - 用 React Query 自动 invalidate (useChapters staleTime=60s)
 *   - ChapterList 是纯组件 (props 控制), 本页只负责数据加载
 */

import { useNavigate } from 'react-router-dom';
import {
  Container,
  Box,
  Stack,
  Typography,
  Chip,
  Divider,
  CircularProgress,
  Alert,
} from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';

import { ChapterList } from '../components/chapter/ChapterList';
import { useChapters } from '../api/chapters';
import { useProjectStatus } from '../api/projects';
import { formatNumber } from '../utils/format';

export function ChapterListPage() {
  const navigate = useNavigate();
  const { data: chapters, isLoading, error } = useChapters();
  const { data: status } = useProjectStatus();

  // 从 status 推断当前激活章节 (last_updated_chapter)
  const activeChapter = status?.last_updated_chapter ?? null;

  // 章节状态映射 (后端暂无 status 字段, 用 last_updated_chapter 推断)
  const statusMap: Record<number, 'idle' | 'writing' | 'reviewed'> = {};
  if (chapters && activeChapter != null) {
    for (const c of chapters) {
      if (c.chapter === activeChapter) {
        statusMap[c.chapter] = 'writing';
      }
    }
  }

  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="warning">
          加载章节列表失败：{error instanceof Error ? error.message : '未知错误'}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <MenuBookIcon color="primary" />
          <Typography variant="h4">章节列表</Typography>
          {chapters && chapters.length > 0 && (
            <Chip
              size="small"
              label={`${chapters.length} 章`}
              variant="outlined"
              data-testid="chapter-count-chip"
            />
          )}
        </Stack>
      </Stack>

      {/* 项目状态卡 */}
      {status?.initialized && (
        <Box
          sx={{
            mb: 3,
            p: 2,
            bgcolor: 'background.paper',
            borderRadius: 1,
            border: 1,
            borderColor: 'divider',
          }}
          data-testid="project-status-summary"
        >
          <Stack direction="row" spacing={3} alignItems="center" flexWrap="wrap">
            <Box>
              <Typography variant="caption" color="text.secondary">
                项目
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {status.project_name ?? '—'}
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="caption" color="text.secondary">
                总字数
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {formatNumber(status.character_count)}
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="caption" color="text.secondary">
                上次更新
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {activeChapter != null ? `第 ${activeChapter} 章` : '—'}
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem />
            <Box>
              <Typography variant="caption" color="text.secondary">
                题材
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {status.genre ?? '—'}
              </Typography>
            </Box>
          </Stack>
        </Box>
      )}

      {/* 章节列表 */}
      <ChapterList
        chapters={chapters ?? []}
        activeChapter={activeChapter}
        statusMap={statusMap}
        onSelect={(ch) => navigate(`/write/${ch}`)}
      />
    </Container>
  );
}