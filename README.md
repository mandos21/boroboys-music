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

## Developer commands

```text
make bootstrap
make db-up
make migrate
make task-schema
make api
make worker
make web
make test
make lint
make typecheck
make verify
```

Copy `.env.example` to `.env` before starting local services. Never commit secrets.
