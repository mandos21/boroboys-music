import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { post } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";

/** A deliberately small first step; scheduling and membership belong in the series workspace. */
export function SeriesCreatePanel() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>("/admin/series", {
        name,
        slug,
        timezone,
        default_policies: [],
        auto_start_next_round: false,
        round_plan: null,
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["series"] });
      queryClient.invalidateQueries({ queryKey: ["admin-series"] });
      showToast({
        title: "Series created",
        description: "Add people, a schedule, and automation in its workspace.",
      });
      navigate(`/admin/series/${result.id}`);
    },
    onError: () =>
      showToast({
        title: "Couldn’t create series",
        description: "Check the details and try again.",
        tone: "error",
      }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <section className="panel series-create-panel" aria-labelledby="create-series-heading">
      <div>
        <p className="eyebrow">Start something new</p>
        <h2 id="create-series-heading">Create a series</h2>
        <p>Make a monthly check-in, a themed prompt, or an ongoing place to swap what has caught your ear.</p>
      </div>
      <form onSubmit={submit}>
        <label>
          Name
          <input
            value={name}
            required
            maxLength={200}
            onChange={(event) => {
              setName(event.target.value);
              if (!slugEdited) {
                setSlug(
                  event.target.value
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, "-")
                    .replace(/^-|-$/g, ""),
                );
              }
            }}
          />
        </label>
        <details className="advanced-options">
          <summary>Advanced options</summary>
          <div>
            <label>
              URL name
              <input
                value={slug}
                required
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                maxLength={100}
                onChange={(event) => {
                  setSlugEdited(true);
                  setSlug(event.target.value);
                }}
              />
              <span className="field-hint">Used in the series URL.</span>
            </label>
            <label>
              Timezone
              <input value={timezone} required onChange={(event) => setTimezone(event.target.value)} />
              <span className="field-hint">Detected from this browser. Change it if the series follows another place.</span>
            </label>
          </div>
        </details>
        <button className="button" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create series"}
        </button>
        {errorMessage(create.error) && <p className="error-message" role="alert">{errorMessage(create.error)}</p>}
      </form>
    </section>
  );
}
