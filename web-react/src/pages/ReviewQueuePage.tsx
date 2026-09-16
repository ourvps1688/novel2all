/**
 * ReviewQueuePage：审查队列页（Sprint 3 / V1.5.3 完整实现）
 *
 * 布局（2 列）：
 *   ┌──────────────────────────────────────────────────────────┐
 *   │ Header: 审查队列 | 总览（critical / warn / pass 数）     │
 *   ├──────────────────┬───────────────────────────────────────┤
 *   │ 章节列表 (左 35%) │ 4-agent 报告 (右 65%)                  │
 *   │ - 章节号          │ - 顶部 4 个维度评分卡                  │
 *   │ - 字数            │   (节奏/情感/可读性/沉浸)               │
 *   │ - [Review] 按钮   │ - 中间 4 tab (All/critical/major/minor)│
 *   │                  │ - 每个 issue card 含跳转按钮           │
 *   └──────────────────┴───────────────────────────────────────┘
 *
 * 数据流：
 *   - useChapters(): 列出所有章节
 *   - useReviewChapter(): 触发 4-agent review（Idempotency-Key 自动）
 *   - 报告缓存：useCachedReview (跨页共享) + useReviewChapter.setQueryData
 *   - 跳转：useNavigate(/write/:chapter)
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  Skeleton,
  Stack,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import LaunchIcon from '@mui/icons-material/Launch';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import InfoIcon from '@mui/icons-material/Info';

import { useChapters, useReviewChapter, useCachedReview } from '../api/chapters';
import type { ReviewReport, ReviewIssue } from '../api/types';
import { EmptyState } from '../components/common/EmptyState';
import { useSnackbar } from '../hooks/useSnackbar';

const DEFAULT_PROJECT_ROOT = '.';

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'critical', label: 'Critical' },
  { key: 'major', label: 'Major' },
  { key: 'minor', label: 'Minor' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

/**
 * QualityScore 4 维度 — 对应 4-agent 评审
 * 字段顺序按 architecture-V1.5.x.md §3 维度评分
 */
const QUALITY_DIMENSIONS = [
  { key: 'pacing', label: '节奏', agent: '架构 agent' },
  { key: 'emotion', label: '情感', agent: '爽点 agent' },
  { key: 'readability', label: '可读性', agent: '可读性 agent' },
  { key: 'immersion', label: '沉浸', agent: '一致性 agent' },
] as const;

function verdictUI(v: 'pass' | 'warn' | 'fail') {
  if (v === 'pass') return { color: 'success' as const, icon: <CheckCircleIcon fontSize="small" /> };
  if (v === 'warn') return { color: 'warning' as const, icon: <WarningIcon fontSize="small" /> };
  return { color: 'error' as const, icon: <ErrorIcon fontSize="small" /> };
}

function severityUI(s: ReviewIssue['severity']) {
  if (s === 'critical') return { color: 'error' as const, icon: <ErrorIcon fontSize="small" /> };
  if (s === 'warning') return { color: 'warning' as const, icon: <WarningIcon fontSize="small" /> };
  return { color: 'info' as const, icon: <InfoIcon fontSize="small" /> };
}

export function ReviewQueuePage() {
  const navigate = useNavigate();
  const { show } = useSnackbar();

  const projectRoot = DEFAULT_PROJECT_ROOT;
  const { data: chapters, isLoading: chaptersLoading, isError: chaptersError, refetch } = useChapters(projectRoot);
  const reviewMutation = useReviewChapter(projectRoot);
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('all');

  // 当前章节的 review 报告（如果缓存里有）
  const { data: cachedReport } = useCachedReview(selectedChapter ?? -1);

  // 默认选中第一个章节
  const firstChapter = useMemo(() => chapters?.[0]?.chapter ?? null, [chapters]);
  const activeChapter = selectedChapter ?? firstChapter;

  /** 触发 review */
  const handleReview = async (chapter: number) => {
    setSelectedChapter(chapter);
    try {
      const result = await reviewMutation.mutateAsync({ chapter });
      if (result._idempotent_replay) {
        show('复用已有审查结果（5min 内）', 'info');
      } else {
        show(`审查完成（${result.overall_verdict}）`, 'success');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      show(`审查失败: ${msg}`, 'error');
    }
  };

  /** 跳转到 WritePage */
  const handleJumpToChapter = (chapter: number) => {
    navigate(`/write/${chapter}`);
  };

  if (chaptersError) {
    return (
      <Box sx={{ p: 3 }}>
        <EmptyState
          title="章节加载失败"
          subtitle="请检查项目是否初始化（novel2all setup）"
          action={{ label: '重试', onClick: () => void refetch() }}
        />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography variant="h4">审查队列</Typography>
        <Button
          startIcon={<RefreshIcon />}
          onClick={() => void refetch()}
          disabled={chaptersLoading}
          size="small"
        >
          刷新
        </Button>
      </Stack>

      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                章节列表
              </Typography>
              {chaptersLoading ? (
                <Stack spacing={1}>
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} variant="rectangular" height={48} />
                  ))}
                </Stack>
              ) : !chapters || chapters.length === 0 ? (
                <EmptyState
                  title="暂无章节"
                  subtitle="请先初始化项目并写至少一章"
                />
              ) : (
                <List dense disablePadding>
                  {chapters.map((ch) => (
                    <ListItem key={ch.chapter} disablePadding>
                      <ListItemButton
                        selected={ch.chapter === activeChapter}
                        onClick={() => setSelectedChapter(ch.chapter)}
                        sx={{ borderRadius: 1 }}
                      >
                        <Stack
                          direction="row"
                          alignItems="center"
                          justifyContent="space-between"
                          sx={{ width: '100%' }}
                          spacing={1}
                        >
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Typography variant="body2" noWrap>
                              第 {ch.chapter} 章
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {ch.char_count ?? 0} 字
                            </Typography>
                          </Box>
                          <Tooltip title="触发 4-agent 审查">
                            <IconButton
                              size="small"
                              onClick={(e) => {
                                e.stopPropagation();
                                void handleReview(ch.chapter);
                              }}
                              disabled={
                                reviewMutation.isPending && reviewMutation.variables?.chapter === ch.chapter
                              }
                            >
                              {reviewMutation.isPending && reviewMutation.variables?.chapter === ch.chapter ? (
                                <CircularProgress size={16} />
                              ) : (
                                <RefreshIcon fontSize="small" />
                              )}
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={8}>
          {activeChapter == null ? (
            <Card variant="outlined">
              <CardContent>
                <EmptyState title="请先选择章节" />
              </CardContent>
            </Card>
          ) : (
            <ReportPanel
              report={cachedReport ?? null}
              chapter={activeChapter}
              isReviewing={
                reviewMutation.isPending && reviewMutation.variables?.chapter === activeChapter
              }
              activeTab={activeTab}
              onTabChange={setActiveTab}
              onJumpToChapter={handleJumpToChapter}
              onReview={() => void handleReview(activeChapter)}
            />
          )}
        </Grid>
      </Grid>
    </Box>
  );
}

// ============ 报告面板 ============

interface ReportPanelProps {
  report: ReviewReport | null;
  chapter: number;
  isReviewing: boolean;
  activeTab: TabKey;
  onTabChange: (key: TabKey) => void;
  onJumpToChapter: (chapter: number) => void;
  onReview: () => void;
}

function ReportPanel({
  report,
  chapter,
  isReviewing,
  activeTab,
  onTabChange,
  onJumpToChapter,
  onReview,
}: ReportPanelProps) {
  const allIssues = useMemo<ReviewIssue[]>(() => {
    if (!report) return [];
    return [...report.critical_issues, ...report.major_issues, ...report.minor_issues];
  }, [report]);

  const filteredIssues = useMemo<ReviewIssue[]>(() => {
    if (!report) return [];
    if (activeTab === 'all') return allIssues;
    if (activeTab === 'critical') return report.critical_issues;
    if (activeTab === 'major') return report.major_issues;
    return report.minor_issues;
  }, [report, activeTab, allIssues]);

  if (!report) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Stack alignItems="center" spacing={2} sx={{ py: 4 }}>
            <Typography variant="body2" color="text.secondary">
              第 {chapter} 章 还未审查
            </Typography>
            <Button
              variant="contained"
              onClick={onReview}
              disabled={isReviewing}
              startIcon={isReviewing ? <CircularProgress size={16} /> : <RefreshIcon />}
            >
              {isReviewing ? '审查中...' : '开始 4-agent 审查'}
            </Button>
            <Typography variant="caption" color="text.secondary">
              4 个 agent 并行：架构 / 可读性 / 一致性 / 爽点
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  const verdict = verdictUI(report.overall_verdict);
  const isReplay = report._idempotent_replay;

  return (
    <Stack spacing={2}>
      <Alert
        severity={verdict.color}
        action={
          <Stack direction="row" spacing={1}>
            {isReplay && <Chip size="small" label="复用结果" variant="outlined" />}
            <Button
              size="small"
              variant="outlined"
              onClick={onReview}
              disabled={isReviewing}
              startIcon={isReviewing ? <CircularProgress size={12} /> : <RefreshIcon />}
            >
              重新审查
            </Button>
          </Stack>
        }
        icon={verdict.icon}
      >
        <Typography variant="subtitle2">
          第 {report.chapter_number} 章 · {report.overall_verdict.toUpperCase()} ·{' '}
          {report.content_chars} 字 · {report.elapsed_seconds.toFixed(1)}s
        </Typography>
        {report.quality_score && (
          <Typography variant="caption" color="text.secondary">
            质量分 {report.quality_score.overall_score.toFixed(1)}/5
          </Typography>
        )}
      </Alert>

      {report.quality_score && (
        <Grid container spacing={1}>
          {QUALITY_DIMENSIONS.map((dim) => {
            const qs = report.quality_score;
            if (!qs) return null;
            const score = qs[dim.key as keyof typeof qs] as number;
            return (
              <Grid item xs={6} sm={3} key={dim.key}>
                <Card variant="outlined">
                  <CardContent sx={{ textAlign: 'center', py: 1.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {dim.label}
                    </Typography>
                    <Typography variant="h5" sx={{ mt: 0.5 }}>
                      {score.toFixed(1)}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      <Card variant="outlined">
        <Tabs
          value={activeTab}
          onChange={(_, v) => onTabChange(v as TabKey)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          {TABS.map((t) => {
            const count =
              t.key === 'all'
                ? allIssues.length
                : t.key === 'critical'
                  ? report.critical_issues.length
                  : t.key === 'major'
                    ? report.major_issues.length
                    : report.minor_issues.length;
            return (
              <Tab
                key={t.key}
                value={t.key}
                label={
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <span>{t.label}</span>
                    <Chip size="small" label={count} color={count > 0 ? 'primary' : 'default'} />
                  </Stack>
                }
              />
            );
          })}
        </Tabs>

        <CardContent>
          {filteredIssues.length === 0 ? (
            <EmptyState
              title="没有 issue"
              subtitle={activeTab === 'all' ? '完美章节 🎉' : '此分类下没有 issue'}
            />
          ) : (
            <Stack spacing={2} divider={<Divider flexItem />}>
              {filteredIssues.map((issue, idx) => (
                <IssueCard
                  key={`${activeTab}-${idx}-${issue.description.slice(0, 20)}`}
                  issue={issue}
                  onJumpToChapter={() => onJumpToChapter(chapter)}
                />
              ))}
            </Stack>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}

// ============ Issue Card ============

interface IssueCardProps {
  issue: ReviewIssue;
  onJumpToChapter: () => void;
}

function IssueCard({ issue, onJumpToChapter }: IssueCardProps) {
  const sev = severityUI(issue.severity);
  return (
    <Box>
      <Stack direction="row" alignItems="flex-start" spacing={1.5}>
        <Chip
          size="small"
          color={sev.color}
          icon={sev.icon as React.ReactElement}
          label={issue.severity}
          sx={{ flexShrink: 0, mt: 0.25 }}
        />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            {issue.description}
          </Typography>
          <Stack direction="row" spacing={0.5} sx={{ mb: 1 }} flexWrap="wrap">
            {issue.category && <Chip size="small" label={issue.category} variant="outlined" />}
            {issue.agent_label && (
              <Chip size="small" label={issue.agent_label} variant="outlined" color="secondary" />
            )}
          </Stack>
          {issue.evidence && (
            <Alert severity="info" sx={{ py: 0.5, mb: 1 }}>
              <Typography variant="caption">
                <strong>证据:</strong> {issue.evidence}
              </Typography>
            </Alert>
          )}
          {issue.suggestion && (
            <Alert severity="success" sx={{ py: 0.5, mb: 1 }}>
              <Typography variant="caption">
                <strong>建议:</strong> {issue.suggestion}
              </Typography>
            </Alert>
          )}
        </Box>
        <Tooltip title="跳转到该章节">
          <IconButton size="small" onClick={onJumpToChapter}>
            <LaunchIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}
