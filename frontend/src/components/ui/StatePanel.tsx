import type { ReactNode } from "react";
import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";

type StatePanelProps = {
  title: string;
  children: ReactNode;
  kind?: "empty" | "error" | "loading";
};

export function StatePanel({ title, children, kind = "empty" }: StatePanelProps) {
  const Icon = kind === "error" ? AlertCircle : kind === "loading" ? LoaderCircle : Inbox;
  return (
    <section className={`state-panel state-panel-${kind}`} aria-live={kind === "loading" ? "polite" : undefined}>
      <Icon aria-hidden="true" className={kind === "loading" ? "spin" : undefined} size={24} />
      <div>
        <h2>{title}</h2>
        <p>{children}</p>
      </div>
    </section>
  );
}
