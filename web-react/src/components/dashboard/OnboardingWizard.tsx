/**
 * OnboardingWizard：新用户引导（项目未初始化时展示）
 *
 * 4 步（PRD §5 Sprint 4 第 6 项）：
 *   1. projectInit — 初始化项目（CLI: novel2all setup）
 *   2. modelSelect — 选择模型
 *   3. cacheConfig — 缓存配置（prompt prefix 命中率优化）
 *   4. firstWrite — 开始写第一章
 *
 * 可选 props:
 *   skippable: 是否显示「跳过引导」按钮（默认 true）
 *   onComplete: 全部完成时回调
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  Typography,
  Stack,
  Stepper,
  Step,
  StepLabel,
  Box,
  Button,
  Alert,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import TerminalIcon from '@mui/icons-material/Terminal';
import ModelTrainingIcon from '@mui/icons-material/ModelTraining';
import EditNoteIcon from '@mui/icons-material/EditNote';
import SpeedIcon from '@mui/icons-material/Speed';
import CloseIcon from '@mui/icons-material/Close';

import { useCurrentModel } from '../../api/models';

const STEPS = [
  { label: '初始化项目', icon: <TerminalIcon /> },
  { label: '选择模型', icon: <ModelTrainingIcon /> },
  { label: '缓存配置', icon: <SpeedIcon /> },
  { label: '开始创作', icon: <EditNoteIcon /> },
];

export interface OnboardingWizardProps {
  /** 是否显示「跳过引导」按钮（PRD §5 Sprint 4 验收第 6 项） */
  skippable?: boolean;
  /** 全部完成时回调（可选） */
  onComplete?: () => void;
}

export function OnboardingWizard({ skippable = true, onComplete }: OnboardingWizardProps = {}) {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  const handleSkip = (): void => {
    setDismissed(true);
    onComplete?.();
  };

  const handleComplete = (): void => {
    setDismissed(true);
    onComplete?.();
  };

  if (dismissed) return null;
  const { data: currentModel } = useCurrentModel();

  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Stack spacing={3}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <RocketLaunchIcon color="primary" sx={{ fontSize: 32 }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h5">欢迎使用 novel2all</Typography>
              <Typography variant="body2" color="text.secondary">
                让我们用 4 步完成首次创作准备
              </Typography>
            </Box>
            {skippable && (
              <Tooltip title="跳过引导（可稍后在设置页再次查看）">
                <IconButton onClick={handleSkip} aria-label="skip onboarding">
                  <CloseIcon />
                </IconButton>
              </Tooltip>
            )}
          </Stack>

          <Stepper activeStep={activeStep} alternativeLabel>
            {STEPS.map((s) => (
              <Step key={s.label}>
                <StepLabel icon={s.icon}>{s.label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          {activeStep === 0 && (
            <Stack spacing={2}>
              <Alert severity="info">
                当前项目未初始化。请在服务器终端运行：
              </Alert>
              <Box
                sx={{
                  p: 2,
                  bgcolor: (t) => (t.palette.mode === 'light' ? 'grey.100' : 'grey.900'),
                  borderRadius: 1,
                  fontFamily: 'monospace',
                  fontSize: 14,
                }}
              >
                $ novel2all setup
              </Box>
              <Typography variant="caption" color="text.secondary">
                该命令会引导你输入书名、类型、风格锚点等元数据。完成后点击下方"我已初始化"。
              </Typography>
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button variant="contained" onClick={() => setActiveStep(1)}>
                  我已初始化 →
                </Button>
              </Stack>
            </Stack>
          )}

          {activeStep === 1 && (
            <Stack spacing={2}>
              <Typography variant="body1">当前模型：</Typography>
              <Chip
                label={currentModel?.model ?? '加载中…'}
                color="primary"
                sx={{ alignSelf: 'flex-start', fontSize: 16, px: 2, py: 3 }}
              />
              <Typography variant="body2" color="text.secondary">
                前往「设置」页面切换模型。推荐长篇写作使用 deepseek-chat 或 claude-sonnet-4。
              </Typography>
              <Stack direction="row" spacing={1} justifyContent="space-between">
                <Button onClick={() => setActiveStep(0)}>← 上一步</Button>
                <Button variant="contained" onClick={() => setActiveStep(2)}>
                  继续 →
                </Button>
              </Stack>
            </Stack>
          )}

          {activeStep === 2 && (
            <Stack spacing={2}>
              <Typography variant="body1">缓存配置：</Typography>
              <Typography variant="body2" color="text.secondary">
                Prompt Prefix Cache 可节省 ~70% 输入成本。前 5 章节会预热缓存，之后每章复用。
              </Typography>
              <Alert severity="info">
                系统已自动启用缓存。前往「设置」→「缓存调优」可监控命中率。
              </Alert>
              <Stack direction="row" spacing={1} justifyContent="space-between">
                <Button onClick={() => setActiveStep(1)}>← 上一步</Button>
                <Button variant="contained" onClick={() => setActiveStep(3)}>
                  继续 →
                </Button>
              </Stack>
            </Stack>
          )}

          {activeStep === 3 && (
            <Stack spacing={2}>
              <Typography variant="body1">准备就绪！开始你的第一章节创作：</Typography>
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={() => {
                    handleComplete();
                    navigate('/write/1');
                  }}
                  startIcon={<EditNoteIcon />}
                >
                  开始第 1 章
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => {
                    handleComplete();
                    navigate('/settings');
                  }}
                >
                  调整设置
                </Button>
              </Stack>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
