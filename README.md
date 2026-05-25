# Pet Sitter Intelligence System

Personal automation and intelligence system for finding pet sitting opportunities in New Zealand.

## Goal

- Detect new listings as early as possible.
- Send Telegram alerts for promising sits. The site does this but with certain delay.
- Store a historical database of listings.
- Build future analytics around location, timing, duration, pet mix, lead time, and listing lifecycle.

## Current Direction

Stack:

- Python as scripting language.
- `requests` + BeautifulSoup for scraping.
- Supabase/PostgreSQL for history, scopes, and alert filters.
- Telegram Bot API for notifications.
- An always-on home machine for production scheduling.

The scheduler invokes one due-scope workflow; the Python code decides which
configured scopes need to run.

Initial scope cadence:

| Scope | Frequency |
| --- | ---: |
| Auckland Central | 5 minutes |
| North Shore City | 10 minutes |
| Auckland Region | 60 minutes |
| North Island | 12 hours |
| All New Zealand | 24 hours |

## Future Analytics Questions

Possible future analysis:

- How many listings appear at each time of year?
- How much lead time do homeowners usually provide?
- How does lead time vary by sit duration?
- What is the mix of dogs, cats, mixed pets, and other animals?
- How long do listings remain visible?
- Which areas are hottest for pet sits?
- Was accepting a mediocre sit rational given later market supply?

## Planned Phases

1. Local scraper that returns normalized listing dictionaries.
2. Pagination and search scopes.
3. Supabase schema and migrations.
4. Upsert, lifecycle, and missing-listing handling.
5. Telegram alert filters and sent alert tracking.
6. Home-hosted scheduled runner, quiet hours, locking, and secrets.
7. Hardening with fixtures, retries, technical alerts, and clearer logs.

## Documentation

Agent-facing project context starts at [AGENTS.md](AGENTS.md) and continues in focused files under [docs/agent-context](docs/agent-context).

## Development

This project uses `uv` for Python dependency management and command execution.

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
```

Run the package entry point:

```bash
uv run python -m pet_sitting_palantir
```

Fetch the first KiwiHouseSitters search page and print normalized JSON:

```bash
uv run python -m pet_sitting_palantir --scope all_nz --max-pages 1 --pretty
```

Follow pagination until the site has no next page:

```bash
uv run python -m pet_sitting_palantir --scope all_nz --max-pages all --pretty
```

Print a compact summary instead of every parsed field:

```bash
uv run python -m pet_sitting_palantir --scope all_nz --max-pages 1 --summary --pretty
```

Scrape one database-backed scope and persist normalized listings:

```bash
scripts/persist-local.sh auckland_central 1
```

Run every database-backed scope that is due:

```bash
scripts/run-due-local.sh 1
```

Use `all` to follow pagination until the site has no next page:

```bash
scripts/run-due-local.sh all
```

The `--run-due` workflow used for ongoing production scraping pauses from
midnight through 05:59 New Zealand time.

If `DATABASE_URL` is set in a local `.env` file, you can also run:

```bash
uv run python -m pet_sitting_palantir --run-due --max-pages 1 --pretty
```

If `DATABASE_URL` is set in the environment or in a local `.env` file, you can also run:

```bash
uv run python -m pet_sitting_palantir --scope auckland_central --max-pages 1 --persist --pretty
```

## Database

Schema SQL lives in `supabase/migrations`.

Initial scope seed data lives in `supabase/seed.sql`.

Database record contracts are documented in `docs/contracts`.

Listings first discovered during a scope's first successful scrape are stored
with `first_seen_context = 'baseline'`. They may have existed before this
system started watching, so lifetime analytics should normally use
`first_seen_context = 'observed'`.

Start a local Postgres database with Docker:

```bash
docker compose up -d postgres
```

Initialize the persistent local database:

```bash
scripts/init-local-postgres.sh
```

The app loads `.env` from the current working directory. For local development, copy
the example env file if you want to run the raw Python command without setting
`DATABASE_URL` inline:

```bash
cp .env.example .env
```

The `*-local.sh` scripts always target the local Docker database, even if another
`DATABASE_URL` exists in your shell.

Run database integration tests against that local database:

```bash
scripts/test-local-postgres.sh
```

The script starts Docker Postgres, waits until it is ready, and runs:

```bash
TEST_DATABASE_URL="postgresql://palantir:palantir@localhost:54321/pet_sitting_palantir" \
  uv --cache-dir .uv-cache run pytest \
    tests/test_database_integration.py \
    tests/test_storage_integration.py
```

Stop the local database:

```bash
docker compose down
```

Open `psql`:

```bash
scripts/psql-local.sh
```

Production database access is intentionally separate. Store the Supabase
connection string in a gitignored `.env.production` file:

```bash
cp .env.production.example .env.production
```

Use the interactive production maintenance scripts only when you mean it. They
print a production warning and require a typed confirmation before connecting:

```bash
scripts/init-production-postgres.sh
scripts/psql-production.sh
```

Production scraping is intended to run on an always-on home machine using its
residential network connection. After configuring `.env.production`, start the
restartable production runner with:

```bash
scripts/run-production.sh
```

It runs due scopes immediately and then checks again every 5 minutes. Stop it
with `Ctrl+C`; restarting the same command resumes from successful run
timestamps stored in PostgreSQL. If connectivity temporarily fails, the runner
stays alive and retries on a later tick. The existing `*-local.sh` scripts remain
development helpers that always target local Docker PostgreSQL.

Code-owned runtime values such as scraper request pacing, quiet hours, and the
home-runner tick interval are centralized in
`src/pet_sitting_palantir/settings.py`. Scope cadences remain database-configured.

Useful inspection queries:

```sql
\dt
select * from scrape_scopes order by name;
select * from scrape_runs order by started_at desc;
select external_id, title, region, subregion, status from listings;
```

Run SQL integration tests against a real Postgres database:

```bash
TEST_DATABASE_URL="$DATABASE_URL" uv run pytest tests/test_database_integration.py
```

## Discovery

One-off site discovery scripts live in [discovery](discovery).
