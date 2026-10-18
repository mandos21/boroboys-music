import { CircleHelp } from "lucide-react";
import { Popover } from "@base-ui/react/popover";
import { useId, useState, type ReactNode } from "react";

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
    <Popover.Root onOpenChange={setIsOpen}>
      <Popover.Trigger
        aria-describedby={isOpen ? descriptionId : undefined}
        aria-label={label}
        className="info-hint"
      >
        <CircleHelp aria-hidden="true" size={12} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner
          align="end"
          collisionAvoidance={{ side: "flip", align: "shift", fallbackAxisSide: "end" }}
          collisionPadding={12}
          positionMethod="fixed"
          side="bottom"
          sideOffset={6}
        >
          <Popover.Popup className="info-hint-popup" id={descriptionId}>
            {children}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
