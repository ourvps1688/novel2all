/**
 * DashboardPage：主页（默认进入）
 *
 * 布局：
 *  - 已初始化：4 卡片 grid（Current / Progress / Cache / Cost）+ Quick Start 4 skill
 *  - 未初始化：OnboardingWizard 替代 4 卡片
 *  - 加载中：skeleton 卡片
 */

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Grid,
  Typography,
  Stack,
  Skeleton,
  Card,
  CardActionArea,
  CardContent,
  Chip,
} from '@mui/material';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';

import { useProjectStatus } from '../api/projects';
import { useSkills } from '../api/skills';
import { CurrentChapterCard } from '../components/dashboard/CurrentChapterCard';
import { ProjectProgressCard } from '../components/dashboard/ProjectProgressCard';
import { CacheStatusCard } from '../components/dashboard/CacheStatusCard';
import { TodayCostCard } from '../components/dashboard/TodayCostCard';
import { OnboardingWizard } from '../components/dashboard/OnboardingWizard';
import { QUICK_START_SKILLS } from '../data/skillCategories';

export function DashboardPage() {
  const { data: status, isLoading } = useProjectStatus();
  const navigate = useNavigate();
  const { data: skills } = useSkills();

  // 取快速启动的 4 个 skill (setup / long-write / scan / cover)
  const quickStartSkills = useMemo(() => {
    if (!skills) return [];
    return QUICK_START_SKILLS
      .map((name) => skills.find((s) => s.name === name))
      .filter((s): s is NonNullable<typeof s> => Boolean(s));
  }, [skills]);

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
      <Stack spacing={4}>
        <Box>
          <Typography variant="h4">{status.project_name ?? '主页'}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {status.genre && `类型：${status.genre}`}
            {status.style_anchor && ` · 风格：${status.style_anchor}`}
          </Typography>
        </Box>

        {/* 主 4 卡片 */}
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

        {/* 快速启动 4 skill */}
        <Box>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <RocketLaunchIcon color="primary" />
            <Typography variant="h6">快速启动</Typography>
            <Chip size="small" label={`${quickStartSkills.length} 个常用 skill`} variant="outlined" />
          </Stack>
          <Grid container spacing={2}>
            {quickStartSkills.map((skill) => (
              <Grid item xs={12} sm={6} md={3} key={skill.name}>
                <Card variant="outlined" sx={{ height: '100%', '&:hover': { boxShadow: 2 } }}>
                  <CardActionArea
                    onClick={() => navigate(`/skills/${skill.name}`)}
                    sx={{ height: '100%' }}
                  >
                    <CardContent>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                          {skill.category}
                        </Typography>
                        <ArrowForwardIcon fontSize="small" color="action" />
                      </Stack>
                      <Typography variant="subtitle1" sx={{ mb: 0.5 }} noWrap>
                        {skill.name}
                      </Typography>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          display: '-webkit-box',
                          WebkitBoxOrient: 'vertical',
                          WebkitLineClamp: 2,
                          overflow: 'hidden',
                          minHeight: 40,
                        }}
                      >
                        {skill.description}
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Stack>
    </Container>
  );
}
