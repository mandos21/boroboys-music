# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Music Rounds is a private, self-hosted app for timed music-submission rounds
that publish to Spotify playlists. This is the "v2" clean rebuild; the
previous prototype lives only in `main`'s history. The implementation contract
and all product/architecture decisions are in
[docs/v2-product-and-architecture.md](docs/v2-product-and-architecture.md) —
read it before making non-trivial product or schema decisions, since it
records *why* things work the way they do (e.g. why rounds aren't tied to
calendar months, why membership is historical, why unpublish is constrained to
the most recent round). Treat its decisions as binding unless the user says
otherwise; if you change one, update the doc in the same change.

Note: the doc's proposed frontend feature layout (`auth/`, `series/`,
`listening-evidence/`, `publication/`) differs from what's actually on disk
(`admin/`, `connections/`, `genres/`, `profiles/`, `rounds/`, `submissions/`).
Follow the actual directory layout described below, not the doc's example.

## Commands

All commands run from the repo root via `make` unless noted.

```text
make setup              # install Poetry (if missing), backend deps, frontend deps, .env
make db-up              # start local Postgres only
make migrate            # alembic upgrade head
make api                # FastAPI with reload (also runs db-up + migrate)
make worker             # Procrastinate worker
make web                # Vite dev server (localhost:5173, proxies /api)
```

Quality gates:

```text
make test               # backend pytest + frontend vitest, against music_rounds_test
make lint                # ruff (backend) + eslint/prettier (frontend)
make typecheck          # mypy --strict (backend) + tsc -b (frontend)
make verify             # alembic check + lint + typecheck + pytest + frontend build (full local CI gate)
make visual             # Playwright screenshot comparisons (light/dark x phone/tablet/desktop)
make a11y               # Playwright axe accessibility smoke checks
```

- Backend tests **require** `TEST_DATABASE_URL` to point at a database whose
  name ends in `_test`; `conftest.py` refuses to run otherwise, and pytest
  never touches the database the running API uses. `make test-db` creates it.
- Run a single backend test: `cd backend && TEST_DATABASE_URL=... poetry run pytest tests/test_submission_integration.py::test_name`.
- Run a single frontend test: `cd frontend && npm run test -- SubmissionPage` (vitest).
- Run one Playwright spec: `cd frontend && npx playwright test e2e/<file>.spec.ts`.
- Backend tests run against **real PostgreSQL**, never mocks/sqlite — the code
  relies on row locks, advisory locks, and `ON CONFLICT`, and the test `db`
  fixture wraps each test in a transaction that's rolled back afterward.
- Regenerate the API contract after changing backend routes/schemas:
  `make api-contract` (writes `backend/openapi.json` and
  `frontend/src/api/schema.ts`). CI fails if either is out of sync with what's
  committed.
- Update a Playwright visual baseline intentionally: `cd frontend && npm run test:visual -- --update-snapshots`, then commit the changed `e2e/*.spec.ts-snapshots/` files alongside the UI change.
- Historical playlist import (one-time, dry-run first): `make history-dry-run SERIES_SLUG=... PUBLISHER_ACCOUNT_ID=... IDENTITY_MAP=...`, then `make history-import CONFIRM_HISTORICAL_IMPORT=yes ...`. Never call Spotify during import.

## Architecture

Modular monolith, three deployable processes sharing one Python package, one Postgres database:

- **API** (`backend/app`, FastAPI) — serves the frontend and does all request/response work.
- **Worker** (same package, `procrastinate --app=app.tasks.app worker`) — runs durable background tasks (schedule reconciliation, Spotify publication, evidence refresh) via [Procrastinate](https://procrastinate.readthedocs.io/en/stable/), a Postgres-native task queue. There is deliberately no Redis/RabbitMQ/Celery. Procrastinate's own schema is managed by Alembic migrations — never hand-edit or recreate its tables.
- **Frontend** (`frontend/`, React/Vite) — built once, served as static files in production; Vite proxies `/api` in dev. Same-origin only.

Round scheduling (open/close/publish transitions and series "round plans" for
auto-continuation) is reconciled by one frequent periodic task that queries
due transitions and defers locked per-round tasks — administrator-authored
round plans are dynamic data, not code-defined cron schedules.

### Backend layout (`backend/app/`)

- `main.py` — FastAPI app assembly.
- `api/routes/` — route modules, split into contributor-facing (`rounds/`, `submissions.py`, `profiles.py`, `connections.py`, `series.py`, `auth.py`) and `admin/` (series/round/publication management). `_common.py` files hold shared route dependencies per group.
- `services/` — domain logic: `policies.py` (submission-restriction handlers), `publications.py` (publish/unpublish workflow), `lifecycle.py` (round state transitions), `evidence.py` + `lastfm.py` (listening evidence caching), `spotify.py`, `authorization.py`, `membership.py`, `credential_rotation.py`, `historical_import.py`, `notifications.py`/`email.py`/`mattermost.py`.
- `auth/oidc.py` — generic OIDC relying-party flow (discovery, PKCE, state/nonce).
- `core/config.py` / `core/security.py` — settings and credential encryption.
- `db/models.py` — all SQLAlchemy models (see domain model below); `db/session.py` for engine/session setup.
- `tasks.py` — Procrastinate app and task definitions.
- `cli/` — one-off/operational scripts run via `poetry run python -m app.cli.<name>` (historical import, credential rotation, artwork/genre backfills).
- `data/genres-tree.yaml` — canonical genre taxonomy data consumed by `services/genre_taxonomy.py`.

Schema changes always go through an Alembic revision (`backend/migrations/versions/`) with a real downgrade path — never `metadata.create_all` outside test setup. `alembic check` (via `make verify` or CI) catches model/migration drift.

### Domain model essentials (see doc §6 for full field list)

Identity is OIDC-first: `User` is keyed by `(oidc_issuer, oidc_subject)`, not
email. Spotify/Last.fm are separate optional `ExternalAccount` links with
credentials in a separate encrypted `ExternalCredential` table — access tokens
never live on the session or user record. Three authorization layers:
platform admin, `SeriesAdmin`, and per-`Round` `RoundMember` (contributor or
no access — no round-level admin/viewer role). A `Series` groups `Round`s;
each `Round` materializes its own `RoundMember`s at creation time so that
publication history doesn't shift when a `ContributorGroup` changes later.
`Submission` → `PolicyEvaluation` (per configured policy, e.g.
`submission_limit`, `no_duplicate_in_round`) → frozen at close →
`Publication`/`PublicationItem` (durable, retryable Spotify publish, tracked
separately from the domain transaction). `AuditEvent` records administrative
corrections to otherwise-immutable published rounds.

### Frontend layout (`frontend/src/`)

Route-oriented React (Router v7), not one stateful root controller. TanStack
Query for all server state; React Hook Form + Zod for forms; types generated
from the backend's OpenAPI schema (`src/api/schema.ts`, regenerate via
`make api-contract`, never hand-edit). Query keys are centralized in
`src/api/queryKeys.ts` so cache invalidation is greppable by symbol rather
than by string literal.

- `app/` — router, providers, query client, top-level layout.
- `api/` — generated schema, `client.ts`, query keys.
- `features/<name>/` — one directory per feature area (`admin`, `connections`, `genres`, `profiles`, `rounds`, `submissions`), each owning its components, tests, and a scoped `.css` file.
- `components/` — reusable presentational components only (no feature logic).
- `lib/` — date/format/avatar/performance utilities.

Styling is hand-written CSS driven by custom properties, not Tailwind (Tailwind was installed and deliberately removed after going unused — don't reintroduce utility classes). Accessible primitives come from Base UI. Don't invent bespoke component variants per-feature; extend the shared ones in `components/`.

### Testing

Backend: unit tests for policy/lifecycle/credential logic, integration tests
against real Postgres for locking/idempotency/membership isolation, API tests
for auth states and command idempotency, provider-contract tests with mocked
Spotify/Last.fm/OIDC. Frontend: component/form tests (vitest) plus Playwright
tests that intercept API calls with committed fixtures (no OIDC or real DB
needed) covering functional flows, cross-viewport/theme visual regression,
and axe accessibility smoke checks. CI (`.github/workflows/ci.yml`) runs the
full gate — formatter, lint, mypy strict, tsc, both test suites, Postgres
migration-from-previous-head, OpenAPI/schema drift check, production frontend
build, and Docker image builds — and pins the exact Playwright container
image + installs the `fonts-inter` package because visual snapshots are only
pixel-stable inside that specific OS/font/browser combination.

## Notes

- `playlist_rounds/`, `historical_data.csv*`, and other historical bundle files are private/local-only and gitignored — never assume they're committed elsewhere.
- Copy `.env.example` to `.env` for local secrets; never commit real secrets.
- License is AGPL-3.0-only — running a modified version as a network service requires offering that version's source per AGPL §13.
