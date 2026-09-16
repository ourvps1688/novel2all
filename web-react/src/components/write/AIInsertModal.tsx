/**
 * AIInsertModal: AI 在指定位置插入段落预览 Modal (Sprint 2)
 *
 * 流程:
 *   1. 用户在编辑器选中位置 + 点击工具栏 "插入"
 *   2. 弹 Modal, 显示 instruction 输入框 + 上下文预览
 *   3. 用户输入 instruction + 提交 → 调 /api/chapter/{n}/insert
 *   4. 收到 AI 插入内容后, 显示 preview
 *   5. 用户点 [应用] → 调用 onApply(inserted) 插入
 *      或点 [拒绝] → 关闭 modal
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Stack,
  Typography,
  CircularProgress,
  Alert,
  Divider,
} from '@mui/material';
import AddCircleIcon from '@mui/icons-material/AddCircle';

export interface AIInsertModalProps {
  open: boolean;

  /** 章节号 */
  chapter: number;

  /** 插入位置 */
  position: number;

  /** 上下文: 位置前 100 字 + 位置后 100 字 */
  context: string;

  /** AI 插入结果 (null = 还在生成) */
  inserted: string | null;

  /** 用户指令 */
  instruction: string;

  /** 加载状态 */
  loading: boolean;

  /** 错误信息 */
  errorMsg?: string | null;

  /** 用户确认插入 */
  onApply: () => void;

  /** 用户拒绝 */
  onReject: () => void;

  /** 修改 instruction */
  onInstructionChange: (instruction: string) => void;
}

export function AIInsertModal({
  open,
  chapter,
  position,
  context,
  inserted,
  instruction,
  loading,
  errorMsg,
  onApply,
  onReject,
  onInstructionChange,
}: AIInsertModalProps) {
  // 内部状态: 用户是否已提交
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (open) {
      setSubmitted(false);
    }
  }, [open]);

  const showPreview = submitted && inserted != null;

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onReject}
      maxWidth="md"
      fullWidth
      data-testid="ai-insert-modal"
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AddCircleIcon color="primary" />
          <Typography variant="h6">AI 插入段落</Typography>
          <Typography variant="caption" color="text.secondary">
            第 {chapter} 章 · 位置 {position}
          </Typography>
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        {/* 上下文 */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
            📍 上下文 (前后各 100 字)
          </Typography>
          <Box
            sx={{
              p: 1.5,
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'background.default',
              maxHeight: 120,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: '"Source Han Serif", "Songti SC", serif',
              fontSize: 14,
            }}
            data-testid="insert-context"
          >
            {context || '（无上下文）'}
          </Box>
        </Box>

        {/* 插入指令 */}
        <TextField
          fullWidth
          size="small"
          label="插入指令"
          placeholder="例如: 加入一段战斗场景 / 自然衔接的过渡段落 / 角色内心独白"
          value={instruction}
          onChange={(e) => onInstructionChange(e.target.value)}
          disabled={loading || showPreview}
          inputProps={{ 'aria-label': '插入指令' }}
          sx={{ mb: 2 }}
        />

        {errorMsg && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMsg}
          </Alert>
        )}

        {/* 插入结果预览 */}
        {showPreview && inserted != null && (
          <Box>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
              ✨ 待插入内容 ({inserted.length} 字)
            </Typography>
            <Box
              sx={{
                p: 1.5,
                border: 1,
                borderColor: 'primary.main',
                borderRadius: 1,
                bgcolor: 'primary.50',
                maxHeight: 240,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                fontFamily: '"Source Han Serif", "Songti SC", serif',
                fontSize: 14,
              }}
              data-testid="insert-result"
            >
              {inserted}
            </Box>
          </Box>
        )}

        {loading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
            <CircularProgress size={16} />
            <Typography variant="body2" color="text.secondary">
              AI 生成中...
            </Typography>
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {!showPreview ? (
          <>
            <Button onClick={onReject} disabled={loading}>
              取消
            </Button>
            <Button
              variant="contained"
              onClick={() => setSubmitted(true)}
              disabled={loading || !instruction.trim()}
              data-testid="insert-submit"
            >
              {loading ? '生成中...' : '生成内容'}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={onReject} color="inherit">
              拒绝
            </Button>
            <Button
              variant="contained"
              color="success"
              onClick={onApply}
              disabled={loading}
              data-testid="insert-apply"
            >
              插入到选区
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}