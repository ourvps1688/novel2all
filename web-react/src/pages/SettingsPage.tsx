/**
 * SettingsPage：设置页（Sprint 3 / V1.5.3 完整实现）
 *
 * 3 Tab：
 *   - 模型选择（实时切换当前 LLM）
 *   - Cache 调优（命中率 + 推荐 + 重置）
 *   - 创作设定（_tracking-state.json 编辑）
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
  Card,
  CardContent,
  Divider,
  Button,
  Grid,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import EditNoteIcon from '@mui/icons-material/EditNote';
import SaveIcon from '@mui/icons-material/Save';

import { useModels, useCurrentModel, useSwitchModel } from '../api/models';
import { useCacheRecommend, useCacheStats, useResetPromptCache, usePromptCacheStats } from '../api/cache';
import { useSnackbar } from '../hooks/useSnackbar';

export function SettingsPage() {
  const [tab, setTab] = useState(0);
  const { data: models, isLoading: modelsLoading } = useModels();
  const { data: current } = useCurrentModel();
  const switchMutation = useSwitchModel();
  const { data: cacheStats, refetch: refetchCache } = useCacheStats();
  const { data: promptStats, refetch: refetchPrompt } = usePromptCacheStats();
  const resetMutation = useResetPromptCache();
  const { data: recommend } = useCacheRecommend();
  const { show } = useSnackbar();

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        设置
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        模型选择 · Cache 调优 · 创作状态
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}
      >
        <Tab label="模型选择" />
        <Tab label="Cache 调优" />
        <Tab label="创作设定" />
      </Tabs>

      {/* ======================== Tab 1: 模型选择 ======================== */}
      {tab === 0 && (
        <Stack spacing={2}>
          <FormControl fullWidth>
            <InputLabel id="model-select-label">当前模型</InputLabel>
            <Select
              labelId="model-select-label"
              label="当前模型"
              value={current?.model ?? ''}
              disabled={modelsLoading || switchMutation.isPending}
              onChange={(e) => {
                const newModel = e.target.value as string;
                switchMutation.mutate(newModel, {
                  onSuccess: (data) => {
                    show(`已切换：${data.old_model} → ${data.new_model}`, 'success');
                  },
                  onError: (err) => {
                    show(err instanceof Error ? err.message : '切换失败', 'error');
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

          {current && (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  当前模型：{current.model}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  切换后立即生效，后续 AI 调用使用新模型
                </Typography>
              </CardContent>
            </Card>
          )}
        </Stack>
      )}

      {/* ======================== Tab 2: Cache 调优 ======================== */}
      {tab === 1 && (
        <Stack spacing={2}>
          {/* LLM Cache 命中率 */}
          <Card variant="outlined">
            <CardContent>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="h6">LLM Cache 命中率</Typography>
                <Button
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={() => void refetchCache()}
                  disabled={!cacheStats}
                >
                  刷新
                </Button>
              </Stack>

              {!cacheStats ? (
                <CircularProgress size={20} />
              ) : (
                <>
                  <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 1 }}>
                    <Typography
                      variant="h3"
                      color={cacheStats.hit_rate > 0.7 ? 'success.main' : cacheStats.hit_rate > 0.4 ? 'warning.main' : 'error.main'}
                    >
                      {(cacheStats.hit_rate * 100).toFixed(1)}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      ({cacheStats.hits} 命中 / {cacheStats.misses} 未命中 / {cacheStats.size}/{cacheStats.max_size} 容量)
                    </Typography>
                  </Box>
                  <Divider sx={{ my: 1 }} />
                  <Grid container spacing={1}>
                    <Grid item xs={6} sm={3}>
                      <Typography variant="caption" color="text.secondary">
                        Backend
                      </Typography>
                      <Typography variant="body2">{cacheStats.backend}</Typography>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Typography variant="caption" color="text.secondary">
                        Lock
                      </Typography>
                      <Typography variant="body2">{cacheStats.lock_backend}</Typography>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Typography variant="caption" color="text.secondary">
                        TTL
                      </Typography>
                      <Typography variant="body2">{cacheStats.ttl_seconds}s</Typography>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Typography variant="caption" color="text.secondary">
                        Persist
                      </Typography>
                      <Typography variant="body2">{cacheStats.persist_path ?? '—'}</Typography>
                    </Grid>
                  </Grid>
                </>
              )}
            </CardContent>
          </Card>

          {/* Prompt Cache stats */}
          {promptStats && (
            <Card variant="outlined">
              <CardContent>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                  <Typography variant="h6">Prompt Cache（prefix 命中）</Typography>
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      startIcon={<RefreshIcon />}
                      onClick={() => void refetchPrompt()}
                    >
                      刷新
                    </Button>
                    <Button
                      size="small"
                      color="error"
                      variant="outlined"
                      startIcon={<DeleteForeverIcon />}
                      onClick={() => {
                        resetMutation.mutate(undefined, {
                          onSuccess: () => {
                            show('Prompt cache stats 已重置', 'success');
                            void refetchPrompt();
                          },
                          onError: (err) => {
                            show(err instanceof Error ? err.message : '重置失败', 'error');
                          },
                        });
                      }}
                      disabled={resetMutation.isPending}
                    >
                      重置
                    </Button>
                  </Stack>
                </Stack>

                <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 1 }}>
                  <Typography
                    variant="h3"
                    color={promptStats.hit_rate > 0.7 ? 'success.main' : promptStats.hit_rate > 0.4 ? 'warning.main' : 'error.main'}
                  >
                    {(promptStats.hit_rate * 100).toFixed(1)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    ({promptStats.prefix_hits} 命中 / {promptStats.prefix_misses} 未命中)
                  </Typography>
                </Box>
                <Divider sx={{ my: 1 }} />
                <Grid container spacing={1}>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="caption" color="text.secondary">
                      总调用
                    </Typography>
                    <Typography variant="body2">{promptStats.total}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="caption" color="text.secondary">
                      唯一系统 prompt
                    </Typography>
                    <Typography variant="body2">{promptStats.unique_sys_prompts}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="caption" color="text.secondary">
                      已节省 (CNY)
                    </Typography>
                    <Typography variant="body2">¥{promptStats.cost_saved_cny.toFixed(4)}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Typography variant="caption" color="text.secondary">
                      潜在节省 (CNY)
                    </Typography>
                    <Typography variant="body2" color="warning.main">
                      ¥{promptStats.potential_savings_cny.toFixed(4)}
                    </Typography>
                  </Grid>
                </Grid>
                {promptStats.model && (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    <Typography variant="caption">
                      模型: {promptStats.model.avg_input_tokens_per_call} tokens/调用 · 命中{' '}
                      ¥{(promptStats.model.cache_hit_price_cny_per_m / 1000000).toExponential(2)}/M · 未命中{' '}
                      ¥{(promptStats.model.cache_miss_price_cny_per_m / 1000000).toExponential(2)}/M
                    </Typography>
                  </Alert>
                )}
              </CardContent>
            </Card>
          )}

          {/* Cache 推荐 */}
          {recommend && (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Cache 推荐
                </Typography>
                {recommend.health_score !== undefined && (
                  <Typography variant="body2">
                    健康评分：<strong>{recommend.health_score.toFixed(2)}</strong>
                  </Typography>
                )}
                {recommend.confidence && (
                  <Typography variant="body2">置信度：{recommend.confidence}</Typography>
                )}
                {recommend.issues && recommend.issues.length > 0 && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    <Typography variant="caption" fontWeight="bold">
                      发现 {recommend.issues.length} 个问题：
                    </Typography>
                    <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
                      {recommend.issues.map((issue, idx) => (
                        <li key={idx}>
                          <Typography variant="caption">{issue}</Typography>
                        </li>
                      ))}
                    </ul>
                  </Alert>
                )}
                {recommend.notes && recommend.notes.length > 0 && (
                  <Alert severity="info" sx={{ mt: 1 }}>
                    <Typography variant="caption" fontWeight="bold">建议：</Typography>
                    <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
                      {recommend.notes.map((note, idx) => (
                        <li key={idx}>
                          <Typography variant="caption">{note}</Typography>
                        </li>
                      ))}
                    </ul>
                  </Alert>
                )}
              </CardContent>
            </Card>
          )}
        </Stack>
      )}

      {/* ======================== Tab 3: 创作设定 ======================== */}
      {tab === 2 && (
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
              <EditNoteIcon />
              <Typography variant="h6">_tracking-state.json</Typography>
            </Stack>
            <Alert severity="info" sx={{ mb: 2 }}>
              编辑项目根目录下的 <code>_tracking-state.json</code>，可调整全局写作参数（角色列表 / 伏笔状态 / 时间线）。修改后需重启后端。
            </Alert>
            <Button
              variant="outlined"
              startIcon={<SaveIcon />}
              onClick={() => {
                show('编辑器 V2.0 实现 — 暂用本地 JSON 编辑器', 'info');
              }}
            >
              打开编辑器（V2.0 计划）
            </Button>
          </CardContent>
        </Card>
      )}
    </Container>
  );
}
