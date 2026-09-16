/**
 * SkillDetailPage: 单个 Skill 的执行页 (Sprint 1 核心 + Sprint 5 扩展)
 *
 * 布局 (playbook §2.2.4):
 *   ┌─────────────────────────────────────────────────┐
 *   │ ← 返回 Skills                                   │
 *   │  ╔═══════════════════════════════════════════╗  │
 *   │  ║ 📖 story-long-write [v1.0] [⚙]            ║  │
 *   │  ║ 长篇 AI 续写 (8 阶段进度)                  ║  │
 *   │  ╚═══════════════════════════════════════════╝  │
 *   │  ┌─────────────────────┬──────────────────────┐ │
 *   │  │ 输入区              │ 输出区 (SSE 流式)     │ │
 *   │  │ [🚀 执行] [⛔ 取消] │ [📋 复制][💾 下载]    │ │
 *   │  └─────────────────────┴──────────────────────┘ │
 *   │  ┌──────────────────────────────────────────┐  │
 *   │  │ 历史 (最近 5 次)                          │  │
 *   │  └──────────────────────────────────────────┘  │
 *   └─────────────────────────────────────────────────┘
 *
 * Sprint 5 扩展: scan + analyze skill 专用布局（Recharts 可视化）
 *   - story-long-scan / story-short-scan → ScanReportView
 *   - story-long-analyze / story-short-analyze → AnalyzeReportView
 */

import { useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  Stack,
  Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';

import { useSkills } from '../api/skills';
import { SkillRunner } from '../components/skill/SkillRunner';
import { SkillHistory } from '../components/skill/SkillHistory';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { EmptyState } from '../components/common/EmptyState';
import { ScanReportView, AnalyzeReportView } from '../components/skill/SkillReportView';
import type { SkillInfo } from '../types/skills';

/** 4 个 Sprint 5 专用 skill 名（带 -scan 或 -analyze 后缀） */
const SCAN_SKILLS = new Set(['story-long-scan', 'story-short-scan']);
const ANALYZE_SKILLS = new Set(['story-long-analyze', 'story-short-analyze']);

function isScanSkill(skillName: string): boolean {
  return SCAN_SKILLS.has(skillName);
}
function isAnalyzeSkill(skillName: string): boolean {
  return ANALYZE_SKILLS.has(skillName);
}

export function SkillDetailPage() {
  const { name = '' } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: skills, isLoading, isError } = useSkills();

  const skill = useMemo<SkillInfo | null>(() => {
    if (!skills) return null;
    return skills.find((s) => s.name === name) ?? null;
  }, [skills, name]);

  // 加载中
  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <LoadingSkeleton variant="skillDetail" />
      </Container>
    );
  }

  // 错误 / 找不到
  if (isError) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <EmptyState
          title="Skill 加载失败"
          subtitle="请检查网络连接后重试"
          action={{ label: '返回 Skills 列表', onClick: () => navigate('/skills') }}
        />
      </Container>
    );
  }

  if (!skill) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <EmptyState
          title={`Skill "${name}" 不存在`}
          subtitle="可能已被移除或名称拼写错误"
          action={{ label: '返回 Skills 列表', onClick: () => navigate('/skills') }}
        />
      </Container>
    );
  }

  // 内部 skill 不允许手动调用
  if (skill.category === '内部' || !skill.userInvocable) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Button
          component={Link}
          to="/skills"
          startIcon={<ArrowBackIcon />}
          sx={{ mb: 2 }}
        >
          返回 Skills
        </Button>
        <Alert severity="warning">
          <Typography variant="subtitle2">{skill.name}</Typography>
          <Typography variant="body2">
            此 skill 仅供模型内部调用 (browser-cdp 等), 不对用户开放手动执行。
          </Typography>
        </Alert>
      </Container>
    );
  }

  // Sprint 5: scan skill 专用布局
  if (isScanSkill(skill.name)) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Button component={Link} to="/skills" startIcon={<ArrowBackIcon />} sx={{ mb: 2 }}>
          返回 Skills
        </Button>
        <Box sx={{ mb: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
            <Typography variant="h4">{skill.name}</Typography>
            <Chip size="small" label={`v${skill.version}`} variant="outlined" />
            <Chip size="small" label={skill.category} color="primary" variant="outlined" />
            <Chip size="small" label="扫榜" color="secondary" />
          </Stack>
          <Typography variant="body1" color="text.secondary">
            {skill.description}
          </Typography>
        </Box>
        <ScanReportView skill={skill} />
        <Box sx={{ mt: 3 }}>
          <SkillHistory skillName={skill.name} />
        </Box>
      </Container>
    );
  }

  // Sprint 5: analyze skill 专用布局
  if (isAnalyzeSkill(skill.name)) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Button component={Link} to="/skills" startIcon={<ArrowBackIcon />} sx={{ mb: 2 }}>
          返回 Skills
        </Button>
        <Box sx={{ mb: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
            <Typography variant="h4">{skill.name}</Typography>
            <Chip size="small" label={`v${skill.version}`} variant="outlined" />
            <Chip size="small" label={skill.category} color="primary" variant="outlined" />
            <Chip size="small" label="拆文" color="secondary" />
          </Stack>
          <Typography variant="body1" color="text.secondary">
            {skill.description}
          </Typography>
        </Box>
        <AnalyzeReportView skill={skill} />
        <Box sx={{ mt: 3 }}>
          <SkillHistory skillName={skill.name} />
        </Box>
      </Container>
    );
  }

  // 默认：通用 SkillRunner (Sprint 1)
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      {/* 返回 */}
      <Button
        component={Link}
        to="/skills"
        startIcon={<ArrowBackIcon />}
        sx={{ mb: 2 }}
        aria-label="返回 Skills 列表"
      >
        返回 Skills
      </Button>

      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
          <Typography variant="h4">{skill.name}</Typography>
          <Chip size="small" label={`v${skill.version}`} variant="outlined" />
          <Chip size="small" label={skill.category} color="primary" variant="outlined" />
          {!skill.userInvocable && <Chip size="small" label="内部" color="warning" />}
        </Stack>
        <Typography variant="body1" color="text.secondary">
          {skill.description}
        </Typography>
      </Box>

      {/* Runner */}
      <Box sx={{ mb: 3 }}>
        <SkillRunner skill={skill} />
      </Box>

      {/* 历史 */}
      <SkillHistory skillName={skill.name} />
    </Container>
  );
}
