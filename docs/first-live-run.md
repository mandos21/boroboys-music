# First live-run checklist

Complete this runbook once against the deployment that will host Music Rounds.
It is the final acceptance exercise for a small private test group, not a
substitute for the automated local checks.

## 1. Configure the deployment

Set deployment-managed environment variables; do not place any of these secrets
in Git or in the built frontend.

```text
APP_ENV=production
APP_BASE_URL=https://boromusic.dege.app
DATABASE_URL=postgresql+psycopg://…
PROCRASTINATE_DATABASE_URL=postgresql://…
SESSION_SECRET=<long random value>
CREDENTIAL_ENCRYPTION_KEY=<Fernet key>
CREDENTIAL_ENCRYPTION_KEY_VERSION=v1

OIDC_ISSUER_URL=https://id.dege.app/realms/<realm>
OIDC_CLIENT_ID=music-rounds
OIDC_CLIENT_SECRET=<deployment secret>
OIDC_REDIRECT_URI=https://boromusic.dege.app/api/v1/auth/callback
OIDC_POST_LOGOUT_REDIRECT_URL=https://boromusic.dege.app/signed-out

SPOTIFY_CLIENT_ID=<deployment secret>
SPOTIFY_CLIENT_SECRET=<deployment secret>
SPOTIFY_REDIRECT_URI=https://boromusic.dege.app/api/v1/connections/spotify/callback

LASTFM_API_KEY=<deployment secret>
LASTFM_SHARED_SECRET=<deployment secret>
LASTFM_CALLBACK_URL=https://boromusic.dege.app/api/v1/connections/lastfm/callback
```

The Keycloak client needs standard authorization-code flow, the OIDC redirect URI
above, `https://boromusic.dege.app/signed-out` as a post-logout redirect, and
`https://boromusic.dege.app` as a web origin. `openid profile email` is sufficient.
No Keycloak group or role mapping is required: with an empty application database,
the first successfully provisioned OIDC identity receives platform-admin access.

Start the API and Procrastinate worker independently. Apply Alembic migrations and
the Procrastinate schema before either begins serving work. Confirm both
`/api/v1/health` and `/api/v1/health/worker`; the latter becomes healthy after the
worker's first heartbeat.

## 2. Verify identity and account links

1. Open the deployed site in a private browser window and sign in through OIDC.
   Confirm the first account can open **Manage series**.
2. Sign out, confirm the configured signed-out page returns, and sign in again.
3. Link a Spotify account and a Last.fm account from **Connections**. Confirm that
   neither provider token appears in browser storage, API responses, or logs.
4. Sign in as at least one further test contributor and link Last.fm for that
   account as well. Choose the desired evidence visibility on each linked account.

## 3. Exercise overlapping round behavior

1. Create two contributor groups with at least one person in both.
2. Create two simultaneously open rounds with different per-round defaults and a
   per-member limit override. Include duplicate and recent-series policies on at
   least one round.
3. Submit a track from the shared contributor. Verify the policy explanation,
   warning confirmation, replacement, note edit, and withdrawal paths.
4. Select a track whose Last.fm history is known. Confirm the evidence matrix is
   shown or marked refreshing, then refresh after the worker completes. A stale
   positive entry is expected to remain visible if the provider is unavailable.
5. Confirm the contributor cannot open an unrelated private round directly.

## 4. Exercise publication and reversal

1. Close a test round, select a linked Spotify publisher in its administration
   page, and publish it.
2. Confirm worker progress, playlist creation, order, attribution snapshot, and
   audit history. Trigger a recoverable failure only in a disposable test playlist
   if retry behavior needs manual confirmation; retry must reuse the existing
   playlist rather than duplicate it.
3. Unpublish the most recent published round. Confirm it returns to `closed` and
   the remote playlist is retired as far as Spotify permits. Confirm an older
   published round cannot be unpublished.
4. For a series with an enabled rolling or calendar plan, publish a second test
   round and confirm that exactly one valid successor is created with the member
   snapshot and configured timeline.

## 5. Record operational evidence

1. Take a compressed PostgreSQL backup and restore it into a disposable database
   following [operations.md](operations.md). Record the migration revision and
   credential-key version with the backup.
2. Save the request ID from one browser response and locate its corresponding
   redacted server log entry.
3. Record the date, deployed commit, test participants, and any provider behavior
   observed. Do not record provider credentials or authorization codes.

Only after this checklist succeeds should the deployment be used for a non-test
round.
