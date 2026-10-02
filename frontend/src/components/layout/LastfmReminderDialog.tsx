import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Headphones } from "lucide-react";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "../ui/alert-dialog";

type Connection = components["schemas"]["ConnectionResponse"];

const DISMISSED_KEY = "music-rounds-lastfm-reminder-dismissed-at";
const COOLDOWN_MS = 14 * 24 * 60 * 60 * 1000;

function wasRecentlyDismissed(): boolean {
  try {
    const stored = window.localStorage.getItem(DISMISSED_KEY);
    if (!stored) return false;
    const dismissedAt = Date.parse(stored);
    return !Number.isNaN(dismissedAt) && Date.now() - dismissedAt < COOLDOWN_MS;
  } catch {
    return false;
  }
}

/** A gentle, recurring nudge to link Last.fm - the one external account
 * nearly everyone is expected to have, since it now drives avatars,
 * listening evidence, and submission suggestions. Dismissing it snoozes for
 * two weeks rather than forever, since a one-time dismiss rarely turns into
 * a link, but nagging every page load would just train people to ignore it. */
export function LastfmReminderDialog({ enabled }: { enabled: boolean }) {
  const [dismissed, setDismissed] = useState(wasRecentlyDismissed);
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: () => api<Connection[]>("/connections"),
    enabled,
  });

  const hasLastfm = (connections.data ?? []).some(
    (connection) => connection.provider === "lastfm" && connection.isActive,
  );
  const open = enabled && connections.isSuccess && !hasLastfm && !dismissed;

  function dismiss() {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISSED_KEY, new Date().toISOString());
    } catch {
      // Private browsing or a full storage quota - the reminder just won't
      // snooze across reloads, which is harmless.
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) dismiss();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia aria-hidden="true">
            <Headphones size={20} />
          </AlertDialogMedia>
          <AlertDialogTitle>Link your Last.fm?</AlertDialogTitle>
          <AlertDialogDescription>
            Connecting Last.fm shows your recent listening to the group and powers submission
            suggestions. It only takes a minute, and you can manage it anytime from Settings.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Maybe later</AlertDialogCancel>
          <AlertDialogAction render={<a href="/api/v1/connections/lastfm/login" />}>
            Connect Last.fm
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
