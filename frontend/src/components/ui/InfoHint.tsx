import { CircleHelp } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";

export function InfoHint({
  children,
  label = "How this works",
}: {
  children: ReactNode;
  label?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const descriptionId = useId();

  return (
    <Tooltip disableHoverablePopup onOpenChange={setIsOpen}>
      <TooltipTrigger
        aria-describedby={isOpen ? descriptionId : undefined}
        aria-label={label}
        className="info-hint"
      >
        <CircleHelp aria-hidden="true" size={12} />
      </TooltipTrigger>
      <TooltipContent
        align="end"
        className="info-hint-popup"
        collisionAvoidance={{ side: "flip", align: "shift", fallbackAxisSide: "end" }}
        collisionPadding={12}
        id={descriptionId}
        positionMethod="fixed"
        role="tooltip"
        side="bottom"
        sideOffset={6}
      >
        {children}
      </TooltipContent>
    </Tooltip>
  );
}
