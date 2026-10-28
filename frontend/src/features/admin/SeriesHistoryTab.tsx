import { Disclosure } from "../../components/ui/Disclosure";
import { HistoricalImportPanel } from "./HistoricalImportPanel";
import { isPastRound, SeriesRoundList } from "./SeriesRoundsTab";
import type { SeriesDetail } from "./types";

export function SeriesHistoryTab({
  series,
  onSaved,
}: {
  series: SeriesDetail;
  onSaved: () => void;
}) {
  return (
    <div className="series-tab-stack">
      <section className="panel">
        <h2>Past rounds</h2>
        <SeriesRoundList
          rounds={series.rounds.filter(isPastRound)}
          empty="Published and cancelled rounds will appear here."
        />
      </section>
      <Disclosure
        className="panel"
        title="Import a past playlist"
        description="Bring an existing Spotify playlist into this series’ history."
      >
        <HistoricalImportPanel
          seriesId={series.id}
          timezone={series.timezone}
          onImported={onSaved}
        />
      </Disclosure>
    </div>
  );
}
