import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { patch } from "../../api/client";
import { Button } from "../../components/ui/button";
import { useToast } from "../../components/ui/ToastProvider";
import { PolicyEditor } from "./PolicyEditor";
import { errorMessage } from "./adminUtils";

type Policy = Record<string, unknown>;

export function PolicySettings({
  id,
  scope,
  policies: initialPolicies,
  onSaved,
}: {
  id: string;
  scope: "round" | "series";
  policies: Policy[];
  onSaved: () => void;
}) {
  const [policies, setPolicies] = useState(initialPolicies);
  const { showToast } = useToast();
  const save = useMutation({
    mutationFn: () =>
      patch(
        scope === "round" ? `/admin/rounds/${id}` : `/admin/series/${id}`,
        scope === "round" ? { policy_snapshot: policies } : { default_policies: policies },
      ),
    onSuccess: () => {
      onSaved();
      showToast({
        title: scope === "round" ? "Round checks saved" : "Series defaults saved",
        description:
          scope === "round"
            ? "New and changed submissions use these checks. Existing entries stay accepted."
            : "Rounds created from now on will inherit these checks.",
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t save round checks",
        description: errorMessage(error) ?? "Try again in a moment.",
        tone: "error",
      }),
  });

  return (
    <div className="admin-round-form">
      <PolicyEditor value={policies} onChange={setPolicies} scope={scope} />
      <p className="field-hint">
        {scope === "round"
          ? "Changes apply to new submissions and replacements. Tracks already accepted stay in the round."
          : "These defaults are copied into future rounds. Existing rounds keep their own checks."}
      </p>
      <Button
        type="button"
        disabled={save.isPending || JSON.stringify(policies) === JSON.stringify(initialPolicies)}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : scope === "round" ? "Save round checks" : "Save defaults"}
      </Button>
      {errorMessage(save.error) && <p className="error-message">{errorMessage(save.error)}</p>}
    </div>
  );
}
