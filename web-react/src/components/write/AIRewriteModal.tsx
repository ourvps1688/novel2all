/**
 * AIRewriteModal: AI 重写选区预览 Modal (Sprint 2)
 *
 * 流程:
 *   1. 用户在编辑器选中段落 + 点击工具栏 "重写"
 *   2. 弹 Modal, 显示 instruction 输入框 + 原文预览
 *   3. 用户输入 instruction + 提交 → 调 /api/chapter/{n}/rewrite
 *   4. 收到 AI 重写后, 显示 diff (原文 → 改写)
 *   5. 用户点 [应用] → 调用 onApply(rewritten) 替换选区
 *      或点 [拒绝] → 关闭 modal
 *
 * 设计:
 *   - 双重 UI: instruction 输入 + diff 预览
 *   - 区分三阶段: input (loading=false) → preview (rewritten 拿到后) → applied
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
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';

export interface AIRewriteModalProps {
  open: boolean;

  /** 章节号 (用于显示) */
  chapter: number;

  /** 原文 (只读) */
  original: string;

  /** AI 改写结果 (null = 还在生成) */
  rewritten: string | null;

  /** 用户指令 */
  instruction: string;

  /** 加载状态 (调后端 rewrite 中) */
  loading: boolean;

  /** 错误信息 */
  errorMsg?: string | null;

  /** 用户确认改写 (替换选区) */
  onApply: () => void;

  /** 用户拒绝 (关闭 modal) */
  onReject: () => void;

  /** 修改 instruction */
  onInstructionChange: (instruction: string) => void;
}

export function AIRewriteModal({
  open,
  chapter,
  original,
  rewritten,
  instruction,
  loading,
  errorMsg,
  onApply,
  onReject,
  onInstructionChange,
}: AIRewriteModalProps) {
  // 内部状态: 用户是否已确认 instruction (点击 "生成")
  const [submitted, setSubmitted] = useState(false);

  // Modal 打开时重置 submitted
  useEffect(() => {
    if (open) {
      setSubmitted(false);
    }
  }, [open]);

  const showPreview = submitted && rewritten != null;

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onReject}
      maxWidth="md"
      fullWidth
      data-testid="ai-rewrite-modal"
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoFixHighIcon color="primary" />
          <Typography variant="h6">AI 重写选区</Typography>
          <Typography variant="caption" color="text.secondary">
            第 {chapter} 章
          </Typography>
        </Stack>
      </DialogTitle>

      <DialogContent dividers>
        {/* 原文 (只读) */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
            📄 原文 ({original.length} 字)
          </Typography>
          <Box
            sx={{
              p: 1.5,
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
              bgcolor: 'background.default',
              maxHeight: 160,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: '"Source Han Serif", "Songti SC", serif',
              fontSize: 14,
            }}
            data-testid="rewrite-original"
          >
            {original}
          </Box>
        </Box>

        {/* 改写指令 */}
        <TextField
          fullWidth
          size="small"
          label="改写指令"
          placeholder="例如: 改写得更生动自然 / 突出紧张感 / 精简到 200 字"
          value={instruction}
          onChange={(e) => onInstructionChange(e.target.value)}
          disabled={loading || showPreview}
          inputProps={{ 'aria-label': '改写指令' }}
          sx={{ mb: 2 }}
        />

        {errorMsg && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMsg}
          </Alert>
        )}

        {/* 重写结果预览 */}
        {showPreview && rewritten != null && (
          <Box>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
              <Typography variant="caption" color="text.secondary">
                ✨ AI 改写 ({rewritten.length} 字, {rewritten.length - original.length >= 0 ? '+' : ''}
                {rewritten.length - original.length} 字)
              </Typography>
              <Typography variant="caption" color="text.secondary">
                对比差异 (unified diff)
              </Typography>
            </Stack>
            <Box
              sx={{
                p: 1.5,
                border: 1,
                borderColor: 'success.main',
                borderRadius: 1,
                bgcolor: 'success.50',
                maxHeight: 240,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                fontFamily: '"Source Han Serif", "Songti SC", serif',
                fontSize: 14,
              }}
              data-testid="rewrite-result"
            >
              {rewritten}
            </Box>
          </Box>
        )}

        {/* Loading */}
        {loading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
            <CircularProgress size={16} />
            <Typography variant="body2" color="text.secondary">
              AI 改写中...
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
              disabled={loading || !instruction.trim() || !original.trim()}
              data-testid="rewrite-submit"
            >
              {loading ? '生成中...' : '生成改写'}
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
              data-testid="rewrite-apply"
            >
              应用改写
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}