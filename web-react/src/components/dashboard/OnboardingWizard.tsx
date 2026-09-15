/**
 * OnboardingWizard：新用户引导（项目未初始化时展示）
 *
 * 3 步：
 *   1. projectInit — 初始化项目（CLI: novel2all setup）
 *   2. modelSelect — 选择模型
 *   3. firstWrite — 开始写第一章
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
} from '@mui/material';
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch';
import TerminalIcon from '@mui/icons-material/Terminal';
import ModelTrainingIcon from '@mui/icons-material/ModelTraining';
import EditNoteIcon from '@mui/icons-material/EditNote';

import { useCurrentModel } from '../../api/models';

const STEPS = [
  { label: '初始化项目', icon: <TerminalIcon /> },
  { label: '选择模型', icon: <ModelTrainingIcon /> },
  { label: '开始创作', icon: <EditNoteIcon /> },
];

export function OnboardingWizard() {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const { data: currentModel } = useCurrentModel();

  return (
    <Card>
      <CardContent sx={{ p: 4 }}>
        <Stack spacing={3}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <RocketLaunchIcon color="primary" sx={{ fontSize: 32 }} />
            <Box>
              <Typography variant="h5">欢迎使用 novel2all</Typography>
              <Typography variant="body2" color="text.secondary">
                让我们用 3 步完成首次创作准备
              </Typography>
            </Box>
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
              <Typography variant="body1">准备就绪！开始你的第一章节创作：</Typography>
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={() => navigate('/write/1')}
                  startIcon={<EditNoteIcon />}
                >
                  开始第 1 章
                </Button>
                <Button variant="outlined" size="large" onClick={() => navigate('/settings')}>
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
