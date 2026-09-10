import { CheckCircle2, CircleAlert, Info, LoaderCircle } from "lucide-react";
import type { CSSProperties } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      closeButton
      containerAriaLabel="Notifications"
      icons={{
        success: <CheckCircle2 aria-hidden="true" size={18} />,
        error: <CircleAlert aria-hidden="true" size={18} />,
        info: <Info aria-hidden="true" size={18} />,
        loading: <LoaderCircle aria-hidden="true" className="spin" size={18} />,
      }}
      position="bottom-right"
      style={
        {
          "--border-radius": "var(--radius)",
          "--normal-bg": "var(--popover)",
          "--normal-border": "var(--border)",
          "--normal-text": "var(--popover-foreground)",
        } as CSSProperties
      }
      toastOptions={{ classNames: { toast: "cn-toast" } }}
      visibleToasts={3}
      {...props}
    />
  );
}
