/**
 * NotFoundPage：404
 */

import { Link } from 'react-router-dom';
import { Box, Typography, Button, Stack } from '@mui/material';
import SearchOffIcon from '@mui/icons-material/SearchOff';

export function NotFoundPage() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 3,
      }}
    >
      <Stack alignItems="center" spacing={2}>
        <SearchOffIcon sx={{ fontSize: 80 }} color="disabled" />
        <Typography variant="h3">404</Typography>
        <Typography variant="body1" color="text.secondary">
          你访问的页面不存在
        </Typography>
        <Button component={Link} to="/" variant="contained">
          返回主页
        </Button>
      </Stack>
    </Box>
  );
}
