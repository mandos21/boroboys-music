import { useRef } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { post } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";

const createSeriesSchema = z.object({
  name: z.string().trim().min(1, "Give the series a name.").max(200),
  slug: z
    .string()
    .min(1, "Add a URL name.")
    .max(100)
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and hyphens."),
  timezone: z.string().min(1, "Choose a timezone."),
});

type CreateSeriesValues = z.infer<typeof createSeriesSchema>;

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** A deliberately small first step; scheduling and membership belong in the series workspace. */
export function SeriesCreatePanel() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const slugEdited = useRef(false);
  const form = useForm<CreateSeriesValues>({
    resolver: zodResolver(createSeriesSchema),
    defaultValues: {
      name: "",
      slug: "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    },
  });
  const { formState, handleSubmit, register, setValue } = form;
  const create = useMutation({
    mutationFn: (values: CreateSeriesValues) =>
      post<{ id: string }>("/admin/series", {
        name: values.name.trim(),
        slug: values.slug,
        timezone: values.timezone,
        default_policies: [],
        // Deliberately omit auto_start_next_round so the API's product default
        // remains the single source of truth. A cadence is selected later.
        round_plan: null,
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.series() });
      queryClient.invalidateQueries({ queryKey: queryKeys.adminSeries() });
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
  const name = register("name");
  const slug = register("slug");

  return (
    <section className="panel series-create-panel" aria-labelledby="create-series-heading">
      <div>
        <p className="eyebrow">Start something new</p>
        <h2 id="create-series-heading">Create a series</h2>
        <p>
          Make a monthly check-in, a themed prompt, or an ongoing place to swap what has caught your
          ear.
        </p>
      </div>
      <form
        className="admin-round-form"
        noValidate
        onSubmit={handleSubmit((values) => create.mutate(values))}
      >
        <label>
          Name
          <input
            {...name}
            maxLength={200}
            onChange={(event) => {
              name.onChange(event);
              if (!slugEdited.current) {
                setValue("slug", slugify(event.target.value), { shouldValidate: true });
              }
            }}
          />
          {formState.errors.name && (
            <span className="error-message">{formState.errors.name.message}</span>
          )}
        </label>
        <details className="advanced-options">
          <summary>Advanced options</summary>
          <div>
            <label>
              URL name
              <input
                {...slug}
                maxLength={100}
                onChange={(event) => {
                  slugEdited.current = true;
                  slug.onChange(event);
                }}
              />
              <span className="field-hint">Used in the series URL.</span>
              {formState.errors.slug && (
                <span className="error-message">{formState.errors.slug.message}</span>
              )}
            </label>
            <label>
              Timezone
              <input {...register("timezone")} />
              <span className="field-hint">
                Detected from this browser. Change it if the series follows another place.
              </span>
              {formState.errors.timezone && (
                <span className="error-message">{formState.errors.timezone.message}</span>
              )}
            </label>
          </div>
        </details>
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
  );
}
