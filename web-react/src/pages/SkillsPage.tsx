/**
 * SkillsPage: 13 Skill 卡片网格 + 分类筛选 + 搜索
 *
 * 布局 (playbook §2.2.3):
 *   ┌─────────────────────────────────────────────────┐
 *   │ Skills (13)  [🔍 搜索] [分类: All ▼] [最近使用] │
 *   │ 创作类 (4) | 分析类 (4) | 工具类 (3) | 入口类(1)│
 *   │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
 *   │ │ ⚙   │ │ ✍️   │ │ ✏️   │ │ 🎨   │            │
 *   │ └──────┘ └──────┘ └──────┘ └──────┘            │
 *   └─────────────────────────────────────────────────┘
 *
 * 数据：useSkills() + skillExecutionStore.history (最近运行)
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Chip,
  Container,
  Grid,
  InputAdornment,
  Stack,
  TextField,
  Typography,
  Card,
  CardActionArea,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import HistoryIcon from '@mui/icons-material/History';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';

import { useSkills } from '../api/skills';
import { useSkillExecutionStore } from '../store/skillExecutionStore';
import { SkillCard } from '../components/skill/SkillCard';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { EmptyState } from '../components/common/EmptyState';
import type { SkillCategory, SkillInfo } from '../types/skills';
import { SKILL_CATEGORY_LIST } from '../types/skills';
import type { SkillExecutionHistoryEntry } from '../types/skills';

type CategoryFilter = SkillCategory | '全部';

const CATEGORY_FILTERS: CategoryFilter[] = ['全部', ...SKILL_CATEGORY_LIST];

const CATEGORY_COLOR: Record<SkillCategory, 'primary' | 'secondary' | 'success' | 'warning' | 'default'> = {
  创作类: 'primary',
  分析类: 'secondary',
  工具类: 'success',
  入口类: 'warning',
  内部: 'default',
};

// V1.5.1 修复（已知问题 #3）：后端 base URL 从环境变量读取，避免硬编码 IP。
// 优先级：VITE_API_BASE_URL (build-time 注入) > 默认 localhost。
// 默认值保留 192.168.3.106:8000 兼容现有本地开发环境；
// 生产 / 其他部署可通过 .env.local / .env.production 覆盖。
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  'http://192.168.3.106:8000';

export function SkillsPage() {
  const navigate = useNavigate();
  const { data: skills, isLoading, isError } = useSkills();
  const history = useSkillExecutionStore((s) => s.history);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<CategoryFilter>('全部');

  // 过滤 + 分组
  const grouped = useMemo(() => {
    const list = skills ?? [];
    const filtered = list.filter((s) => {
      // 排除内部 skill (browser-cdp)
      if (s.category === '内部' || !s.userInvocable) return false;
      // 分类
      if (filter !== '全部' && s.category !== filter) return false;
      // 搜索 (name + description)
      if (search) {
        const q = search.toLowerCase();
        const inName = s.name.toLowerCase().includes(q);
        const inDesc = s.description.toLowerCase().includes(q);
        if (!inName && !inDesc) return false;
      }
      return true;
    });
    const groups: Partial<Record<SkillCategory, SkillInfo[]>> = {};
    for (const s of filtered) {
      const cat = s.category;
      if (!groups[cat]) groups[cat] = [];
      groups[cat]!.push(s);
    }
    return groups;
  }, [skills, filter, search]);

  // 最近使用 (取所有 skill 中最近一次的, 最多 4 个)
  const recentSkills = useMemo<SkillInfo[]>(() => {
    const list = skills ?? [];
    const withRun = list
      .filter((s) => s.category !== '内部' && s.userInvocable && history[s.name]?.[0])
      .map((s) => ({ skill: s, last: history[s.name]?.[0] }))
      .sort((a, b) => (b.last?.startedAt ?? 0) - (a.last?.startedAt ?? 0))
      .slice(0, 4);
    return withRun.map((x) => x.skill);
  }, [skills, history]);

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <LoadingSkeleton variant="pageHeader" />
        <LoadingSkeleton variant="skillGrid" count={12} />
      </Container>
    );
  }

  if (isError) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <EmptyState
          title="Skills 加载失败"
          subtitle={`请检查后端服务 (${API_BASE_URL}) 是否正常, 或刷新重试`}
          action={{ label: '刷新', onClick: () => window.location.reload() }}
        />
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={2} sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4">Skills</Typography>
          <Typography variant="body2" color="text.secondary">
            共 {skills?.length ?? 0} 个能力, 覆盖创作 / 分析 / 工具 / 入口
          </Typography>
        </Box>
        <TextField
          size="small"
          placeholder="搜索 skill 名称或描述"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ width: { xs: '100%', md: 280 } }}
          inputProps={{ 'aria-label': '搜索 skill' }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
      </Stack>

      {/* 最近使用 (仅在全部视图下展示) */}
      {filter === '全部' && !search && recentSkills.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
            <HistoryIcon fontSize="small" color="action" />
            <Typography variant="subtitle2" color="text.secondary">
              最近使用
            </Typography>
          </Stack>
          <Grid container spacing={2}>
            {recentSkills.map((skill) => (
              <Grid item xs={12} sm={6} md={3} key={`recent-${skill.name}`}>
                <SkillCard
                  skill={skill}
                  lastRun={history[skill.name]?.[0] ?? null}
                  onClick={() => navigate(`/skills/${skill.name}`)}
                />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* 分类筛选 chips */}
      <Stack direction="row" spacing={1} sx={{ mb: 3, flexWrap: 'wrap', gap: 1 }}>
        {CATEGORY_FILTERS.map((cat) => {
          const active = filter === cat;
          const color = cat === '全部' ? 'default' : CATEGORY_COLOR[cat];
          return (
            <Chip
              key={cat}
              label={cat}
              clickable
              onClick={() => setFilter(cat)}
              color={active ? color : 'default'}
              variant={active ? 'filled' : 'outlined'}
              aria-pressed={active}
            />
          );
        })}
      </Stack>

      {/* 分类分组 */}
      {SKILL_CATEGORY_LIST.map((cat) => {
        const list = grouped[cat] ?? [];
        if (list.length === 0) return null;
        return (
          <Box key={cat} sx={{ mb: 4 }} data-testid={`skill-group-${cat}`}>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 1.5 }}>
              <Typography variant="h6">{cat}</Typography>
              <Typography variant="body2" color="text.secondary">
                {list.length} 个
              </Typography>
            </Stack>
            <Grid container spacing={2}>
              {list.map((skill) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={skill.name}>
                  <SkillCard
                    skill={skill}
                    lastRun={(history[skill.name]?.[0] as SkillExecutionHistoryEntry | undefined) ?? null}
                    onClick={() => navigate(`/skills/${skill.name}`)}
                  />
                </Grid>
              ))}
            </Grid>
          </Box>
        );
      })}

      {/* 空状态 (筛选/搜索后无结果) */}
      {Object.values(grouped).every((arr) => !arr || arr.length === 0) && (
        <EmptyState
          title="没有匹配的 skill"
          subtitle={search ? `没有找到包含 "${search}" 的 skill` : '该分类下暂无 skill'}
          action={
            search
              ? { label: '清除搜索', onClick: () => setSearch('') }
              : { label: '查看全部', onClick: () => setFilter('全部') }
          }
        />
      )}

      {/* 内部 skill 提示 (折叠在底部) */}
      {filter === '全部' && !search && (
        <Box sx={{ mt: 4 }}>
          <Card variant="outlined" sx={{ bgcolor: 'action.hover' }}>
            <CardActionArea
              onClick={() => navigate('/admin')}
              sx={{ p: 2 }}
              aria-label="查看内部 skill"
            >
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="subtitle2">内部能力</Typography>
                  <Typography variant="body2" color="text.secondary">
                    浏览器自动化等底层 skill 仅供模型自动调用, 不对用户展示
                  </Typography>
                </Box>
                <ArrowForwardIcon color="action" />
              </Stack>
            </CardActionArea>
          </Card>
        </Box>
      )}
    </Container>
  );
}