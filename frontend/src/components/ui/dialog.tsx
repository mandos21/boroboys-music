import type { ComponentProps } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { X } from "lucide-react";

import { Button } from "./button";
import "./dialog.css";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;

/** Dismissible modal with Base UI focus management, Escape, and outside-click handling. */
export function DialogContent({
  className,
  children,
  ...props
}: ComponentProps<typeof DialogPrimitive.Popup>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Backdrop className="modal-dialog-backdrop" />
      <DialogPrimitive.Popup className={`modal-dialog ${className ?? ""}`} {...props}>
        {children}
        <DialogPrimitive.Close
          render={<Button variant="ghost" size="icon" className="modal-dialog-close" />}
          aria-label="Close"
        >
          <X aria-hidden="true" size={20} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Popup>
    </DialogPrimitive.Portal>
  );
}
