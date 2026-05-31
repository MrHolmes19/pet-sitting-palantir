# Database Backups

Production data is treated as sacred. Backup automation may read from
production, but restore automation must target local PostgreSQL unless a future
task explicitly adds a guarded production restore path.

## Commands

Create a logical backup package from production:

```bash
scripts/backup-production.sh
```

The command reads `DATABASE_URL` from `.env.production` and writes a timestamped
directory under `.backups/`:

```text
.backups/2026-05-31T120000Z/
  schema.sql
  data.sql
  manifest.json
```

Restore a backup package into local Docker PostgreSQL:

```bash
scripts/restore-local-backup.sh .backups/2026-05-31T120000Z
```

This command is destructive only for the local Docker database. It does not load
production credentials and does not connect to production.

Restore a backup package into production only after proving the same backup
locally and stopping `scripts/run-production.sh`:

```bash
scripts/restore-prod-backup.sh .backups/2026-05-31T120000Z
```

This command is destructive for production. It loads `.env.production`, requires
multiple typed confirmations, and runs schema plus data as a single PostgreSQL
transaction so failures roll back instead of leaving a partial restore.

## Backup Format

Backups use PostgreSQL logical dumps, not CSV. CSV is useful for analysis
exports, but it is not a reliable restore format for the application database
because table order, foreign keys, sequences, JSONB values, defaults, triggers,
and indexes matter.

`scripts/backup-production.sh` first creates one custom-format `pg_dump`
archive from the production `public` schema, then derives `schema.sql` and
`data.sql` from that same archive. This keeps schema and data from the same
transaction-consistent snapshot while leaving human-readable SQL restore files.

Production Supabase currently runs PostgreSQL 17. If local `pg_dump` and
`pg_restore` are older than PostgreSQL 17, the backup script uses the
`postgres:17-alpine` Docker image for matching client tools.

The production dump runs with `default_transaction_read_only=on` and excludes
ownership and privilege statements.

Data restore disables trigger-based foreign-key checks during the local load.
`pg_restore` can emit table data in an order that is valid as a complete
snapshot but not valid row-by-row for existing foreign keys. This is acceptable
for the local restore path because the data comes from one transaction-consistent
production dump, and the local restore user is the Docker Postgres superuser.

Local Docker PostgreSQL should use the same major version as production. If a
local database volume was created with an older major version and Docker cannot
start Postgres after the image changes, remove the local-only volume before
restoring a backup:

```bash
docker compose down -v
```

## Production Restore

Production restore is a high-risk recovery operation, not a routine workflow.
Before running `scripts/restore-prod-backup.sh`, restore the same backup locally
and inspect the result. Stop the production runner so it does not write during
the restore transaction.
