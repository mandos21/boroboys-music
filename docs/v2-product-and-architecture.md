# Music Rounds v2: Product and Architecture Guide

**Status:** accepted design for the v2 rebuild. This document is the implementation
reference; changes to its decisions should be deliberate and recorded here.

## 1. Product intent

Music Rounds is a private application for groups of people to contribute music to
curated playlists. It must support more than one group and more than one active
collection at a time. The original Boro Boys monthly playlist is one instance of
this model, not a limitation of the model.

The basic experience is:

1. An organizer creates a series and one or more timed rounds within it.
2. The organizer selects the contributors for each round, sets their individual
   submission limit, configures restrictions, and chooses a Spotify publishing
   account.
3. Contributors sign in through the deployment's OIDC provider, optionally link
   Spotify and Last.fm accounts, and submit tracks while their round is open.
4. When a contributor chooses a track, the application evaluates the round's
   restrictions and retrieves cached listening evidence for linked members.
5. At the configured publication time, the system freezes the final submission
   set and publishes a Spotify playlist through a durable, retryable background task.
6. A series configured to continue automatically creates and starts its successor
   round after successful publication.
7. The published playlist, its item order, submitter attribution, policy results,
   and relevant listening evidence remain available as history.

The product is intentionally a **small-group curation tool**, not a social network,
music streaming service, recommendation engine, or generic automation platform.

## 2. Product principles and decisions

### 2.1 Explicit rounds, not a global calendar

A calendar month is not an entity. A **round** is an administrator-defined
collection window with `opens_at`, `closes_at`, and `publish_at` timestamps. A
monthly round is a convenient template:

```text
opens_at:  2026-10-01 00:00 America/New_York
closes_at: 2026-11-01 00:00 America/New_York
publish_at: 2026-11-01 00:05 America/New_York
```

The timestamps are stored in UTC and the selected IANA timezone is stored with the
round for display and audit. The server is authoritative for whether a round is
open. This supports monthly, weekly, seasonal, ad-hoc, and overlapping rounds
without special cases.

A series may also have a **round plan**: an administrator-defined successor rule
with a default of `enabled`. A plan specifies the next round's duration, title
pattern, membership source, policies, and publication relationship. It supports
rolling timelines (the next round opens when the previous one successfully
publishes) and calendar timelines (for example, the next calendar month). The plan
creates the next round automatically; administrators do not need to approve each
ordinary round individually.

### 2.2 Series organize history and defaults

A **series** groups related rounds, such as `Boro Boys Monthly`. It provides a
stable name, history scope, timezone default, optional recurrence template, and
default policies. A round snapshots or overrides those defaults. The database must
not impose a global unique month; at most it may enforce a series-specific period
key when an administrator elects to use one.

### 2.3 Membership is round-specific and historical

Reusable contributor groups are useful for quickly creating rounds, but publication
history must not change when a group changes later. Creating a round materializes a
set of `round_members` from selected contributor groups and direct additions.

An administrator may add or remove members while a round is open. Removal revokes
future submission access but does not erase their existing submission, membership
record, or attribution. Published rounds are immutable except for narrowly scoped
administrative corrections recorded in an audit log.

### 2.4 Policies are configurable but code-defined

Restrictions must be represented as configuration of reviewed policy handlers, not
as an arbitrary expression language. Each policy kind has a typed configuration
schema, a deterministic evaluator, user-facing explanation, and tests.

Initial policy kinds:

- `submission_limit`: maximum accepted submissions per member;
- `no_duplicate_in_round`: reject the same canonical Spotify track twice in one
  round, or warn if the organizer chooses that behavior;
- `no_recent_series_repeat`: reject or warn about a track appearing in the prior
  `N` published rounds of the same series;
- `track_availability`: warn when Spotify reports a track unavailable to the
  publishing account's market;
- `explicit_content`: allow, warn, or reject explicit tracks.

Future policies may inspect artist, release date, genre, listening evidence, or a
custom allow/block list. A policy receives explicit scope and data; it must not
quietly query unrelated rounds or groups.

### 2.5 Linked accounts are optional and consent-based

OIDC identifies the person. Spotify and Last.fm are separately linked external
accounts. A member can participate with neither linked; they simply cannot search
Spotify through the app until a publisher or app credential path is available, and
they contribute no listening evidence.

Listening information is sensitive within a small group. The UI must state which
round members can see it, present `not linked` separately from `not listened`, and
allow a member to disconnect an account. Visibility is configured **per linked
account**, rather than per round: the account owner selects whether its evidence is
available to eligible round contributors, series administrators only, or nobody.
The default is available to eligible round contributors and series administrators.

### 2.6 Publication is a stateful operation

Publishing to Spotify is an external side effect, not a database transaction. It
must be modeled as a durable process with progress and retry state. Retrying must
not create a second playlist or duplicate items.

### 2.7 Unpublishing is a constrained reversal

A series administrator may unpublish only the **most recently successfully
published round in that series**. "Most recent" is the highest publication sequence,
not merely the latest record still in `published` state: once a newer round has ever
been published, an older round cannot be altered through this reversal. This is a
correction mechanism, not normal editing: it returns the eligible round to `closed`,
preserves its frozen submissions, and permits correction followed by a new
publication.

Spotify does not offer a Web API endpoint that deletes a playlist; even removing an
owner's association is modeled as unfollowing, not deletion. See [Spotify's playlist
documentation](https://developer.spotify.com/documentation/web-api/concepts/playlists).
The remote reversal therefore clears app-added items, marks the playlist private
where applicable, and removes it from the publisher's library when Spotify permits.
The app records it as an unpublished/retired remote playlist rather than promising
literal deletion. This is the closest safe equivalent and must be clear in the UI.

## 3. Scope

### In scope for v2

- Generic OIDC sign-in and server-side sessions.
- OIDC user auto-provisioning, configurable role/claim mapping, and logout return
  behavior.
- Series, arbitrary-timeline rounds, reusable groups, and round membership
  snapshots.
- Per-member limits, policy evaluation, Spotify search/linking, Last.fm linking,
  listening evidence caching, and Spotify publishing.
- Automatic successor-round planning and starting, enabled by default per series.
- Historical round and playlist views, plus administrative management.
- Reproducible schema migrations, local development, backup-ready deployment, and
  integration tests for core behavior.

### Explicitly out of scope for the first v2 release

- Collaborative Spotify playlists edited directly by every contributor.
- Sending email or chat notifications; background tasks should expose events so this can be
  added later.
- A visual policy-expression builder or a plug-in scripting language.
- Full Spotify listening-history ingestion, recommendations, streaming, or audio
  playback.
- Synchronizing OIDC-provider groups into local contributor groups.

## 4. Architecture overview

Use a modular monolith with three deployable processes and one database:

```text
Browser
  │ HTTPS, same-origin cookie
  ▼
Frontend (React static app) ───► API (FastAPI)
                                      │
                                      ├── PostgreSQL: domain data, sessions,
                                      │   task queue, audit log, cached evidence
                                      ├── OIDC provider: generic identity
                                      ├── Spotify: account linking/search/publish
                                      └── Last.fm: account linking/listening data

Worker (separate FastAPI application command)
  └── runs Procrastinate tasks for schedule reconciliation, publication, and refresh
```

The API and worker share one application package but have separate entry points.
Use [Procrastinate](https://procrastinate.readthedocs.io/en/stable/) as the durable
PostgreSQL-native task queue. It supplies workers, retries, periodic tasks, task
locks, queueing locks, and its own PostgreSQL schema; this deliberately avoids an
additional Redis/RabbitMQ/Celery service. The application owns the domain state that
makes a task safe to retry; Procrastinate owns task dispatch and execution.

Round plans are dynamic administrator data, whereas Procrastinate's direct periodic
schedules are defined in code. Define one frequent static `reconcile_schedules` task
(for example, every minute) which queries due transitions and round plans, then
defers locked per-round tasks. This is Procrastinate's documented pattern for dynamic
scheduling and ensures multiple workers defer a periodic reconciliation only once.

The production frontend is built once and served as static files by the existing
reverse proxy or a small static container. In development, Vite proxies `/api` to
the API. Production browser traffic stays same-origin; the API is not exposed to
arbitrary browser origins.

## 5. Identity, authorization, sessions, and credentials

### 5.1 Generic OIDC

The application is an OIDC relying party, not a Keycloak-specific application. It
uses discovery at:

```text
{OIDC_ISSUER_URL}/.well-known/openid-configuration
```

and the Authorization Code flow with PKCE, `state`, and `nonce`. Validate issuer,
audience/client ID, expiration, nonce, and signature using the provider's JWKS.
Keycloak implements standard discovery endpoints, so it is a normal first provider
rather than a special code path. See [Keycloak's OIDC guide](https://www.keycloak.org/securing-apps/oidc-layers).

The immutable OIDC `sub`, qualified by issuer, is the external identity key. Email
and display name are profile attributes and may change; they are not primary keys.

Deployment configuration:

```text
OIDC_ISSUER_URL=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_SCOPES=openid profile email
OIDC_AUTO_PROVISION_USERS=true
OIDC_REQUIRE_VERIFIED_EMAIL=false
OIDC_ADMIN_CLAIM=roles
OIDC_ADMIN_VALUES=music-admin
OIDC_POST_LOGOUT_REDIRECT_URL=https://music.example.net/
```

`OIDC_AUTO_PROVISION_USERS` creates a local application user on a successful first
login. It does **not** make that user a member of any contributor group. Disabled
auto-provisioning turns unknown authenticated identities into a clear access-denied
state. Claim-to-admin mapping is optional and only grants platform administration;
series and round roles remain local domain data.

Logout clears the local session, then uses the provider's advertised end-session
endpoint when available. The post-logout destination is a configured, validated
application URL, never an arbitrary query parameter.

### 5.2 Server-side sessions

The browser receives only an opaque, random session ID in an `HttpOnly`, `Secure`,
`SameSite=Lax`, path-restricted cookie. Session records live in PostgreSQL initially
and contain local user ID, expiry, creation metadata, and OIDC session identifier
when available. They never contain OIDC, Spotify, or Last.fm access tokens.

All state-changing API calls require a CSRF defense appropriate to cookie auth:
same-origin checks plus a synchronizer/double-submit token sent in a custom header.
OIDC callbacks have independent `state` and `nonce` validation.

### 5.3 Authorization

Use two authorization layers plus contributor membership:

1. **Platform administrator**: manages global settings and can recover data.
2. **Series administrator**: manages a series, every round in it, contributor
   groups, policies, and publication recovery.
3. **Round contributor**: a user is either a current contributor in a round or has
   no round access. There is no round-administrator or round-viewer role.

Authorization is checked by domain policy functions, not only by hiding frontend
buttons. Every repository query that returns private data is scoped by the current
user's series-administration or round-contributor membership.

### 5.4 External-account links

`external_accounts` belongs to one application user and has provider (`spotify` or
`lastfm`), provider subject/username, scopes, connection status, and timestamps.
Provider credentials live in a separate encrypted credential record.

- Spotify uses a dedicated OAuth account-linking flow. The account chosen as a
  round publisher must grant playlist-write scope and can be disconnected or
  reauthorized independently of app login. Spotify's authorization model is scope
  based. [Spotify authorization documentation](https://developer.spotify.com/documentation/web-api/concepts/authorization)
- Last.fm uses its web authorization flow to establish ownership and, when needed,
  an API session key. Its API documentation says session keys persist until revoked,
  so they are protected like refresh tokens. [Last.fm web authentication](https://www.last.fm/api/webauth)

Encrypt credentials with a maintained cryptographic library and a deployment-managed
versioned key set. Store ciphertext, key version, and provider metadata; never log
tokens, session keys, callback codes, or authorization headers. Implement key
rotation by decrypting with an old key and re-encrypting with the current key during
normal credential use or a controlled migration.

## 6. Domain model

The names below are logical entities; migrations choose conventional plural table
names. All entities have UUID primary keys, `created_at`, and `updated_at` unless
noted otherwise. UUIDs avoid exposing sequencing and simplify offline/import tasks.

| Entity | Essential fields and invariants |
| --- | --- |
| `users` | `id`, `oidc_issuer`, `oidc_subject`, profile fields, platform role. Unique `(oidc_issuer, oidc_subject)`. |
| `external_accounts` | `user_id`, provider, provider subject, display name, scopes, connection status, and evidence-visibility setting. One active Spotify account per user initially; allow multiple later only with an explicit UX. |
| `contributor_groups` | Reusable named lists, owned by a series admin or platform admin. |
| `contributor_group_members` | Membership in a reusable group. This is a convenience/source, not historical truth. |
| `series` | Name, slug, description, default timezone, default policy configuration, archival state. |
| `series_admins` | Local administrative grants for a series. |
| `rounds` | `series_id`, title, timezone, `opens_at`, `closes_at`, `publish_at`, status, optional publisher external account, policy snapshot/version. Times must satisfy `opens_at < closes_at <= publish_at`. |
| `round_members` | Materialized contributor snapshot; user, submission limit override, joined/removed times. A unique `(round_id, user_id)` row is retained after removal. Membership grants contribution access; it has no per-round role. |
| `tracks` | Canonical Spotify track ID and normalized immutable metadata snapshot. Do not key solely by name/artist. |
| `submissions` | Round, contributor, track, status, note, submitted/withdrawn times. A contributor can have multiple accepted submissions unless constrained by policy. |
| `policy_evaluations` | Submission/track candidate, policy kind/version, decision, message, structured result, evaluated time. Immutable audit record. |
| `listening_evidence` | External account, canonical track, source, playcount, last played time, match confidence, fetched/expiry times, response status. Unique cache identity by account/track/source. |
| `publications` | Round, selected publisher connection, Spotify playlist ID, state, idempotency key, attempts, last error, timestamps. One active publication per round. |
| `publication_items` | Immutable ordered snapshot of accepted submissions that was published, including attribution and Spotify track URI. Duplicates are allowed. |
| `audit_events` | Actor, action, target type/ID, safe structured before/after data, timestamp. Never includes credentials. |

Important database constraints:

- `rounds` has no global month uniqueness;
- `round_members` is unique per round/user;
- `submissions` must not have a unique user/round constraint;
- `publication_items` is unique by `(publication_id, position)`, **not** track ID;
- `publications` is unique by round;
- membership and policy checks use indexes on round/status/user and series/published
  time.

## 7. Round lifecycle

```text
draft → scheduled → open → closed → publishing → published → unpublishing → closed
                         │                 └── failed (retryable)
                         └── cancelled
```

- **Draft:** administrators configure membership, policy, publisher, and schedule.
- **Scheduled:** the round exists but is not open. Administrators may edit it.
- **Open:** `opens_at <= now < closes_at`; eligible contributors may submit.
- **Closed:** submissions are frozen. Administrators may make audited corrections.
- **Publishing:** a worker owns an active publication task.
- **Published:** Spotify playlist and immutable publication item snapshot exist.
- **Unpublishing:** a worker is performing the constrained latest-round reversal.
  Success returns the round to `closed`; the original publication remains in audit
  history as unpublished.
- **Failed:** a recoverable external/publication failure with visible reason and
  retry control. A failure never silently reopens submissions.

The worker reconciles timestamp-driven transitions, so missed downtime causes a
late transition rather than a permanently stuck round. The transition queries lock
rows and must be idempotent.

On a successful publication, a series with an enabled plan automatically creates
and starts the successor round. For a rolling plan, its open time is the successful
publication time and its close time is calculated from the configured duration. For
a calendar plan, dates are calculated from the configured timezone/calendar rule;
if publication is late enough that the successor would already be closed, the
worker creates a `scheduled` exception requiring an administrator to resolve the
dates rather than silently producing a zero-length round.

## 8. Submission, restrictions, and listening evidence

### 8.1 Submit flow

1. The contributor opens a round detail page and searches Spotify or past tracks.
2. Selecting a candidate creates a transient server-side evaluation request; it
   does not create a submission yet.
3. The API verifies round membership and round openness, loads policy configuration,
   evaluates all policies, and returns errors, warnings, and listening evidence.
4. The contributor confirms warnings and submits. The API repeats critical policy
   checks in one database transaction before persisting the submission.
5. The API stores policy evaluation records and defers a listening-evidence
   refresh task for stale or absent records. The UI may show cached data immediately
   and refresh asynchronously.

There is no client-side-only enforcement. Limits and duplicate checks must use
transactional database queries/constraints designed for concurrent submissions.

### 8.2 Listening evidence

For a selected track, query every current round member who has consented to share
the relevant linked account. Cache a result per member's external account and
canonical track rather than per round, then project the results into the round.

Suggested cache semantics:

- a successful observation is retained as durable, useful evidence; a member cannot
  undo a play, so stale positive data is better than no data;
- `playcount` is displayed as **at least N, observed at time T** when stale, and
  `last_played_at` is likewise labelled with its observation time;
- fresh observations are normally refreshed after 24 hours, but stale observations
  remain visible while a refresh task is queued or a provider is unavailable;
- a manual administrator refresh can bypass the freshness threshold, subject to
  provider rate limits;
- failed, unlinked, private, and no-match results use short negative-cache windows;
- store normalized summary data rather than an unlimited raw listening-history
  archive, while retaining enough audit data to say when and how it was fetched.

Use Last.fm as the primary source for this feature. Spotify's recently-played API
is limited to the current authorized user and a maximum of 50 returned items; it is
not a dependable all-time group-history service. [Spotify recently played reference](https://developer.spotify.com/documentation/web-api/reference/get-recently-played)

Track matching should start with exact Spotify identity where a provider supports it,
then use normalized artist/title matching with an explicit confidence level. Never
present a fuzzy match as a definite play. A `no match` result means only that the
provider returned no match at the recorded query time.

## 9. Publication workflow

Publishing is initiated by a due-task reconciliation or an explicit administrator
action. Both defer the same Procrastinate `publish_round` task configured with a
per-round queueing lock. `publications` supplies the domain-level uniqueness and
idempotency record; the queueing lock prevents duplicate waiting work.

1. The worker locks the round/publication record and verifies it is closed and has
   a valid connected Spotify publisher.
2. It creates an immutable `publication_items` snapshot from accepted submissions,
   preserving order and allowing duplicate tracks.
3. It creates the Spotify playlist if the publication has no remote playlist ID,
   then commits that ID locally immediately.
4. It adds items in provider-supported batches, recording progress after each batch.
5. It verifies completion where the provider permits, marks the publication and
   round published, and emits an audit event.

If any external call fails, the task records a sanitized error and uses bounded
retry/backoff. If Spotify creation succeeded, later attempts reuse the recorded
remote playlist ID. Administrators can see and retry a failed task; they cannot
accidentally start an uncontrolled parallel publication.

### 9.1 Unpublish workflow

`unpublish_round` is a separate durable Procrastinate task. It obtains a series-level lock, proves
that the target has the highest successful publication sequence in that series, and
changes the round to `unpublishing`. It then clears the items managed by this application
from the Spotify playlist, makes it non-public where supported, and removes the
publisher's library association when the provider allows it. Spotify has no true
playlist-deletion endpoint, so this operation must be described as *retiring the
published Spotify playlist*, not deleting it.

After remote retirement succeeds, the task marks the publication unpublished,
retains its item snapshot/audit trail, clears the round's active-publication link,
and returns the round to `closed`. Existing submissions stay frozen until a series
administrator explicitly edits them. Any remote failure leaves `unpublishing` with
a retryable task; it must never falsely claim the playlist was removed.

Importing historical playlists creates a published round and publication snapshot.
It does not infer or mutate old live submissions unless an administrator explicitly
maps attribution during import.

## 10. API design

Use `/api/v1` JSON endpoints and expose a curated OpenAPI document. FastAPI's
schema is the contract; generate TypeScript types/client code from it in frontend
CI rather than hand-maintaining duplicated response types.

Representative resources:

```text
GET    /me
POST   /auth/login
POST   /auth/logout
GET    /account/connections
POST   /account/connections/spotify/start
POST   /account/connections/lastfm/start
DELETE /account/connections/{id}

GET    /series
POST   /series
GET    /series/{series_id}
PATCH  /series/{series_id}
POST   /series/{series_id}/rounds

GET    /rounds?mine=true&status=open
GET    /rounds/{round_id}
PATCH  /rounds/{round_id}
POST   /rounds/{round_id}/members
DELETE /rounds/{round_id}/members/{user_id}
POST   /rounds/{round_id}/evaluate-track
GET    /rounds/{round_id}/listening-evidence?track_id=...
POST   /rounds/{round_id}/submissions
PATCH  /rounds/{round_id}/submissions/{submission_id}
DELETE /rounds/{round_id}/submissions/{submission_id}
POST   /rounds/{round_id}/publish
POST   /rounds/{round_id}/publication/retry
POST   /rounds/{round_id}/unpublish
```

Mutation responses return the updated resource and an `ETag`/version where a stale
administrator edit could overwrite another edit. Mutations are idempotent where a
network retry is likely, especially connection callbacks and publication commands.

Use a consistent error envelope with stable machine code, human message, field
errors, request ID, and safe remediation information. Never expose database errors,
provider responses containing credentials, or authorization internals.

## 11. Frontend architecture

The frontend should be a route-oriented TypeScript React application, not one
stateful `App.tsx` controller. Use Vite, React Router, TanStack Query for all
server state, React Hook Form plus Zod for forms, and generated types from OpenAPI.
Use a small accessible component system built on Radix primitives and Tailwind/CSS
variables; do not create bespoke variants independently in every feature.

Feature-oriented layout:

```text
src/
  app/              router, providers, query client, layout
  api/              generated client and thin domain adapters
  features/
    auth/
    connections/
    rounds/
    series/
    submissions/
    listening-evidence/
    publication/
    admin/
  components/       reusable presentational components only
  lib/              date, permissions, formatting, form utilities
```

Required routes:

- `/`: current open rounds the signed-in user can access;
- `/rounds/:roundId`: overview, schedule, member-visible submissions, and history;
- `/rounds/:roundId/submit`: search, policy result, evidence matrix, and submit;
- `/series/:seriesId`: series history and round list;
- `/settings/connections`: Spotify/Last.fm links and privacy status;
- `/admin/series/:seriesId` and `/admin/rounds/:roundId`: management workflows;
- `/signed-out`: fixed post-logout page.

The UI should be desktop-first but responsive, keyboard-navigable, and semantic.
It should use loading/error/empty states consistently, preserve unsaved form input,
and communicate asynchronous states such as `evidence refreshing` or `publication
retrying`. Client permission checks improve usability but never substitute for API
authorization.

## 12. Database, migrations, and operations

Use SQLAlchemy 2.x mappings and Alembic from the first migration. `metadata.create_all`
is prohibited outside isolated test setup. Application schema changes require:

1. an Alembic revision with upgrade and practical downgrade path;
2. a migration test against an empty database and the preceding revision;
3. indexes/constraints reviewed alongside the application change;
4. a data migration plan when semantics change.

Pin Procrastinate as an application dependency and apply/check its versioned
PostgreSQL schema with Procrastinate's supported CLI during bootstrap and deploy.
Do not recreate or hand-maintain Procrastinate's internal tables in application
Alembic revisions; document the library schema upgrade alongside each dependency
upgrade and run it before workers start on the new version.

Developer commands should include:

```text
make bootstrap       # install dependencies and create local env template
make db-up           # start only local Postgres
make migrate         # alembic upgrade head
make task-schema     # apply/check the pinned Procrastinate PostgreSQL schema
make api             # API with reload
make worker          # Procrastinate worker with reload/dev polling
make web             # Vite dev server
make test
make lint
make typecheck
```

Production configuration comes from deployment-managed environment/secrets, not a
web setup wizard. The first platform administrator is established through a
documented CLI command or an OIDC claim mapping. Compose must mount persistent
Postgres storage, have explicit health checks, and run API/worker separately.

Back up PostgreSQL regularly and test restoration. Provider credentials are part of
the encrypted database backup and require the matching key material during disaster
recovery; document that key-recovery procedure separately.

## 13. Testing and quality gates

Tests should concentrate on behavior and boundaries:

- **Unit:** date/lifecycle transitions, policy handlers, identifier normalization,
  credential encryption, OIDC claim mapping, and task retry decisions.
- **Repository/integration:** real Postgres migrations, row locking, membership
  isolation, concurrent submission-limit enforcement, cache freshness, and task
  locking/idempotency.
- **API:** authenticated/unauthenticated/unauthorized cases, OIDC callback state,
  round CRUD, policy evaluation, and publication command idempotency.
- **Provider contracts:** mocked Spotify/Last.fm/OIDC success, expiry, revocation,
  rate-limit, and partial-failure responses.
- **Frontend:** component/form tests plus browser tests for OIDC return handling,
  joining multiple rounds, submission warnings, and failed-publication recovery.

CI gates: formatter, linter, Python type checking, frontend type checking, unit
tests, Postgres integration tests, migration-from-previous-head test, and production
frontend build. Do not merge a schema/model/API change that lacks an appropriate
test layer.

## 14. Delivery plan

### Phase 0: establish the new baseline

- Archive the v1 code and preserve this document.
- Create the v2 application layout, developer commands, Docker development stack,
  Alembic configuration, CI, and health endpoints.
- Add the pinned Procrastinate dependency, its schema/bootstrap command, a worker
  entry point, and worker health checks before any feature defers a task.
- Add the initial schema only after reviewing it against this document.

### Phase 1: identity and core administration

- Implement generic OIDC login/logout, opaque sessions, auto-provisioning, and
  platform/series authorization.
- Build series, groups, rounds, round plans, and materialized round-membership
  administration.
- Deliver the open-round dashboard and round schedule display.

### Phase 2: submissions and policies

- Implement Spotify linking/search and canonical track persistence.
- Implement submission creation/edit/withdrawal and the initial policy registry.
- Add API and browser tests for overlapping rounds, overlapping memberships, limits,
  duplicate scopes, and boundary times.

### Phase 3: listening evidence

- Implement Last.fm linking, encrypted credentials, consent/visibility behavior,
  evidence cache, stale refresh tasks, and the evidence matrix UI.
- Add rate-limit/backoff behavior and clear unavailable/not-linked presentation.

### Phase 4: publishing and history

- Implement publication snapshots, Procrastinate tasks, Spotify publishing,
  constrained unpublishing/remote retirement, retries, audit views, and historical
  playlist import.
- Implement automatic successor creation/start from the configured round plan.
- Exercise provider partial failures in integration tests before real use.

### Phase 5: operational hardening

- Backups/restores, metrics/logging, key rotation, dependency updates, accessibility
  pass, and a real round run-through with a small test group.

## 15. Definition of done for first real use

The application is ready for a live round only when all of the following are true:

- An admin can run two concurrent rounds with overlapping people and different
  limits, schedules, and policies.
- A contributor cannot read or mutate another private round without membership.
- Membership changes preserve previous attribution and do not rewrite history.
- Submission policy decisions are correct under concurrent requests and explain
  warnings/rejections.
- OIDC works against the configured provider without Keycloak-specific code;
  unknown-user, auto-provisioned-user, logout, and session expiry behavior are
  tested.
- Provider credentials never appear in browser sessions, logs, API responses, or
  audit events, and encrypted credential storage is covered by tests.
- A failed Spotify publish can be retried safely after a playlist has already been
  created remotely.
- The latest published round in a series can be safely unpublished and returned to
  `closed`; an earlier published round cannot be unpublished.
- A series with its default enabled round plan creates and starts the correct
  successor only after successful publication.
- A clean environment can run migrations, start the API/worker/frontend, and pass
  the core integration suite using documented commands.
- PostgreSQL backup restoration has been performed successfully.

## 16. Decisions to revisit later

- SMTP notifications and their delivery/retry model.
- Procrastinate worker concurrency, queue partitioning, and upgrade strategy after
  observing real task volume.
- Additional successor-plan types beyond the initial rolling and calendar plans.
