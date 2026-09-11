# Operations runbook

Music Rounds keeps all durable state—including encrypted provider credentials—in
PostgreSQL. Backups are only recoverable when the credential-encryption key is
retained alongside the backup in the deployment secret manager.

## Before deploying

1. Set a production-only `CREDENTIAL_ENCRYPTION_KEY`. Sessions need no signing
   secret: the cookie carries an opaque random token and only its SHA-256 hash
   is stored, so there is nothing to sign.
2. Apply Alembic migrations before starting an updated worker: `make migrate`.
3. Apply the Procrastinate schema when its library version changes:
   `make task-schema`.
4. Start API and worker as separate processes, then check `/api/v1/health` and
   `/api/v1/health/worker`. The worker endpoint becomes healthy after its first
   one-minute heartbeat and reports degraded when the heartbeat is older than two
   minutes.

## Backup and restore drill

Create a compressed logical backup from the production PostgreSQL instance:

```sh
pg_dump --format=custom --no-owner "$POSTGRES_DSN" > music-rounds-$(date +%F).dump
```

`POSTGRES_DSN` is a libpq connection URI (for example,
`postgresql://user:password@host:5432/music_rounds`), not SQLAlchemy's
`postgresql+psycopg://` application URL.

To validate a backup, restore it into an empty disposable database and run the
migration check:

```sh
createdb music_rounds_restore_check
pg_restore --clean --if-exists --no-owner --dbname=music_rounds_restore_check music-rounds-YYYY-MM-DD.dump
DATABASE_URL=postgresql+psycopg://.../music_rounds_restore_check \
PROCRASTINATE_DATABASE_URL=postgresql://.../music_rounds_restore_check \
make migrate task-schema
```

Record the backup date, PostgreSQL version, migration revision, and the key version
that can decrypt credentials. Do not test restoration against the live database.
The restore check should also confirm an expected application row count and the
presence of Procrastinate's queue tables; a successful schema migration alone does
not prove the backup contained the application data.

## Credential-key rotation

Credential records carry a key version. Rotation is a two-stage deploy: add the
new key and a new `CREDENTIAL_ENCRYPTION_KEY_VERSION` to the deployment secret
store, then run the one-off re-encryption command while the previous key is still
available only in an environment variable:

```sh
OLD_CREDENTIAL_ENCRYPTION_KEY="$PREVIOUS_KEY" \
poetry run python -m app.cli.rotate_credentials --from-version=v1
```

The command re-encrypts and version-tags each matching row in one database
transaction. Verify that every credential has the destination version, perform a
verified backup, and only then remove the old key. Never rotate the only key before
the re-encryption step has succeeded.

Only provider credentials are re-encrypted. Browser sessions and in-flight login
attempts also hold ciphertext under the key, but they are short-lived and are not
rotated: a session created before the rotation can still sign out (the stored
ID-token hint is simply dropped from the provider logout redirect), and a login
that straddles the rotation is asked to start again.

## Incident signals

- A growing queue or repeated publication errors requires pausing publication and
  inspecting the durable `publications.last_error` field.
- An unavailable Last.fm refresh must retain cached positive evidence; investigate
  provider rate limits before retrying aggressively.
- A failed OIDC login should expose only a generic browser error; inspect server
  logs without logging tokens, authorization codes, or credential ciphertext.
- Every completed API response includes `X-Request-ID`. Request logs contain that
  ID, method, normalized route label, status, and duration—but deliberately omit
  query strings, cookies, request bodies, and authorization data—so use the ID to
  correlate a user report with server-side diagnostics.
