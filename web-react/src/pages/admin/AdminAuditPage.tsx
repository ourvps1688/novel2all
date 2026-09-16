/**
 * AdminAuditPage — 管理员审计日志页（PRD §5 Sprint 4 第 4 项）
 *
 * 功能:
 *   - 审计日志列表（useAuditLog → AuditLogSchema → events[]）
 *   - 过滤（event_type + user_id + limit）
 *   - CSV 导出（前端 blob 下载）
 *
 * AuditEventSchema 实际字段:
 *   event_type / user_id / username / ip / success / detail / timestamp
 */

import { useState } from 'react';

import {
  Stack,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Button,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import FilterAltIcon from '@mui/icons-material/FilterAlt';
import ClearIcon from '@mui/icons-material/Clear';

import { useAuditLog, type AuditFilters } from '../../api/audit';
import { useSnackbar } from '../../hooks/useSnackbar';

const EVENT_TYPES = [
  'login',
  'logout',
  'login_failed',
  'user_created',
  'user_deleted',
  'user_disabled',
  'project_created',
  'project_shared',
  'chapter_written',
  'chapter_reviewed',
  'cache_cleared',
];

export function AdminAuditPage() {
  const snackbar = useSnackbar();
  const [filters, setFilters] = useState<AuditFilters>({ limit: 200 });

  const auditQuery = useAuditLog(filters);
  const events = auditQuery.data?.events ?? [];

  const handleApplyFilter = () => {
    void auditQuery.refetch();
  };

  const handleClearFilter = () => {
    setFilters({ limit: 200 });
  };

  const handleExportCsv = () => {
    if (events.length === 0) {
      snackbar.warning('无数据可导出');
      return;
    }

    // CSV header (实际 schema 字段)
    const header = [
      'event_type',
      'user_id',
      'username',
      'ip',
      'success',
      'detail',
      'timestamp',
    ];

    const esc = (v: unknown): string => {
      if (v == null) return '';
      const s = typeof v === 'string' ? v : String(v);
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };

    const rows = events.map((e) => [
      e.event_type,
      e.user_id ?? '',
      e.username ?? '',
      e.ip ?? '',
      e.success == null ? '' : String(e.success),
      e.detail ?? '',
      e.timestamp,
    ]);

    const csv = [header, ...rows].map((row) => row.map(esc).join(',')).join('\n');
    const bom = '\uFEFF'; // Excel 中文兼容
    const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    snackbar.success(`已导出 ${events.length} 条审计日志`);
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h6">审计日志 ({events.length})</Typography>

      {/* 过滤栏 */}
      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>事件类型</InputLabel>
            <Select
              value={filters.event_type ?? ''}
              label="事件类型"
              onChange={(e) =>
                setFilters({
                  ...filters,
                  event_type: e.target.value ? String(e.target.value) : undefined,
                })
              }
            >
              <MenuItem value="">（全部）</MenuItem>
              {EVENT_TYPES.map((t) => (
                <MenuItem key={t} value={t}>
                  {t}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <TextField
            size="small"
            label="用户 ID"
            type="number"
            value={filters.user_id ?? ''}
            onChange={(e) =>
              setFilters({
                ...filters,
                user_id: e.target.value ? Number(e.target.value) : undefined,
              })
            }
            sx={{ width: 120 }}
          />

          <TextField
            size="small"
            label="数量上限"
            type="number"
            value={filters.limit ?? 200}
            onChange={(e) =>
              setFilters({ ...filters, limit: Number(e.target.value) || 200 })
            }
            sx={{ width: 120 }}
          />

          <Button
            variant="contained"
            startIcon={<FilterAltIcon />}
            onClick={handleApplyFilter}
            data-testid="admin-audit-apply"
          >
            应用
          </Button>
          <Button
            startIcon={<ClearIcon />}
            onClick={handleClearFilter}
            data-testid="admin-audit-clear"
          >
            清空
          </Button>

          <Box sx={{ flex: 1 }} />

          <Tooltip title="刷新">
            <span>
              <IconButton
                onClick={() => void auditQuery.refetch()}
                disabled={auditQuery.isFetching}
              >
                <RefreshIcon />
              </IconButton>
            </span>
          </Tooltip>

          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleExportCsv}
            disabled={events.length === 0}
            data-testid="admin-audit-export-csv"
          >
            导出 CSV
          </Button>
        </Stack>
      </Paper>

      {auditQuery.isError && (
        <Alert severity="error">
          加载审计日志失败：{(auditQuery.error as Error).message}
        </Alert>
      )}

      {auditQuery.isLoading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
        </Stack>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small" data-testid="admin-audit-table">
            <TableHead>
              <TableRow>
                <TableCell>时间</TableCell>
                <TableCell>事件</TableCell>
                <TableCell>用户</TableCell>
                <TableCell>IP</TableCell>
                <TableCell>结果</TableCell>
                <TableCell>详情</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((e, idx) => (
                <TableRow key={`${e.timestamp}-${idx}`} hover>
                  <TableCell>
                    <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                      {e.timestamp.replace('T', ' ').slice(0, 19)}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={e.event_type} />
                  </TableCell>
                  <TableCell>
                    {e.username ?? (e.user_id != null ? `#${e.user_id}` : '-')}
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                      {e.ip ?? '-'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={e.success == null ? '-' : e.success ? 'OK' : 'FAIL'}
                      color={
                        e.success == null
                          ? 'default'
                          : e.success
                            ? 'success'
                            : 'error'
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        display: 'block',
                        maxWidth: 360,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={e.detail}
                    >
                      {e.detail ?? '-'}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
              {events.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography color="text.secondary">无审计记录</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}
