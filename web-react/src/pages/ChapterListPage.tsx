/**
 * ChapterListPage：章节列表页（T05 占位）
 */

import { Container, Typography, Box, Alert } from '@mui/material';

export function ChapterListPage() {
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        章节列表
      </Typography>
      <Alert severity="info">
        <strong>T05 占位</strong> — 完整实现见 P1 sprint。
        数据源：<code>/api/chapters</code>。
      </Alert>
      <Box sx={{ mt: 3, p: 3, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary">
          章节列表 + 搜索 + 排序 + 批量操作 + 字数统计。
          接入 useChapters() hook（已实现于 src/api/chapters.ts）。
        </Typography>
      </Box>
    </Container>
  );
}
