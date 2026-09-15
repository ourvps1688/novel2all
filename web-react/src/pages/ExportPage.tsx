/**
 * ExportPage：导出页（T05 占位）
 */

import { Container, Typography, Box, Alert } from '@mui/material';

export function ExportPage() {
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        导出
      </Typography>
      <Alert severity="info">
        <strong>T08 占位</strong> — 完整实现见 P1 sprint。
      </Alert>
      <Box sx={{ mt: 3, p: 3, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary">
          单章导出（md/txt/epub）+ 整书导出 + 流式下载。
          接入 <code>/api/chapter/&#123;n&#125;/export?format=...</code> 和 <code>/api/export</code>。
        </Typography>
      </Box>
    </Container>
  );
}
