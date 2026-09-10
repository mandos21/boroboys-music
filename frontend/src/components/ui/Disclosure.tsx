import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./collapsible";

type DisclosureProps = {
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  description?: string;
  title: string;
};

/** A themed shadcn/Base UI collapsible for progressive-reveal sections. */
export function Disclosure({
  children,
  className,
  defaultOpen = false,
  description,
  title,
}: DisclosureProps) {
  return (
    <Collapsible
      className={`disclosure${className ? ` ${className}` : ""}`}
      defaultOpen={defaultOpen}
    >
      <CollapsibleTrigger className="disclosure-trigger">
        <span>
          <strong>{title}</strong>
          {description && <small>{description}</small>}
        </span>
        <ChevronDown aria-hidden="true" size={17} />
      </CollapsibleTrigger>
      <CollapsibleContent className="disclosure-content">{children}</CollapsibleContent>
    </Collapsible>
  );
}
