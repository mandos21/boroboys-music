import { Dialog } from "@base-ui/react/dialog";
import { AlertTriangle, X } from "lucide-react";
import type { ReactNode } from "react";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  isPending?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  isPending = false,
  onOpenChange,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-backdrop" />
        <Dialog.Popup className="confirm-dialog" aria-describedby="confirm-dialog-description">
          <div className="confirm-dialog-icon" aria-hidden="true">
            <AlertTriangle size={21} />
          </div>
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description id="confirm-dialog-description">{description}</Dialog.Description>
          <Dialog.Close
            aria-label="Close confirmation"
            className="icon-button confirm-dialog-close"
          >
            <X aria-hidden="true" size={18} />
          </Dialog.Close>
          <div className="confirm-dialog-actions">
            <Dialog.Close className="button button-secondary" disabled={isPending}>
              Cancel
            </Dialog.Close>
            <button
              className="button button-danger"
              disabled={isPending}
              onClick={onConfirm}
              type="button"
            >
              {isPending ? "Working…" : confirmLabel}
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
