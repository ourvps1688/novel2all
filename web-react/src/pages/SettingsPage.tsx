/**
 * SettingsPage：设置页（T05 占位）
 *
 * 3 Tab：
 *   - 创作设定（project_root / _tracking-state.json 编辑）
 *   - 模型选择
 *   - Cache 调优
 */

import { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Alert,
  Tabs,
  Tab,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
} from '@mui/material';

import { useModels, useCurrentModel, useSwitchModel } from '../api/models';
import { useCacheRecommend } from '../api/cache';
import { useSnackbar } from '../hooks/useSnackbar';

export function SettingsPage() {
  const [tab, setTab] = useState(0);
  const { data: models, isLoading: modelsLoading } = useModels();
  const { data: current } = useCurrentModel();
  const switchMutation = useSwitchModel();
  const { data: recommend } = useCacheRecommend();
  const snackbar = useSnackbar();

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        设置
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tab label="模型选择" />
        <Tab label="Cache 调优" />
        <Tab label="创作设定" />
      </Tabs>

      {tab === 0 && (
        <Stack spacing={2}>
          <Alert severity="info">
            <strong>T09 占位</strong> — 完整实现见 P1 sprint。下方已可切换模型。
          </Alert>
          <FormControl fullWidth>
            <InputLabel id="model-select-label">当前模型</InputLabel>
            <Select
              labelId="model-select-label"
              label="当前模型"
              value={current?.model ?? ''}
              disabled={modelsLoading || switchMutation.isPending}
              onChange={(e) => {
                const newModel = e.target.value;
                switchMutation.mutate(newModel, {
                  onSuccess: (data) => {
                    snackbar.success(`已切换：${data.old_model} → ${data.new_model}`);
                  },
                  onError: (err) => {
                    snackbar.error(err instanceof Error ? err.message : '切换失败');
                  },
                });
              }}
            >
              {(models ?? []).map((m) => (
                <MenuItem key={m.name} value={m.name}>
                  {m.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {modelsLoading && <CircularProgress size={20} />}
        </Stack>
      )}

      {tab === 1 && (
        <Box>
          <Alert severity="info" sx={{ mb: 2 }}>
            <strong>T09 占位</strong> — Cache 推荐已可读。
          </Alert>
          {recommend ? (
            <Stack spacing={1}>
              <Typography variant="body2">
                健康评分：<strong>{(recommend.health_score ?? 0).toFixed(2)}</strong>
              </Typography>
              <Typography variant="body2">置信度：{recommend.confidence ?? '—'}</Typography>
              <Typography variant="body2" color="text.secondary">
                见 <code>/api/cache/recommend</code>
              </Typography>
            </Stack>
          ) : (
            <CircularProgress size={20} />
          )}
        </Box>
      )}

      {tab === 2 && (
        <Alert severity="info">
          <strong>T09 占位</strong> — 创作设定编辑（_tracking-state.json）见 P1 sprint。
        </Alert>
      )}
    </Container>
  );
}
