import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { StatePanel } from "../../components/ui/StatePanel";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import { SeriesHistoryTab } from "./SeriesHistoryTab";
import { SeriesMembersTab } from "./SeriesMembersTab";
import { SeriesNotificationsTab } from "./SeriesNotificationsTab";
import { SeriesRoundsTab } from "./SeriesRoundsTab";
import type { SeriesDetail } from "./types";
import "./admin.css";

const TABS = ["rounds", "members", "history", "notifications"] as const;
type Tab = (typeof TABS)[number];

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const [params, setParams] = useSearchParams();
  const requestedTab = params.get("tab");
  const tab: Tab = TABS.includes(requestedTab as Tab) ? (requestedTab as Tab) : "rounds";
  useEffect(() => {
    if (requestedTab !== "automation") return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("tab", "rounds");
        return next;
      },
      { replace: true },
    );
  }, [requestedTab, setParams]);
  const queryClient = useQueryClient();
  const navRef = useRef<HTMLElement>(null);
  const detail = useQuery({
    queryKey: queryKeys.adminSeriesDetail(seriesId),
    queryFn: () => api<SeriesDetail>(`/admin/series/${seriesId}`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  useEffect(() => {
    navRef.current
      ?.querySelector<HTMLElement>('[aria-current="page"]')
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [tab, detail.isPending]);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.adminSeriesDetail(seriesId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.series() });
  };
  if (detail.isPending)
    return <PageSkeleton label="Loading series workspace" variant="workspace" />;
  if (detail.isError || !detail.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Series unavailable">
          <Link to="/">Return to your series</Link>
        </StatePanel>
      </main>
    );
  const series = detail.data;
  const openCount = series.rounds.filter((round) => round.status === "open").length;
  return (
    <main className="shell admin-shell">
      <Link className="back" to={`/series/${series.id}`}>
        ← {series.name}
      </Link>
      <header className="series-management-heading">
        <div>
          <p className="eyebrow">Series management</p>
          <h1>{series.name}</h1>
          <p className="field-hint">
            {openCount} open round{openCount === 1 ? "" : "s"} · Automation{" "}
            {series.autoStartNextRound && series.roundPlan ? "on" : "off"}
          </p>
        </div>
      </header>
      <nav ref={navRef} className="admin-section-nav series-tabs" aria-label="Series management">
        {TABS.map((name) => {
          const target = new URLSearchParams(params);
          target.set("tab", name);
          return (
            <Link key={name} to={`?${target}`} aria-current={tab === name ? "page" : undefined}>
              {name[0].toUpperCase() + name.slice(1)}
            </Link>
          );
        })}
      </nav>
      <SeriesPanels key={series.id} series={series} tab={tab} onSaved={invalidate} />
    </main>
  );
}

// Mount each panel on its first visit, then preserve its forms when switching
// tabs (including browser Back/Forward). Hidden panels stop their own polling.
function SeriesPanels({
  series,
  tab,
  onSaved,
}: {
  series: SeriesDetail;
  tab: Tab;
  onSaved: () => void;
}) {
  const [visited, setVisited] = useState<Tab[]>([tab]);
  if (!visited.includes(tab)) setVisited([...visited, tab]);
  return (
    <>
      {visited.map((name) => (
        <div key={name} hidden={tab !== name}>
          {name === "rounds" && (
            <SeriesRoundsTab series={series} active={tab === name} onSaved={onSaved} />
          )}
          {name === "members" && <SeriesMembersTab series={series} active={tab === name} />}
          {name === "history" && <SeriesHistoryTab series={series} onSaved={onSaved} />}
          {name === "notifications" && (
            <SeriesNotificationsTab series={series} active={tab === name} />
          )}
        </div>
      ))}
    </>
  );
}
