"""Entry point for the Streamlit application."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import secrets

import streamlit as st
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import or_, select

from app.auth.spotify_auth import create_spotify_oauth, refresh_access_token
from app.bootstrap import (
    DEFAULT_CONFIG,
    build_database_url_from_config,
    create_or_update_admin_user,
    initialize_database,
    write_env_file,
)
from app.config import get_settings, reset_settings_cache
from app.db import crud, models
from app.db.session import session_scope
from app.schemas import PlaylistRead
from app.security import hash_password
from app.services.spotify_service import SpotifyService

st.set_page_config(page_title="Boro Boys Monthly Playlist", layout="wide")

INITIAL_SETUP_PASSWORD = "boroboys-init"


def ensure_session_defaults() -> None:
    if "setup_unlocked" not in st.session_state:
        st.session_state.setup_unlocked = False
    if "oauth_state" not in st.session_state:
        st.session_state.oauth_state = secrets.token_urlsafe(16)


def try_load_settings():
    try:
        return get_settings()
    except (ValidationError, ValueError):
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Settings load failed: %s", exc)
        return None


def render_initial_setup() -> None:
    ensure_session_defaults()
    st.title("Boro Boys Monthly Playlist — Initial Setup")

    if not st.session_state.setup_unlocked:
        st.info("This instance is not configured. Unlock the setup wizard to continue.")
        with st.form("unlock_setup"):
            password = st.text_input("Setup password", type="password")
            submitted = st.form_submit_button("Unlock setup")
        if submitted:
            if password == INITIAL_SETUP_PASSWORD:
                st.session_state.setup_unlocked = True
                st.success("Setup unlocked. Configuration form loading…")
                st.experimental_rerun()
            else:
                st.error("Incorrect password. Please try again.")
        return

    if Path(".env").exists():
        st.warning("Existing .env detected. Enable overwrite to replace it.")

    with st.form("initial_setup_form"):
        st.subheader("Database Connection")
        db_col1, db_col2 = st.columns(2)
        database_host = db_col1.text_input("Host", value=DEFAULT_CONFIG["DATABASE_HOST"])
        database_port = db_col2.number_input(
            "Port", value=int(DEFAULT_CONFIG["DATABASE_PORT"]), min_value=1, max_value=65535, step=1
        )
        db_col3, db_col4 = st.columns(2)
        database_name = db_col3.text_input("Database name", value=DEFAULT_CONFIG["DATABASE_NAME"])
        database_user = db_col4.text_input("Database user", value=DEFAULT_CONFIG["DATABASE_USER"])
        database_password = st.text_input(
            "Database password", value=DEFAULT_CONFIG["DATABASE_PASSWORD"], type="password"
        )

        st.subheader("Spotify API Credentials")
        spotify_client_id = st.text_input("Client ID", value="")
        spotify_client_secret = st.text_input("Client Secret", type="password")
        spotify_redirect_uri = st.text_input(
            "Redirect URI", value=DEFAULT_CONFIG["SPOTIFY_REDIRECT_URI"]
        )
        spotify_scope = st.text_input(
            "Requested scopes",
            value=DEFAULT_CONFIG["SPOTIFY_SCOPE"],
            help="Adjust if you need different Spotify permissions.",
        )

        st.subheader("Last.fm (optional)")
        lastfm_api_key = st.text_input("API Key", value="")
        lastfm_shared_secret = st.text_input("Shared Secret", type="password")
        lastfm_username = st.text_input("Default Username", value="")

        st.subheader("Admin Account")
        admin_username = st.text_input("Admin username", value="admin")
        admin_display_name = st.text_input("Admin display name", value="Boro Admin")
        admin_password = st.text_input("Admin password", type="password")
        admin_password_confirm = st.text_input("Confirm admin password", type="password")
        admin_spotify_id = st.text_input("Admin Spotify user ID (optional)")
        admin_lastfm_username = st.text_input("Admin Last.fm username (optional)")

        secret_key = st.text_input("Application secret key", type="password")
        overwrite_env = st.checkbox("Overwrite existing .env", value=False)
        submitted = st.form_submit_button("Initialize application")

    if not submitted:
        return

    required = {
        "Database host": database_host,
        "Database name": database_name,
        "Database user": database_user,
        "Database password": database_password,
        "Secret key": secret_key,
        "Spotify Client ID": spotify_client_id,
        "Spotify Client Secret": spotify_client_secret,
    }
    missing = [label for label, value in required.items() if not value.strip()]
    if missing:
        st.error(f"Missing required settings: {', '.join(missing)}")
        return

    if admin_password != admin_password_confirm:
        st.error("Admin passwords do not match.")
        return

    config = {
        "DATABASE_HOST": database_host.strip(),
        "DATABASE_PORT": str(int(database_port)),
        "DATABASE_NAME": database_name.strip(),
        "DATABASE_USER": database_user.strip(),
        "DATABASE_PASSWORD": database_password.strip(),
        "SECRET_KEY": secret_key.strip(),
        "SPOTIFY_CLIENT_ID": spotify_client_id.strip(),
        "SPOTIFY_CLIENT_SECRET": spotify_client_secret.strip(),
        "SPOTIFY_REDIRECT_URI": spotify_redirect_uri.strip(),
        "SPOTIFY_SCOPE": spotify_scope.strip(),
        "LASTFM_API_KEY": lastfm_api_key.strip(),
        "LASTFM_SHARED_SECRET": lastfm_shared_secret.strip(),
        "LASTFM_USERNAME": lastfm_username.strip(),
        "LOG_LEVEL": DEFAULT_CONFIG["LOG_LEVEL"],
        "ENABLE_SCHEDULER": DEFAULT_CONFIG["ENABLE_SCHEDULER"],
    }

    with st.spinner("Applying configuration…"):
        database_url = build_database_url_from_config(config)
        try:
            write_env_file(config, overwrite=overwrite_env)
        except FileExistsError:
            st.error(".env already exists. Enable overwrite to replace it.")
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to write .env: %s", exc)
            st.error("Unable to write configuration file. Check logs for details.")
            return

        try:
            initialize_database(database_url)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Database initialization failed: %s", exc)
            st.error("Database initialization failed. Verify credentials and try again.")
            return

        password_hash = hash_password(admin_password)
        try:
            create_or_update_admin_user(
                database_url=database_url,
                username=admin_username.strip(),
                display_name=admin_display_name.strip() or admin_username.strip(),
                password_hash=password_hash,
                spotify_user_id=admin_spotify_id.strip() or None,
                lastfm_username=admin_lastfm_username.strip() or None,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to create admin user: %s", exc)
            st.error("Admin user creation failed. Resolve the issue and rerun setup.")
            return

    reset_settings_cache()
    st.success("Initialization complete. Reloading application…")
    st.session_state.setup_unlocked = False
    st.experimental_rerun()


def get_user_from_session() -> Optional[models.User]:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    with session_scope() as session:
        user = session.get(models.User, user_id)
        if user is None:
            st.session_state.pop("user_id", None)
            return None
        session.expunge(user)
        return user


def ensure_valid_token(user: models.User) -> models.User:
    if (
        user.spotify_refresh_token
        and user.spotify_token_expires_at
        and user.spotify_token_expires_at <= datetime.now(timezone.utc)
    ):
        token_info = refresh_access_token(user.spotify_refresh_token)
        access_token = token_info["access_token"]
        refresh_token = token_info.get("refresh_token")
        expires_at = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
        scope = token_info.get("scope", user.spotify_scope or "")
        with session_scope() as session:
            db_user = session.get(models.User, user.id)
            if db_user is None:
                return user
            db_user.spotify_access_token = access_token
            db_user.spotify_token_expires_at = expires_at
            db_user.spotify_scope = scope
            if refresh_token:
                db_user.spotify_refresh_token = refresh_token
            session.flush()
            session.refresh(db_user)
            session.expunge(db_user)
            user = db_user
        st.session_state.spotify_access_token = access_token
    return user


def handle_spotify_callback() -> Optional[models.User]:
    params = st.experimental_get_query_params()
    code_values = params.get("code")
    if not code_values:
        return None
    code = code_values[0]
    state = params.get("state", [None])[0]
    expected_state = st.session_state.get("oauth_state")
    if expected_state and state != expected_state:
        st.error("Authentication mismatch. Please try signing in again.")
        st.experimental_set_query_params()
        return None

    oauth = create_spotify_oauth(state=expected_state)
    with st.spinner("Completing Spotify authentication…"):
        try:
            token_info = oauth.get_access_token(code, as_dict=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Spotify OAuth failed: %s", exc)
            st.error("Spotify authentication failed. Please try again.")
            st.experimental_set_query_params()
            return None

    if not token_info:
        st.error("Spotify authentication failed. No token returned.")
        st.experimental_set_query_params()
        return None

    access_token = token_info["access_token"]
    refresh_token = token_info.get("refresh_token")
    expires_at = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
    scope = token_info.get("scope", oauth.scope or "")

    spotify_service = SpotifyService.from_user_token(access_token)
    profile = spotify_service.current_user()
    spotify_user_id = profile["id"]
    display_name = profile.get("display_name") or spotify_user_id
    email = profile.get("email")

    with session_scope() as session:
        user = crud.upsert_spotify_user(
            session,
            spotify_user_id=spotify_user_id,
            username=spotify_user_id,
            display_name=display_name,
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
        )
        session.expunge(user)

    st.session_state.user_id = user.id
    st.session_state.spotify_access_token = access_token
    st.session_state.oauth_state = secrets.token_urlsafe(16)
    st.experimental_set_query_params()
    return user


def require_authenticated_user() -> Optional[models.User]:
    user = handle_spotify_callback() or get_user_from_session()
    if not user:
        return None
    return ensure_valid_token(user)


def render_auth_sidebar(user: Optional[models.User]) -> None:
    with st.sidebar:
        st.header("Account")
        if user:
            st.success(f"Signed in as {user.display_name or user.username}")
            if st.button("Log out"):
                for key in ("user_id", "spotify_access_token"):
                    st.session_state.pop(key, None)
                st.experimental_set_query_params()
                st.experimental_rerun()
        else:
            oauth = create_spotify_oauth(state=st.session_state.get("oauth_state"))
            auth_url = oauth.get_authorize_url()
            st.write("Sign in with Spotify to manage submissions and playlists.")
            st.link_button("Continue with Spotify", auth_url)


def get_spotify_service_for_user(user: models.User) -> SpotifyService:
    if user.spotify_access_token:
        return SpotifyService.from_user_token(user.spotify_access_token)
    return SpotifyService.from_app_credentials()


def safe_list_playlists(limit: int = 12) -> List[PlaylistRead]:
    try:
        with session_scope() as session:
            playlists = crud.list_playlists(session, limit=limit)
            return [
                PlaylistRead(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    month=item.month,
                    spotify_playlist_id=item.spotify_playlist_id,
                    tracks=[],
                )
                for item in playlists
            ]
    except Exception as exc:
        logger.debug("Unable to load playlists: %s", exc)
        st.info("Connect to the database and run migrations to view playlist history.")
        return []


def render_submission_form(user: models.User) -> None:
    st.header("Submit A Track")
    st.write(
        "Search Spotify, review existing submissions, and queue your track for this month's playlist."
    )

    query = st.text_input("Spotify search", placeholder="Artist, track, or album")
    spotify_service = get_spotify_service_for_user(user)

    if query:
        with st.spinner("Searching Spotify…"):
            results = spotify_service.search_tracks(query)
        if not results:
            st.warning("No tracks found. Try refining your search term.")
        for item in results:
            track_name = item["name"]
            artist_names = ", ".join(artist["name"] for artist in item.get("artists", []))
            album_name = item.get("album", {}).get("name", "Unknown Album")
            st.markdown(f"**{track_name}** — {artist_names} _(Album: {album_name})_")
            st.caption(f"Spotify ID: {item['id']}")
            if st.button(f"Select {item['id']}", key=item["id"]):
                st.success("Submission workflow coming soon.")


def render_playlist_history() -> None:
    st.header("Playlist History")
    playlists = safe_list_playlists(limit=12)
    if not playlists:
        st.info("Playlists will appear here once the database is populated.")
        return

    for playlist in playlists:
        st.subheader(f"{playlist.name} ({playlist.month:%B %Y})")
        if playlist.spotify_playlist_id:
            st.markdown(
                f"[Open in Spotify](https://open.spotify.com/playlist/{playlist.spotify_playlist_id})"
            )
        st.write(playlist.description or "No description provided yet.")


def render_song_lookup() -> None:
    st.header("Song Lookup & History")
    search_term = st.text_input(
        "Search across submissions", placeholder="Enter artist, track, or album"
    )
    if not search_term:
        st.info("Enter a search term to find previous submissions.")
        return

    try:
        with session_scope() as session:
            statement = (
                select(models.Track)
                .where(
                    or_(
                        models.Track.name.ilike(f"%{search_term}%"),
                        models.Track.artist.ilike(f"%{search_term}%"),
                        models.Track.album.ilike(f"%{search_term}%"),
                    )
                )
                .limit(10)
            )
            tracks = session.scalars(statement).unique().all()
            if not tracks:
                st.info("No matches found in prior submissions.")
                return

            for track in tracks:
                st.subheader(f"{track.name} — {track.artist}")
                if track.album:
                    st.caption(f"Album: {track.album}")
                st.markdown(f"Spotify URL: {track.spotify_url or 'Not stored yet'}")
                if not track.submissions:
                    st.write("No submissions recorded for this track yet.")
                    continue
                for submission in track.submissions:
                    submitted = submission.submission_month.strftime("%B %Y")
                    submitter = submission.user.display_name or submission.user.username
                    status = "Locked" if submission.is_locked else "Open"
                    st.write(f"Submitted by **{submitter}** for **{submitted}** ({status})")
                    if submission.notes:
                        st.caption(f"Notes: {submission.notes}")
    except Exception as exc:
        logger.debug("Song lookup failed: %s", exc)
        st.warning("Song lookup requires the database to be configured.")


def main() -> None:
    ensure_session_defaults()

    loading_placeholder = st.empty()
    with loading_placeholder.container():
        st.info("Loading configuration…")
    settings = try_load_settings()
    loading_placeholder.empty()

    if settings is None:
        render_initial_setup()
        return

    user = require_authenticated_user()
    render_auth_sidebar(user)

    if user is None:
        st.title("Boro Boys Monthly Playlist")
        st.info("Sign in with Spotify to access the application features.")
        return

    st.title("Boro Boys Monthly Playlist")
    st.caption("Curate, review, and celebrate community music picks.")

    page = st.sidebar.radio(
        "Navigate",
        options=("Submit", "History", "Lookup"),
        index=0,
    )

    if page == "Submit":
        render_submission_form(user)
    elif page == "History":
        render_playlist_history()
    else:
        render_song_lookup()


if __name__ == "__main__":
    main()
