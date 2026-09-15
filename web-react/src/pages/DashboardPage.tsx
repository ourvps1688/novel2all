/**
 * DashboardPage：主页（默认进入）
 *
 * 布局：
 *  - 已初始化：4 卡片 grid（Current / Progress / Cache / Cost）
 *  - 未初始化：OnboardingWizard 替代 4 卡片
 *  - 加载中：skeleton 卡片
 */

import { Box, Container, Grid, Typography, Stack, Skeleton } from '@mui/material';

import { useProjectStatus } from '../api/projects';
import { CurrentChapterCard } from '../components/dashboard/CurrentChapterCard';
import { ProjectProgressCard } from '../components/dashboard/ProjectProgressCard';
import { CacheStatusCard } from '../components/dashboard/CacheStatusCard';
import { TodayCostCard } from '../components/dashboard/TodayCostCard';
import { OnboardingWizard } from '../components/dashboard/OnboardingWizard';

export function DashboardPage() {
  const { data: status, isLoading } = useProjectStatus();

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Typography variant="h4" gutterBottom>
          主页
        </Typography>
        <Grid container spacing={3}>
          {[0, 1, 2, 3].map((i) => (
            <Grid item xs={12} sm={6} md={3} key={i}>
              <Skeleton variant="rectangular" height={260} sx={{ borderRadius: 2 }} />
            </Grid>
          ))}
        </Grid>
      </Container>
    );
  }

  // 未初始化 → 引导
  if (!status?.initialized) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Stack spacing={3}>
          <Typography variant="h4">主页</Typography>
          <OnboardingWizard />
        </Stack>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h4">{status.project_name ?? '主页'}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {status.genre && `类型：${status.genre}`}
            {status.style_anchor && ` · 风格：${status.style_anchor}`}
          </Typography>
        </Box>

        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <CurrentChapterCard />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <ProjectProgressCard />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <CacheStatusCard />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TodayCostCard />
          </Grid>
        </Grid>
      </Stack>
    </Container>
  );
}
