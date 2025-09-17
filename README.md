# boroboys-music

Monthly Spotify playlist curator for the Boro Boys community. Collect submissions from registered listeners, build collaborative playlists, and surface Last.fm insights via a lightweight Streamlit app backed by PostgreSQL.

## Key Features
- Streamlit UI for monthly submissions, playlist history, and analytics
- Spotify OAuth login so listeners authenticate with their own Spotify account
- Spotify integration to search tracks and publish finalized playlists with user tokens
- Last.fm integration to display listening stats and tags alongside submissions
- PostgreSQL persistence with rich track metadata for future analysis
- Admin tooling to edit playlists and lock monthly submissions
- Background jobs to finalize playlists and sync external metadata

## Tech Stack
- Python 3.10+
- Streamlit for the web interface
- SQLAlchemy + Alembic on PostgreSQL
- Spotipy (Spotify Web API) and Pylast (Last.fm API)
- APScheduler for time-based tasks
- Poetry for dependency management

## Repository Layout
- `app/` - application source code (config, services, database, Streamlit UI)
- `docs/` - architecture and planning documents
- `tests/` - automated test suite

See `docs/architecture.md` for a deeper architectural overview and roadmap.

## Local Development
1. Install [Poetry](https://python-poetry.org/) and ensure Python 3.10+ is available.
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Launch the Streamlit app:
   ```bash
   poetry run streamlit run app/streamlit_app.py
   ```
4. On first launch you'll see the setup wizard. Unlock it with the default password `boroboys-init`, provide database host/user/password, Spotify app credentials, and create the initial admin user. The wizard writes `.env`, initializes the database schema, and reloads the app.
5. Sign in with Spotify from the sidebar to explore the submission tools and playlist history. Users are created automatically on first login.
6. Apply database migrations (once created):
   ```bash
   poetry run alembic upgrade head
   ```

## Next Steps
- Flesh out database models, services, and initial migration
- Implement Spotify/Last.fm clients with unit tests
- Build Streamlit pages for submissions and playlist history
- Wire up monthly scheduler and admin management tools
