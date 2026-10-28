import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { patch } from "../../api/client";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import { useToast } from "../../components/ui/ToastProvider";
import { PolicySettings } from "./PolicySettings";
import { Disclosure } from "../../components/ui/Disclosure";
import { SeriesIdentityEditor } from "./SeriesIdentityEditor";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail } from "./types";

export function SeriesRoundSettings({
  series,
  onSaved,
}: {
  series: SeriesDetail;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState(series.defaultAttributionRevealDelaySeconds !== null);
  const [minutes, setMinutes] = useState(
    String((series.defaultAttributionRevealDelaySeconds ?? 3600) / 60),
  );
  const { showToast } = useToast();
  const save = useMutation({
    mutationFn: () =>
      patch(`/admin/series/${series.id}`, {
        default_attribution_reveal_delay_seconds: enabled ? Math.round(Number(minutes) * 60) : null,
      }),
    onSuccess: () => {
      onSaved();
      showToast({ title: "Guess Who defaults saved" });
    },
  });
  return (
    <section className="panel" aria-labelledby="round-settings-heading">
      <div className="series-settings-heading">
        <div>
          <h2 id="round-settings-heading">Round settings</h2>
          <p className="field-hint">
            Defaults for new rounds. Existing rounds keep their own settings.
          </p>
        </div>
        <SeriesIdentityEditor series={series} onSaved={onSaved} />
      </div>
      <div className="series-round-controls">
        <Disclosure
          keepMounted
          title="Default round checks"
          description={`${series.defaultPolicies.length} check${series.defaultPolicies.length === 1 ? "" : "s"} configured for new rounds.`}
        >
          <PolicySettings
            id={series.id}
            scope="series"
            policies={series.defaultPolicies}
            onSaved={onSaved}
          />
        </Disclosure>
        <Disclosure
          keepMounted
          title="Guess Who defaults"
          description={
            series.defaultAttributionRevealDelaySeconds === null
              ? "Off for new rounds."
              : `On for new rounds · Names hidden for ${series.defaultAttributionRevealDelaySeconds / 60} minutes after publishing.`
          }
        >
          <form
            className="admin-round-form"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            <label className="notification-toggle">
              <span>Enable Guess Who for new rounds</span>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </label>
            {enabled && (
              <label>
                Minutes to keep names hidden after publishing
                <input
                  type="number"
                  min="0"
                  step="1"
                  required
                  value={minutes}
                  onChange={(event) => setMinutes(event.target.value)}
                />
              </label>
            )}
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save Guess Who defaults"}
            </Button>
            {save.isError && (
              <p role="alert" className="error-message">
                {errorMessage(save.error)}
              </p>
            )}
          </form>
        </Disclosure>
      </div>
    </section>
  );
}
