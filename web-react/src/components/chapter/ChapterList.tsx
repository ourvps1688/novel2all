/**
 * ChapterList: 章节卡片网格 (Sprint 2)
 *
 * 用途:
 *   - 列出全部章节, 按章节号升序
 *   - 显示当前激活章节 (selected)
 *   - 支持搜索过滤 + 空状态
 *
 * 设计:
 *   - 纯组件, 数据通过 props 传入 (避免直接耦合 useChapters)
 *   - 父组件 (ChapterListPage / WritePage) 提供数据 + 选中回调
 */

import { useMemo, useState } from 'react';
import { Box, Stack, TextField, InputAdornment, Grid } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';

import { ChapterCard, type ChapterCardData } from './ChapterCard';
import { EmptyState } from '../common/EmptyState';

export interface ChapterListProps {
  chapters: ChapterCardData[];
  activeChapter?: number | null;
  onSelect?: (chapter: number) => void;
  /** 章节状态映射 (chapter# → status) */
  statusMap?: Record<number, 'idle' | 'writing' | 'reviewed'>;
}

export function ChapterList({
  chapters,
  activeChapter = null,
  onSelect,
  statusMap = {},
}: ChapterListProps) {
  const [search, setSearch] = useState('');

  // 按章节号升序 + 搜索过滤
  const filtered = useMemo(() => {
    const sorted = [...chapters].sort((a, b) => a.chapter - b.chapter);
    if (!search.trim()) return sorted;
    const q = search.trim().toLowerCase();
    return sorted.filter(
      (c) =>
        String(c.chapter).includes(q) ||
        c.filename.toLowerCase().includes(q) ||
        c.first_line.toLowerCase().includes(q),
    );
  }, [chapters, search]);

  if (chapters.length === 0) {
    return (
      <Box sx={{ p: 2 }}>
        <EmptyState
          title="还没有章节"
          subtitle="使用 AI 续写 skill 创建第一个章节"
          minHeight={240}
        />
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} alignItems="center">
        <TextField
          size="small"
          fullWidth
          placeholder="搜索章节号/文件名/首行"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          inputProps={{ 'aria-label': '搜索章节' }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
      </Stack>

      {filtered.length === 0 ? (
        <EmptyState title="无匹配章节" subtitle={`没有包含 "${search}" 的章节`} minHeight={200} />
      ) : (
        <Grid container spacing={1.5} data-testid="chapter-list-grid">
          {filtered.map((c) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={c.chapter}>
              <ChapterCard
                chapter={c}
                selected={c.chapter === activeChapter}
                status={statusMap[c.chapter] ?? 'idle'}
                onClick={onSelect ? () => onSelect(c.chapter) : undefined}
              />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}