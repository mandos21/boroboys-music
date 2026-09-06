# Operations runbook

Music Rounds keeps all durable state—including encrypted provider credentials—in
PostgreSQL. Backups are only recoverable when the credential-encryption key is
retained alongside the backup in the deployment secret manager.

## Before deploying

1. Set production-only `SESSION_SECRET` and `CREDENTIAL_ENCRYPTION_KEY` values.
2. Apply Alembic migrations before starting an updated worker: `make migrate`.
3. Apply the Procrastinate schema when its library version changes:
   `make task-schema`.
4. Start API and worker as separate processes, then check `/api/v1/health`.

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
new key to the deployment secret store, run a one-off re-encryption job, verify that
every credential has the new version, then remove the old key only after a verified
backup. Never rotate the only key before the re-encryption step has succeeded.

## Incident signals

- A growing queue or repeated publication errors requires pausing publication and
  inspecting the durable `publications.last_error` field.
- An unavailable Last.fm refresh must retain cached positive evidence; investigate
  provider rate limits before retrying aggressively.
- A failed OIDC login should expose only a generic browser error; inspect server
  logs without logging tokens, authorization codes, or credential ciphertext.
