# Code cleanliness plan

Each item below is independently approvable and independently revertable.
Nothing here changes application behaviour: every item must leave the release
gate (`make verify`) passing and the generated API contract byte-identical,
unless the item explicitly says otherwise.

The layering is not in question. Every internal import was mapped and the
dependency graph is acyclic and correctly ordered: `core` → `db` → `services` →
`tasks` → `api/routes`, with services never reaching back into `api` or
`tasks`. These items are local cleanups inside that structure.

Ordering is deliberate: items 1–2 are mechanical and make every later diff
readable.

## Context: four planned dependencies, never seen through

Architecture doc §11 specifies "React Hook Form plus Zod for forms" and "Radix
primitives and Tailwind/CSS variables". All four packages were installed; none
were adopted.

| Package | Installed | Wired up | Actually used |
|---|---|---|---|
| `tailwindcss` 4.3.3 | yes | vite plugin + `@import "tailwindcss"` | 2 utility classes |
| `react-hook-form` 7.87 | yes | no | zero imports |
| `zod` 3.25 | yes | no | zero imports |
| `prettier` 3.9.6 | yes | no config, absent from scripts and CI | not run |

The resolution differs per package, and is folded into the items below:
Prettier is adopted (item 1), Tailwind is removed (item 2), React Hook Form and
Zod are adopted for forms (item 6).

---

## 1. Adopt Prettier and the React hooks lint rule

**Problem.** Nothing enforces line width in either language. `ruff` sets
`ignore = ["E501"]`; Prettier is installed but has no config and is wired into
nothing. The result is 196 frontend lines over 120 characters and 29 backend
lines over 100 — with single JSX expressions reaching 1221 characters in
`App.tsx`, 1040 in `AdminSeriesPage.tsx`, and 971 in `InvitePanel.tsx`, which
renders its entire UI on one line. Review diffs on these files are effectively
unreadable.

Separately, `eslint.config.mjs` is only `js.recommended` +
`tseslint.recommended`. For a codebase built on hooks and React Query, the
absence of `eslint-plugin-react-hooks` is a real gap — it is why the incomplete
effect dependency arrays in `SubmissionPage` pass lint today.

**Proposed change.**

- Add `.prettierrc` (`printWidth: 100`, defaults elsewhere) to match the
  backend's 100 columns. The dependency is already present.
- Add `"format"` and `"format:check"` scripts; wire `format:check` into
  `make lint` and CI.
- Add `eslint-plugin-react-hooks` with its recommended config.
- Reformat the frontend in **one commit containing nothing else**, so it can be
  skipped wholesale via `.git-blame-ignore-revs`.
- Remove `ignore = ["E501"]` from `pyproject.toml` and reflow the 29 offending
  backend lines by hand.

**Risk.** Low, but the diff is large. The react-hooks rule will surface existing
violations; those get fixed in a *separate* commit from the reformat. If any
violation looks like a real bug rather than a lint nit, stop and report rather
than fix it silently inside a cleanup pass.

---

## 2. Remove Tailwind

**Problem.** Tailwind is fully wired — vite plugin, `@import "tailwindcss"` —
and used for two utility classes. It pays build cost for nothing.

The existing CSS is not the mess Tailwind usually rescues: 580 lines, 133
semantic class names, scoped into three feature files, already driven by CSS
custom properties (`--series-accent`, `--avatar-background`, `--round-cover`).
Doc §11 asks for "Tailwind/CSS variables"; the CSS-variables half is what was
built, and it is coherent.

Adopting Tailwind properly would mean migrating 580 CSS lines, would change
visual output, and would make item 1 *worse* — utility strings lengthen every
element, and JSX line length is the actual problem.

**Proposed change.** Remove the `tailwindcss()` plugin from `vite.config.ts`,
remove `@import "tailwindcss"` from `styles.css`, replace the two utility usages
with existing semantic classes, and drop `tailwindcss` and `@tailwindcss/vite`
from devDependencies.

**Risk.** Low. Verify the built CSS bundle shrinks and the app renders
identically. Any visual difference means a utility class was load-bearing, and
should be caught before merge.

---

## 3. Extract the duplicated domain helpers

**Problem.** Four pieces of domain logic are written out repeatedly.

| Duplication | Locations |
|---|---|
| "is this user a series admin" | `rounds.py:184`, `rounds.py:406`, `rounds.py:725` inline, plus helpers `series._is_series_admin` and `admin._require_series_admin` |
| Spotify profile-image scalar subquery | `rounds.py:285` and `series.py:416`, verbatim |
| `display_name or email or "Unknown listener"` | `rounds.py:318`, `series.py:443` |
| Round wire payload | `admin._round_summary`, `series._round_payload_from_counts`, the series-history round dict, and two dicts in `rounds.py` |

**Proposed change.** A new `app/services/authorization.py` holding the read-side
predicates, since they are domain questions about durable state rather than HTTP
concerns:

```python
def is_series_admin(db: Session, series_id: uuid.UUID, user: User) -> bool: ...
def is_round_member(db: Session, round_id: uuid.UUID, user_id: uuid.UUID) -> bool: ...
```

`admin._require_series_admin` keeps its `HTTPException` behaviour and its home
in the route layer, but calls `is_series_admin` instead of re-querying.

A new `app/api/payloads.py` for the shared read-model fragments:

```python
def spotify_profile_image_subquery(user_column) -> ScalarSelect[str | None]: ...
def contributor_display_name(display_name: str | None, email: str | None) -> str: ...
def round_timeline(round_: Round) -> dict[str, str]:
```

The round payload builders keep their distinct extras (`submittedCount`,
`policySnapshot`, `publisherAccountId`) and compose the shared core, rather than
being forced into one type that serves nobody well.

**Risk.** Low. Pure extraction, covered by `test_series_access.py`,
`test_admin_integration.py`, and `test_evidence_visibility.py`.

---

## 4. Give the test suite a `conftest.py`

**Problem.** There is no `conftest.py`. Across the suite there are 43 hand-built
`User(oidc_issuer="https://issuer.test", ...)` constructions and 36 copies of
`suffix = uuid.uuid4().hex[:12]`.

More consequential: there is no isolation between tests, or between *runs*.
Rows persist in the development database indefinitely. This produced a flake
during the last change — an assertion on a global count passed alone and failed
in the suite, and was worked around by scoping the assertion rather than fixing
the cause.

**Proposed change.**

- `tests/conftest.py` with a session-scoped engine and a function-scoped `db`
  fixture running each test in a transaction rolled back on teardown. Tests that
  deliberately commit (the publication lease tests use two sessions) opt out via
  a marker and clean up explicitly.
- Factory fixtures returning callables: `make_user`, `make_series`,
  `make_round`, `make_spotify_account`, `make_submission`.
- Migrate file by file, one commit each, so a regression bisects to one module.

**Risk.** Medium — the only item that rewrites existing tests, and a careless
migration can silently weaken one. Mitigation: one file per commit, and
re-confirm that the three tests with known fix-coupling (toast timers, evidence
ladder, scheduled publication) still fail against the unfixed code.

---

## 5. Split `admin.py` and `rounds.py` into packages

**Problem.** `admin.py` is 1031 lines spanning series CRUD, contributor groups,
members, rounds, invites, publication commands, and historical import. Eleven
input models occupy the first ~160 lines. `rounds.py` is 893 lines spanning
round reads, drafts, submissions, track search, evidence, and evaluation.

**Proposed change.** Convert both to packages, moving each route together with
the input models it owns, re-exporting one `APIRouter` per package so
`api/router.py` is unchanged:

```
api/routes/admin/{__init__,series,rounds,publications}.py
api/routes/rounds/{__init__,rounds,submissions,discovery}.py
```

Shared helpers (`_member_round`, `_viewer_round`) move to `_common.py`.

**Risk.** Low functionally, large move diff. Tests import route functions
directly by name, so those imports must be updated — doing this after item 4
means fewer test files to touch.

---

## 6. Adopt React Hook Form and Zod; centralise query keys

**Problem.** `AdminSeriesPage` holds 14 `useState` calls, five mutations, four
queries, and four inline forms in one component. It hand-rolls dirty-tracking
that React Hook Form provides directly:

```ts
const [titleEdited, setTitleEdited] = useState(false);
const [closeEdited, setCloseEdited] = useState(false);
const [publishEdited, setPublishEdited] = useState(false);
const selectedTitle = roundTitle || (monthly && !titleEdited ? monthTitle(selectedOpensAt) : "");
```

Those booleans are `formState.dirtyFields`; the derived-default layer is
`defaultValues` + `watch`/`setValue`. `AdminRoundPage` has the same shape.
Validation is ad-hoc `if (!x.trim()) return showToast(...)` chains.

Separately, query keys exist as 18 scattered string-literal shapes, with
invalidation lists duplicated across components. Knowing what a mutation
invalidates currently requires grepping.

**Proposed change.**

- Add `@hookform/resolvers` (**not currently installed**; `react-hook-form` and
  `zod` already are).
- Convert the round-scheduling form in `AdminSeriesPage` and the settings form
  in `AdminRoundPage` to `useForm` with a Zod schema via `zodResolver`. The
  schemas encode the timeline rules currently expressed as imperative checks
  (`opens < closes <= publish`, timezone validity).
- Extract `RoundScheduleForm` from `AdminSeriesPage` — with RHF this is a
  genuine simplification rather than a relocation.
- `src/api/queryKeys.ts` exporting one object of `as const` key builders; every
  `useQuery`/`invalidateQueries` call site uses it, making invalidation
  greppable by symbol.

**Scope note.** Zod is used for *forms only*. Runtime validation of API
responses is deliberately excluded: the backend now has response models on every
endpoint and the frontend types are generated from that contract, so
client-side re-validation would be redundant.

**Risk.** Low-medium. Forms are user-visible; each converted form needs a test
covering submit and at least one validation failure.

---

## 7. Unify artwork selection

**Problem.** Artwork picking exists in five places across two languages:
round-robin-by-contributor in `series._round_artwork_urls_by_round` *and* again
in TypeScript as `RoundPages.balancedArtwork`, plus three separate
`id.int % len(urls)` modulo picks. The two round-robin implementations will
drift, because nothing connects them.

**Proposed change.** Make the server authoritative and delete the client copy.
Extend the round detail response with `artworkUrls: list[str]` and have
`ReleaseRecap` render it instead of recomputing. Collapse the three modulo picks
into one `stable_pick(urls, seed_uuid)` in `app/api/payloads.py`.

**Note.** The one item that changes the API contract, regenerating
`openapi.json` and `schema.ts`.

**Risk.** Low-medium. Visible in the UI; worth a screenshot check before and
after.

---

## 8. Convert routes from hand-built dicts to response models

**Problem.** Every route hand-builds a camelCase dict — `str(x.id)`,
`.isoformat()`, `"opensAt"` — and FastAPI then validates it *back* into a
response model whose `alias_generator` would have produced exactly those keys
from the snake_case field names. There are 27 `isoformat()` calls doing work
Pydantic already does.

```python
# today: build the wire shape by hand, then have Pydantic re-check it
return {"id": str(round_.id), "opensAt": round_.opens_at.isoformat(), ...}

# proposed: construct the model; serialization handles casing and formatting
return RoundListResponse(id=round_.id, opens_at=round_.opens_at, ...)
```

This is the root cause of the drift risk noted in review: the dicts and the
models are two independent descriptions of one shape, kept in agreement by
convention alone.

**Proposed change.** Convert route by route, one commit per module, verifying
after each that `openapi.json` regenerates byte-identical — strong evidence no
wire shape changed.

**Risk.** Highest here, and the reason it is last. It touches every route. The
mitigating factor is unusually strong: the CI contract diff fails loudly on any
accidental shape change. Do not combine with any other item.

---

## 9. Small items

- **`tasks.py` docstring is stale**: still reads "Phase 0 intentionally exposes
  only the scheduler reconciliation task… added in later phases." The module now
  registers six tasks including publishing and retirement.
- **Doc §11 is stale**: it specifies Radix (the code uses `@base-ui/react`, a
  reasonable substitution) and Tailwind (removed in item 2). Reconcile it with
  what is actually built, including the React Hook Form and Zod adoption from
  item 6.
- **Routes import `app.tasks` for the `defer_*` helpers**, pulling the whole
  Procrastinate app and every task definition into the API process. `tasks.py`
  plays two roles: worker-side registry and caller-side defer API. Moving the
  defer helpers to `app/queue.py` would let the API import only what it
  dispatches. Low priority — the current edge is acyclic and defensible.

---

## Summary

| # | Item | Risk | Effort | Contract change |
|---|---|---|---|---|
| 1 | Prettier + react-hooks lint | Low | Large diff | No |
| 2 | Remove Tailwind | Low | Small | No |
| 3 | Extract duplicated domain helpers | Low | Medium | No |
| 4 | Test `conftest.py` and factories | Medium | Large | No |
| 5 | Split `admin.py` / `rounds.py` | Low | Medium | No |
| 6 | React Hook Form + Zod + query keys | Low-med | Medium | No |
| 7 | Unify artwork selection | Low-med | Small | **Yes** |
| 8 | Response models instead of dicts | High | Large | No (verified) |
| 9 | Stale docs, `defer_*` placement | Low | Small | No |
