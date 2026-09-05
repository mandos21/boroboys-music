# Music Rounds

Music Rounds is a private, self-hosted tool for timed music-submission rounds and Spotify publishing.

This is the clean v2 rebuild. The implementation contract is in
[docs/v2-product-and-architecture.md](docs/v2-product-and-architecture.md); the
previous prototype remains in `main` branch history.

## Layout

- `backend/` — FastAPI API, Alembic schema, and Procrastinate tasks.
- `frontend/` — TypeScript React application.
- `docs/` — product and architectural decisions.

## Status

Phase 0 is in progress: project structure, health endpoint, migration scaffolding,
worker entry point, and a frontend shell are present. Domain workflows are not yet
implemented.

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
```

Copy `.env.example` to `.env` before starting local services. Never commit secrets.
