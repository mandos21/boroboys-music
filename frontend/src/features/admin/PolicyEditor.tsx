type Policy = Record<string, unknown>;

type PolicyDefinition = {
  kind: string;
  name: string;
  description: string;
  supportsLookback?: boolean;
};

const definitions: PolicyDefinition[] = [
  {
    kind: "no_duplicate_in_round",
    name: "No duplicate in this round",
    description: "Stops the same Spotify track from appearing twice in one playlist.",
  },
  {
    kind: "duplicate_in_series",
    name: "No repeat in this series",
    description: "Checks every accepted submission in this series.",
  },
  {
    kind: "no_recent_series_repeat",
    name: "No recent repeat",
    description: "Checks a configurable number of recently published rounds.",
    supportsLookback: true,
  },
  {
    kind: "explicit_content",
    name: "Explicit-content check",
    description: "Uses Spotify’s explicit-content flag.",
  },
  {
    kind: "track_availability",
    name: "Track availability check",
    description: "Flags tracks Spotify reports as unavailable.",
  },
];

type PolicyEditorProps = {
  value: Policy[];
  onChange: (policies: Policy[]) => void;
};

export function PolicyEditor({ value, onChange }: PolicyEditorProps) {
  const available = definitions.filter(
    (definition) => !value.some((policy) => policy.kind === definition.kind),
  );

  function update(index: number, next: Policy) {
    onChange(value.map((policy, current) => (current === index ? next : policy)));
  }

  return (
    <fieldset className="policy-editor">
      <legend>Round checks</legend>
      <p className="field-hint">
        These checks are snapshotted when the round is scheduled, so future policy changes never
        rewrite past decisions.
      </p>
      <div className="policy-list">
        {value.map((policy, index) => {
          const definition = definitions.find((item) => item.kind === policy.kind);
          const kind = typeof policy.kind === "string" ? policy.kind : "Custom policy";
          return (
            <article className="policy-editor-card" key={`${kind}-${index}`}>
              <div>
                <strong>{definition?.name ?? kind}</strong>
                <p>
                  {definition?.description ??
                    "A server-defined policy preserved in this round snapshot."}
                </p>
              </div>
              <label>
                On match
                <select
                  value={typeof policy.on_match === "string" ? policy.on_match : "reject"}
                  onChange={(event) => update(index, { ...policy, on_match: event.target.value })}
                >
                  <option value="reject">Reject submission</option>
                  <option value="warn">Warn, then allow confirmation</option>
                  <option value="accept">Record without blocking</option>
                </select>
              </label>
              {definition?.supportsLookback && (
                <label>
                  Published rounds to check
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={typeof policy.lookback_rounds === "number" ? policy.lookback_rounds : 1}
                    onChange={(event) =>
                      update(index, { ...policy, lookback_rounds: Number(event.target.value) })
                    }
                  />
                </label>
              )}
              <button
                className="text-button danger"
                onClick={() => onChange(value.filter((_, current) => current !== index))}
                type="button"
              >
                Remove
              </button>
            </article>
          );
        })}
      </div>
      {available.length > 0 && (
        <label className="policy-add">
          Add a check
          <select
            defaultValue=""
            onChange={(event) => {
              const definition = definitions.find((item) => item.kind === event.target.value);
              if (!definition) return;
              onChange([
                ...value,
                {
                  kind: definition.kind,
                  on_match: "reject",
                  ...(definition.supportsLookback ? { lookback_rounds: 1 } : {}),
                },
              ]);
              event.currentTarget.value = "";
            }}
          >
            <option disabled value="">
              Choose a policy
            </option>
            {available.map((definition) => (
              <option key={definition.kind} value={definition.kind}>
                {definition.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {value.length === 0 && (
        <p className="field-hint">
          No round-specific checks. The series defaults apply if configured.
        </p>
      )}
    </fieldset>
  );
}
