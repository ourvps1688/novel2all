/**
 * ChapterCard: 单章节卡片 (Sprint 2)
 *
 * 用途:
 *   - 在 ChapterList 中作为单个章节项
 *   - 显示章节号、文件名、字数、首行预览、状态
 *   - 点击触发 onSelect 回调 (跳转 /write/:chapter)
 *
 * 设计:
 *   - 纯展示组件, 数据通过 props 传入
 *   - 不依赖 React Query / 编辑器
 *   - selected 状态由父组件控制 (ListItemButton)
 */

import { Card, CardActionArea, CardContent, Stack, Typography, Chip, Box } from '@mui/material';
import EditNoteIcon from '@mui/icons-material/EditNote';

import { formatNumber } from '../../utils/format';

export interface ChapterCardData {
  chapter: number;
  filename: string;
  char_count: number;
  first_line: string;
}

export interface ChapterCardProps {
  chapter: ChapterCardData;
  selected?: boolean;
  /**
   * 章节状态: 'idle' | 'writing' | 'reviewed' (后端暂无 status 字段, 前端推断)
   * - 'writing': 当前正在写 (由父组件根据 activeChapter 判断)
   */
  status?: 'idle' | 'writing' | 'reviewed';
  onClick?: () => void;
}

export function ChapterCard({
  chapter,
  selected = false,
  status = 'idle',
  onClick,
}: ChapterCardProps) {
  const statusChip = (() => {
    if (status === 'writing') return <Chip size="small" label="✍ 进行中" color="primary" variant="outlined" />;
    if (status === 'reviewed') return <Chip size="small" label="✓ 已审" color="success" variant="outlined" />;
    return null;
  })();

  return (
    <Card
      variant="outlined"
      data-testid={`chapter-card-${chapter.chapter}`}
      sx={{
        borderColor: selected ? 'primary.main' : 'divider',
        borderWidth: selected ? 2 : 1,
        transition: 'border-color 0.2s, box-shadow 0.2s',
        '&:hover': { boxShadow: 1 },
      }}
    >
      <CardActionArea
        onClick={onClick}
        disabled={!onClick}
        aria-label={`打开第 ${chapter.chapter} 章`}
      >
        <CardContent sx={{ pb: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <EditNoteIcon fontSize="small" color={selected ? 'primary' : 'action'} />
              <Typography variant="subtitle2" fontWeight={selected ? 700 : 600}>
                第 {chapter.chapter} 章
              </Typography>
            </Stack>
            {statusChip}
          </Stack>

          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              minHeight: '2.4em',
            }}
            title={chapter.first_line}
          >
            {chapter.first_line || '（暂无内容）'}
          </Typography>

          <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="caption" color="text.secondary">
              {chapter.filename}
            </Typography>
            <Typography variant="caption" fontWeight={600} color={selected ? 'primary.main' : 'text.secondary'}>
              {formatNumber(chapter.char_count)} 字
            </Typography>
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}