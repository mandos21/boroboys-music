import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { markPerformance } from "../../lib/performance";
import "./seriesInsightsShell.css";

const SeriesInsights = lazy(() =>
  import("./SeriesInsights").then((module) => ({ default: module.SeriesInsights })),
);

type SeriesGenreInsights = components["schemas"]["SeriesGenreInsightsResponse"];

export function DeferredSeriesInsights({ seriesId }: { seriesId: string }) {
  const triggerRef = useRef<HTMLElement>(null);
  const [isNearViewport, setIsNearViewport] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const insights = useQuery({
    queryKey: queryKeys.seriesInsights(seriesId),
    queryFn: () => api<SeriesGenreInsights>(`/series/${seriesId}/insights`),
    enabled: isNearViewport,
    retry: false,
  });

  useEffect(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setIsNearViewport(true);
        observer.disconnect();
      },
      { rootMargin: "480px 0px" },
    );
    observer.observe(trigger);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (insights.isSuccess) markPerformance("series-insights-ready", "series-core-ready");
  }, [insights.isSuccess]);

  return (
    <section ref={triggerRef} aria-label="Series genre insights">
      {!isNearViewport || insights.isLoading ? <InsightsSkeleton /> : null}
      {insights.isError ? (
        <p className="series-insights-error">Genre detail is unavailable right now.</p>
      ) : null}
      {insights.data?.genreSpread.length ? (
        <Suspense fallback={<InsightsSkeleton />}>
          <SeriesInsights stats={insights.data} />
        </Suspense>
      ) : null}
    </section>
  );
}

function InsightsSkeleton() {
  return (
    <section className="panel series-insights-skeleton" aria-busy="true">
      <p className="eyebrow">Taste map</p>
      <h2>Loading genre detail</h2>
      <div aria-hidden="true" className="series-insights-skeleton-lines">
        <i />
        <i />
        <i />
      </div>
    </section>
  );
}
