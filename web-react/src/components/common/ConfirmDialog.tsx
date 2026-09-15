/**
 * ConfirmDialog：通用确认对话框
 *
 * 用法：
 *   const [open, setOpen] = useState(false);
 *   <ConfirmDialog
 *     open={open}
 *     title="删除章节"
 *     message="确定要删除章节 5 吗？此操作不可撤销。"
 *     onConfirm={async () => { await delete(); }}
 *     onCancel={() => setOpen(false)}
 *   />
 */

import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';

import { LoadingButton } from './LoadingButton';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmColor?: 'primary' | 'error' | 'warning';
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确定',
  cancelText = '取消',
  confirmColor = 'primary',
  loading,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onClose={loading ? undefined : onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ whiteSpace: 'pre-line' }}>{message}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <LoadingButton onClick={onCancel} disabled={loading} color="inherit">
          {cancelText}
        </LoadingButton>
        <LoadingButton
          onClick={onConfirm}
          loading={loading}
          color={confirmColor}
          variant="contained"
          autoFocus
        >
          {confirmText}
        </LoadingButton>
      </DialogActions>
    </Dialog>
  );
}
