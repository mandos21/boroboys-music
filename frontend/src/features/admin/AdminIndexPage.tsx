import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { api, post } from "../../api/client";
import { errorMessage } from "./adminUtils";
import type { Series, Session } from "./types";

export function AdminIndexPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const series = useQuery({
    queryKey: ["admin-series"],
    queryFn: () => api<Series[]>("/admin/series"),
  });
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [planKind, setPlanKind] = useState<"none" | "rolling" | "calendar">(
    "none",
  );
  const [rollingHours, setRollingHours] = useState("");
  const [calendarDay, setCalendarDay] = useState("1");
  const [calendarDuration, setCalendarDuration] = useState("7");
  const [nextLimit, setNextLimit] = useState("");
  const [autoStart, setAutoStart] = useState(true);
  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>("/admin/series", {
        name,
        slug,
        timezone,
        default_policies: [],
        auto_start_next_round: planKind === "none" ? false : autoStart,
        round_plan:
          planKind === "rolling"
            ? {
                kind: "rolling",
                duration_hours: Number(rollingHours),
                submission_limit: nextLimit ? Number(nextLimit) : null,
              }
            : planKind === "calendar"
              ? {
                  kind: "calendar",
                  open_day: Number(calendarDay),
                  duration_days: Number(calendarDuration),
                  submission_limit: nextLimit ? Number(nextLimit) : null,
                }
              : null,
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["admin-series"] });
      navigate(`/admin/series/${result.id}`);
    },
  });
  const isPlatformAdmin = session.data?.user.platformRole === "admin";

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <main className="shell admin-shell">
      <Link className="back" to="/">
        ← Your rounds
      </Link>
      <header className="submission-heading">
        <p className="eyebrow">Administration</p>
        <h1>Series and rounds</h1>
        <p>
          A series owns its history, reusable contributor groups, policy
          defaults, and an optional automatic successor plan.
        </p>
      </header>
      {isPlatformAdmin && (
        <section className="panel admin-create">
          <h2>Create a series</h2>
          <form onSubmit={submit}>
            <label>
              Name
              <input
                value={name}
                required
                maxLength={200}
                onChange={(event) => {
                  setName(event.target.value);
                  if (!slug)
                    setSlug(
                      event.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, "-")
                        .replace(/^-|-$/g, ""),
                    );
                }}
              />
            </label>
            <label>
              Slug
              <input
                value={slug}
                required
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                maxLength={100}
                onChange={(event) => setSlug(event.target.value)}
              />
            </label>
            <label>
              Timezone
              <input
                value={timezone}
                required
                onChange={(event) => setTimezone(event.target.value)}
              />
            </label>
            <fieldset className="rolling-plan">
              <legend>Automatic next round</legend>
              <label>
                Timeline
                <select
                  value={planKind}
                  onChange={(event) =>
                    setPlanKind(
                      event.target.value as "none" | "rolling" | "calendar",
                    )
                  }
                >
                  <option value="none">None — schedule rounds manually</option>
                  <option value="rolling">
                    Rolling — starts after publication
                  </option>
                  <option value="calendar">Calendar — monthly schedule</option>
                </select>
              </label>
              {planKind === "rolling" && (
                <label>
                  Round duration in hours
                  <input
                    type="number"
                    required
                    min="1"
                    max="8760"
                    value={rollingHours}
                    onChange={(event) => setRollingHours(event.target.value)}
                  />
                </label>
              )}
              {planKind === "calendar" && (
                <>
                  <label>
                    Open on day of month
                    <input
                      type="number"
                      required
                      min="1"
                      max="28"
                      value={calendarDay}
                      onChange={(event) => setCalendarDay(event.target.value)}
                    />
                  </label>
                  <label>
                    Submission window in days
                    <input
                      type="number"
                      required
                      min="1"
                      max="366"
                      value={calendarDuration}
                      onChange={(event) =>
                        setCalendarDuration(event.target.value)
                      }
                    />
                  </label>
                </>
              )}
              <label>
                Next-round submission limit (optional)
                <input
                  type="number"
                  min="0"
                  value={nextLimit}
                  disabled={planKind === "none"}
                  onChange={(event) => setNextLimit(event.target.value)}
                />
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={autoStart}
                  disabled={planKind === "none"}
                  onChange={(event) => setAutoStart(event.target.checked)}
                />
                Start the successor when this round is published
              </label>
            </fieldset>
            <button className="button" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create series"}
            </button>
            {errorMessage(create.error) && (
              <p className="error-message" role="alert">
                {errorMessage(create.error)}
              </p>
            )}
          </form>
        </section>
      )}
      <section className="admin-list">
        <h2>Your managed series</h2>
        {series.isLoading && <p>Loading series…</p>}
        {series.isError && (
          <p className="error-message" role="alert">
            {errorMessage(series.error) ?? "Series could not be loaded."}
          </p>
        )}
        {series.data?.length === 0 && (
          <p>You do not administer a series yet.</p>
        )}
        {series.data?.map((item) => (
          <Link
            className="panel admin-series-card"
            key={item.id}
            to={`/admin/series/${item.id}`}
          >
            <div>
              <span className="role">{item.timezone}</span>
              <h3>{item.name}</h3>
              <p>{item.description ?? "No description yet."}</p>
            </div>
            <span aria-hidden="true">→</span>
          </Link>
        ))}
      </section>
    </main>
  );
}
