/**
 * SkillCard: 单个 Skill 卡片
 *
 * 设计：
 *   - 顶部 emoji + 名称 (MUI icon 不可用时降级 emoji)
 *   - 中部描述 (2 行截断)
 *   - 底部分类 chip + 最近运行状态 (如有)
 *   - 整体可点击 → 跳 /skills/:name
 *
 * V1.5.1 Sprint 1.1 修复（已知问题 #5）：
 *   - 新增 ``isInternal`` prop：内部 skill 卡片额外加 "内部工具" chip 提示
 *   - 仍允许点击查看详情（SkillDetailPage 会展示说明 + 禁止手动执行）
 */

import { useMemo } from 'react';
import {
  Card,
  CardActionArea,
  CardContent,
  Stack,
  Typography,
  Chip,
  Box,
} from '@mui/material';
import {
  Edit as EditIcon,
  Settings as SettingsIcon,
  Search as SearchIcon,
  Article as ArticleIcon,
  Analytics as AnalyticsIcon,
  Image as ImageSearchIcon,
  AutoFixHigh as AutoFixHighIcon,
  RateReview as RateReviewIcon,
  Upload as UploadIcon,
  Route as RouteIcon,
  Lock as LockIcon,
  Extension as ExtensionIcon,
} from '@mui/icons-material';
import type { ComponentType } from 'react';

import type { SkillInfo } from '../../types/skills';
import type { SkillExecutionHistoryEntry } from '../../types/skills';
import { formatDuration } from '../../utils/format';

export interface SkillCardProps {
  skill: SkillInfo;
  lastRun?: SkillExecutionHistoryEntry | null;
  onClick: () => void;
  /**
   * V1.5.1 Sprint 1.1 修复（已知问题 #5）：标记内部 skill
   *
   * - true → 卡片额外显示 "内部工具" chip
   * - false/undefined → 不显示
   *
   * 调用方（SkillsPage）从 ``CATEGORY_MAP[skill.name]?.isInternal`` 取值。
   */
  isInternal?: boolean;
}

/** MUI icon 名称 → 组件 (有限白名单, 防止 XSS) */
const ICON_MAP: Record<string, ComponentType> = {
  Edit: EditIcon,
  Settings: SettingsIcon,
  Search: SearchIcon,
  Article: ArticleIcon,
  Analytics: AnalyticsIcon,
  Image: ImageSearchIcon,
  AutoFixHigh: AutoFixHighIcon,
  RateReview: RateReviewIcon,
  Upload: UploadIcon,
  Route: RouteIcon,
  Lock: LockIcon,
  Extension: ExtensionIcon,
};

const STATUS_COLOR: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
  success: 'success',
  error: 'error',
  cancelled: 'warning',
  preparing: 'default',
  running: 'default',
};

const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  error: '失败',
  cancelled: '已取消',
  preparing: '准备中',
  running: '运行中',
};

export function SkillCard({ skill, lastRun, onClick, isInternal = false }: SkillCardProps) {
  const IconComponent = useMemo<ComponentType>(() => ICON_MAP[skill.icon] ?? ExtensionIcon, [skill.icon]);

  return (
    <Card
      variant="outlined"
      sx={{
        height: '100%',
        transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
        '&:hover': {
          boxShadow: 3,
          borderColor: 'primary.main',
        },
      }}
      data-testid={`skill-card-${skill.name}`}
    >
      <CardActionArea onClick={onClick} sx={{ height: '100%' }}>
        <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          {/* Header */}
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 40,
                height: 40,
                borderRadius: 1.5,
                bgcolor: (t) => (t.palette.mode === 'light' ? 'primary.50' : 'primary.900'),
                color: 'primary.main',
                flexShrink: 0,
                '& svg': { fontSize: 22 },
              }}
              aria-hidden
            >
              <IconComponent />
            </Box>
            <Box sx={{ minWidth: 0, flexGrow: 1 }}>
              <Typography variant="subtitle1" noWrap title={skill.name}>
                {skill.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                v{skill.version}
              </Typography>
            </Box>
            {isInternal && (
              <Chip
                size="small"
                label="内部工具"
                color="warning"
                variant="outlined"
                data-testid={`skill-internal-badge-${skill.name}`}
                sx={{ flexShrink: 0 }}
              />
            )}
          </Stack>

          {/* Description */}
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              flexGrow: 1,
              minHeight: 40,
              display: '-webkit-box',
              WebkitBoxOrient: 'vertical',
              WebkitLineClamp: 2,
              overflow: 'hidden',
            }}
          >
            {skill.description}
          </Typography>

          {/* Footer */}
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mt: 1.5, gap: 1 }}
          >
            <Chip
              size="small"
              label={skill.category}
              variant="outlined"
              color={skill.category === '创作类' ? 'primary' : skill.category === '分析类' ? 'secondary' : 'default'}
            />
            {lastRun ? (
              <Chip
                size="small"
                label={`${STATUS_LABEL[lastRun.status] ?? '历史'} · ${formatDuration(lastRun.durationMs / 1000)}`}
                color={STATUS_COLOR[lastRun.status] ?? 'default'}
                variant="outlined"
              />
            ) : (
              <Typography variant="caption" color="text.disabled">
                未运行
              </Typography>
            )}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}