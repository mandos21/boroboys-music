# Music Rounds

Music Rounds is a private, self-hosted tool for timed music-submission rounds and Spotify publishing.

This is the clean v2 rebuild. The implementation contract is in
[docs/v2-product-and-architecture.md](docs/v2-product-and-architecture.md); the
previous prototype remains in `main` branch history.

Operational procedures, including the required backup/restore drill and credential
key rotation, are in [docs/operations.md](docs/operations.md).
The final deployment and small-group rehearsal are documented in
[docs/first-live-run.md](docs/first-live-run.md).

## Layout

- `backend/` — FastAPI API, Alembic schema, and Procrastinate tasks.
- `frontend/` — TypeScript React application.
- `docs/` — product and architectural decisions.

## Status

The v2 rebuild has the planned application workflows: generic OIDC sessions, core
administration, submissions and policy evaluation, Last.fm evidence caching, and
durable Spotify publication. Operational checks—including migration drift,
credential rotation, backup restoration, API-contract generation, and local
PostgreSQL integration coverage—are in place. It still needs the configured live
OIDC/provider verification and a small real-round rehearsal before first use; the
implementation contract remains the authoritative checklist.

## Local development

`make setup` (also available as `make dev-setup` or the backwards-compatible
`make bootstrap`) installs Poetry automatically when it is missing, installs
the backend development environment, installs the locked frontend dependencies,
and creates `.env` from `.env.example` if needed. It requires Python 3.14+,
`curl` for automatic Poetry installation, and Node.js/npm for the Vite frontend.

```text
make setup
make db-up
make migrate
make task-schema
```

Run the API, worker, and frontend in separate terminals:

```text
make api
make worker
make web
```

The local frontend is at `http://localhost:5173`; API health is at
`http://localhost:8000/api/v1/health`. OIDC and provider integrations remain
disabled until their values are filled in `.env`.

## Historical playlist import

The private historical bundle is deliberately ignored by Git. It contains one
CSV named after each Spotify playlist ID and a local tab-separated mapping of
historical email addresses to immutable OIDC subjects. The importer never calls
Spotify: it reconstructs the ordered published playlist, repeated entries,
submission timestamps, and per-round contributor limits from that bundle.

First create the target series and add the owner of the selected Spotify account
as a series administrator. The historical import itself makes no Spotify calls,
so its account may be an inactive credential-less historical anchor; use an active
linked account later for live publication. Then validate the
entire bundle before writing anything:

```text
make history-dry-run SERIES_SLUG=your-series \
  PUBLISHER_ACCOUNT_ID=your-spotify-account-uuid \
  IDENTITY_MAP=/private/path/email-to-oidc-subject.tsv
```

The dry run refuses missing identity mappings, duplicate playlist IDs already in
the database, or a publisher that is not a series administrator. When its report
is correct, run the same command as an explicit, one-time transaction:

```text
make history-import CONFIRM_HISTORICAL_IMPORT=yes SERIES_SLUG=your-series \
  PUBLISHER_ACCOUNT_ID=your-spotify-account-uuid \
  IDENTITY_MAP=/private/path/email-to-oidc-subject.tsv
```

The source directory defaults to the ignored `playlist_rounds/` directory at the
repository root. Imported playlists are immutable historical publications and
cannot be retired remotely.

## Docker development stack

Docker does not require Poetry, Python, Node.js, or npm on the host. After
reviewing `.env` and adding any provider credentials needed for the flow being
tested, build and start PostgreSQL, the API, the Procrastinate worker, and the
Nginx-served frontend with:

```text
make docker-up
```

The frontend is available at `http://localhost:5173`, the API at
`http://localhost:8000`, and the API container automatically applies Alembic
migrations and the Procrastinate schema before serving requests. Useful Docker
commands are:

```text
make docker-build   # build images without starting them
make docker-logs    # follow API, worker, and frontend logs
make docker-down   # stop containers; retain the named PostgreSQL volume
```

To remove the local database volume as well, use `docker compose down -v` when
you are certain the disposable local data is no longer needed.

## Quality commands

```text
make test
make lint
make typecheck
make verify
make visual
make a11y
```

`make test` and `make verify` create and use `music_rounds_test`, never the
database configured for the running API. Backend pytest also refuses to start
unless `TEST_DATABASE_URL` names a database ending in `_test`; point that value
at a disposable PostgreSQL database when not using the local Compose stack.

## Browser quality checks

The frontend includes deterministic Playwright coverage for the dashboard, series,
round, submission, profile, and administration workspace. It intercepts API requests
with committed fixture data, so it neither requires OIDC nor touches a local database.
Visual comparisons cover phone, tablet, and desktop viewports in light and dark themes; the
same pages also receive a focused axe accessibility smoke check. The first install on
a development machine needs the browser binary once:

```text
cd frontend
npx playwright install chromium
cd ..
make visual
make a11y
```

Review screenshot changes intentionally. To update an approved visual baseline, run
`cd frontend && npm run test:visual -- --update-snapshots` and commit the resulting
`e2e/*.spec.ts-snapshots/` files with the UI change.

Copy `.env.example` to `.env` before starting local services. Never commit secrets.
