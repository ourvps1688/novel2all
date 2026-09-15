/**
 * ReviewQueuePage：审查队列页（T05 占位）
 */

import { Container, Typography, Box, Alert } from '@mui/material';

export function ReviewQueuePage() {
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        审查队列
      </Typography>
      <Alert severity="info">
        <strong>T07 占位</strong> — 完整实现见 P1 sprint。
      </Alert>
      <Box sx={{ mt: 3, p: 3, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary">
          4-agent 审查队列 + verdict diff + Idempotency-Key 自动生成。
          接入 useReviewChapter() hook（已实现）。
        </Typography>
      </Box>
    </Container>
  );
}
