import { Mail } from "lucide-react";

import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "../../components/ui/dialog";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";

export function SeriesEmailPreferences({
  seriesId,
  seriesName,
}: {
  seriesId: string;
  seriesName: string;
}) {
  return (
    <Dialog>
      <DialogTrigger render={<Button variant="outline" />}>My email notifications</DialogTrigger>
      <DialogContent className="series-email-dialog">
        <header className="series-email-dialog-header">
          <span className="series-email-dialog-icon">
            <Mail aria-hidden="true" size={24} />
          </span>
          <DialogTitle>My email notifications</DialogTitle>
          <DialogDescription>{seriesName}</DialogDescription>
        </header>
        <NotificationSettingsPanel seriesId={seriesId} />
      </DialogContent>
    </Dialog>
  );
}
