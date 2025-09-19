# Boro Boys Music Backend

FastAPI + PostgreSQL API that powers the Boro Boys Music playlist curator. The backend exposes authenticated endpoints for Spotify submissions, playlist management, and admin tooling that the new React frontend consumes.

## Key Features
- Versioned `/api/v1` REST surface for submissions, playlists, invites, and setup workflows
- Spotify OAuth login so listeners authenticate with their own Spotify account
- Spotify integration to search tracks and publish finalized playlists with user tokens
- Last.fm integration to display listening stats and tags alongside submissions
- PostgreSQL persistence with rich track metadata for future analysis
- Admin tooling to edit playlists, issue invites, import Spotify playlists, and lock monthly submissions
- Background jobs to finalize playlists and sync external metadata

## Tech Stack
- Python 3.10+
- FastAPI + Starlette session middleware
- SQLAlchemy + Alembic on PostgreSQL
- Spotipy (Spotify Web API) and Pylast (Last.fm API)
- APScheduler for time-based tasks
- Poetry for dependency management

## Layout
- `app/` – application source (config, services, API routers, database layer)
- `docs/` – architecture and roadmap notes for the backend
- `tests/` – pytest suite
- `.env.example` – sanitized template for local configuration

## Local Development
1. Install [Poetry](https://python-poetry.org/) and ensure Python 3.10+ is available.
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Launch the API with auto-reload:
   ```bash
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
4. Complete setup through the REST endpoints:
   - `GET /api/v1/setup/status`
   - `POST /api/v1/setup/unlock`
   - `POST /api/v1/setup/initialize`
5. Start the React frontend (see `../../frontend/README.md`) and authenticate via Spotify using the `/api/v1/auth/login` endpoint.
6. Run tests:
   ```bash
   poetry run pytest
   ```

## Configuration
- Use `.env.example` as a template and keep real secrets out of version control.
- `FRONTEND_REDIRECT_URL` should point at the Node app (defaults to `http://localhost:5173/`).
- The setup API will persist `.env` and seed the first admin user. Re-run it with `overwrite_env=true` if you need to regenerate secrets locally.

## Next Steps
- Add Alembic migrations and database fixtures for automated testing.
- Expand API coverage with integration tests for submissions, playlist imports, and admin workflows.
- Wire scheduler jobs into the deployment topology once hosted infrastructure is available.
