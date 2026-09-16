/**
 * Toolbar: AI 工具栏 (Sprint 2)
 *
 * 按钮:
 *   - 保存 (手动触发, 配合自动保存)
 *   - 撤销 / 重做 (Tiptap 命令)
 *   - AI 续写 (调 /api/write/stream, 8 阶段流)
 *   - AI 重写选区 (调 /api/chapter/{n}/rewrite)
 *   - AI 插入段落 (调 /api/chapter/{n}/insert)
 *
 * 设计:
 *   - 纯展示组件, 状态通过 props 控制
 *   - 章节/选区/loading 状态都从父组件传入
 *   - 操作通过 onAction 回调通知父组件
 */

import { Stack, Button, Tooltip, IconButton, Divider, CircularProgress } from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import UndoIcon from '@mui/icons-material/Undo';
import RedoIcon from '@mui/icons-material/Redo';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import EditIcon from '@mui/icons-material/Edit';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';

import type { TextSelection, AIOperationType } from '../../types/chapters';

export type ToolbarAction =
  | { type: 'save' }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'continue' }
  | { type: 'rewrite'; selection: TextSelection }
  | { type: 'insert'; selection: TextSelection }
  | { type: 'deslop' };

export interface ToolbarProps {
  chapter: number;

  /** 当前选区 (用于重写/插入按钮的 disabled 判断) */
  selection: TextSelection | null;

  /** Tiptap editor 是否可撤销/重做 */
  canUndo: boolean;
  canRedo: boolean;

  /** 当前是否有未保存修改 */
  isDirty: boolean;

  /** 是否正在自动保存 */
  isAutoSaving: boolean;

  /** 是否正在执行某个 AI 操作 (用于 disable 所有 AI 按钮) */
  aiLoading: AIOperationType | null;

  /** SSE 写作是否在进行 (用于 disable 续写按钮) */
  isStreaming: boolean;

  /** 操作回调 */
  onAction: (action: ToolbarAction) => void;
}

export function Toolbar({
  selection,
  canUndo,
  canRedo,
  isDirty,
  isAutoSaving,
  aiLoading,
  isStreaming,
  onAction,
}: ToolbarProps) {
  const hasSelection = selection != null && selection.text.length > 0;
  const aiBusy = aiLoading != null || isStreaming;

  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{ p: 1, borderBottom: 1, borderColor: 'divider' }}
      data-testid="write-toolbar"
    >
      {/* 保存 */}
      <Tooltip title={isAutoSaving ? '保存中...' : isDirty ? '保存 (Ctrl+S)' : '已保存'}>
        <span>
          <Button
            size="small"
            variant={isDirty ? 'contained' : 'outlined'}
            startIcon={
              isAutoSaving ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <SaveIcon fontSize="small" />
              )
            }
            onClick={() => onAction({ type: 'save' })}
            disabled={isAutoSaving || !isDirty}
            color={isDirty ? 'primary' : 'inherit'}
            data-testid="toolbar-save"
          >
            保存
          </Button>
        </span>
      </Tooltip>

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      {/* 撤销 / 重做 */}
      <Tooltip title="撤销 (Ctrl+Z)">
        <span>
          <IconButton
            size="small"
            onClick={() => onAction({ type: 'undo' })}
            disabled={!canUndo}
            data-testid="toolbar-undo"
            aria-label="撤销"
          >
            <UndoIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="重做 (Ctrl+Y)">
        <span>
          <IconButton
            size="small"
            onClick={() => onAction({ type: 'redo' })}
            disabled={!canRedo}
            data-testid="toolbar-redo"
            aria-label="重做"
          >
            <RedoIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      {/* AI 操作 */}
      <Tooltip title={isStreaming ? 'AI 正在写作...' : 'AI 续写 (整章)'}>
        <span>
          <Button
            size="small"
            variant="outlined"
            color="primary"
            startIcon={
              aiLoading === 'continue' || isStreaming ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <AutoAwesomeIcon fontSize="small" />
              )
            }
            onClick={() => onAction({ type: 'continue' })}
            disabled={aiBusy}
            data-testid="toolbar-continue"
          >
            AI 续写
          </Button>
        </span>
      </Tooltip>

      <Tooltip title={hasSelection ? 'AI 重写选区' : '请先选中段落'}>
        <span>
          <Button
            size="small"
            variant="outlined"
            startIcon={
              aiLoading === 'rewrite' ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <EditIcon fontSize="small" />
              )
            }
            onClick={() => selection && onAction({ type: 'rewrite', selection })}
            disabled={aiBusy || !hasSelection || !selection}
            data-testid="toolbar-rewrite"
          >
            AI 重写
          </Button>
        </span>
      </Tooltip>

      <Tooltip title={hasSelection ? 'AI 在选区位置插入' : '请先选位置'}>
        <span>
          <Button
            size="small"
            variant="outlined"
            startIcon={
              aiLoading === 'insert' ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <AddCircleIcon fontSize="small" />
              )
            }
            onClick={() => selection && onAction({ type: 'insert', selection })}
            disabled={aiBusy || !selection}
            data-testid="toolbar-insert"
          >
            AI 插入
          </Button>
        </span>
      </Tooltip>

      <Tooltip title="去 AI 味 (story-deslop)">
        <span>
          <Button
            size="small"
            variant="outlined"
            color="secondary"
            startIcon={
              aiLoading === 'deslop' ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <AutoFixHighIcon fontSize="small" />
              )
            }
            onClick={() => onAction({ type: 'deslop' })}
            disabled={aiBusy}
            data-testid="toolbar-deslop"
          >
            去 AI 味
          </Button>
        </span>
      </Tooltip>

      {/* AI 操作取消按钮 (当某个操作正在加载时显示) */}
      {aiLoading != null && (
        <Tooltip title="取消 AI 操作">
          <IconButton
            size="small"
            color="error"
            onClick={() => {
              // 通知父组件取消: 通过 onAction 触发 type === cancel
              // (父组件会判断并停止 mutation)
              onAction({ type: 'save' });
              /* cancel 由 aiLoading parent 控制 */
            }}
            aria-label="取消 AI 操作"
            data-testid="toolbar-cancel-ai"
          >
            <CancelIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}