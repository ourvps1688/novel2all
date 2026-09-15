/**
 * CurrentChapterCard：当前章节
 *
 * 数据源：/api/chapters（取最后一个有内容的）+ /api/chapter/{n}/content
 * 显示：章节号 / 标题 / 字数 / "继续写"按钮
 */

import { useNavigate } from 'react-router-dom';
import { Card, CardContent, Typography, Stack, Box, Skeleton, Button } from '@mui/material';
import EditNoteIcon from '@mui/icons-material/EditNote';

import { useChapters } from '../../api/chapters';
import { formatChapter, formatNumber, truncate } from '../../utils/format';

export function CurrentChapterCard() {
  const navigate = useNavigate();
  const { data: chapters, isLoading } = useChapters();

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="text" width="60%" height={40} />
          <Skeleton variant="rectangular" height={36} sx={{ mt: 2 }} />
        </CardContent>
      </Card>
    );
  }

  const list = chapters ?? [];
  const last = list.length > 0 ? list[list.length - 1] : null;
  const nextChapter = (last?.chapter ?? 0) + 1;

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <EditNoteIcon color="primary" />
            <Typography variant="h6">当前章节</Typography>
          </Stack>

          {last ? (
            <>
              <Box>
                <Typography variant="overline" color="text.secondary">
                  最新完成
                </Typography>
                <Typography variant="h5" sx={{ mt: 0.5 }}>
                  {formatChapter(last.chapter)}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {truncate(last.first_line, 60)}
                </Typography>
              </Box>

              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" color="text.secondary">
                  字数：
                </Typography>
                <Typography variant="body1" fontWeight={600}>
                  {formatNumber(last.char_count)}
                </Typography>
              </Stack>

              <Button
                variant="contained"
                onClick={() => navigate(`/write/${nextChapter}`)}
                fullWidth
              >
                继续写第 {nextChapter} 章 →
              </Button>
            </>
          ) : (
            <Box sx={{ py: 2 }}>
              <Typography variant="body2" color="text.secondary">
                还没有章节。
              </Typography>
              <Button
                variant="contained"
                sx={{ mt: 2 }}
                onClick={() => navigate('/write/1')}
                fullWidth
              >
                开始第 1 章
              </Button>
            </Box>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
