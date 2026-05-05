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
- GitHub Actions as workflow scheduler.

GitHub Actions will run on a 5 minute schedule, while the Python script decides which scrape scopes are due. This keeps one external scheduler and lets scope frequency live in the database.

Initial scope cadence:

| Scope | Frequency |
| --- | ---: |
| Auckland Central | 5 minutes |
| Auckland Region | 15 minutes |
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
6. GitHub Actions scheduler and secrets.
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

Print a compact summary instead of every parsed field:

```bash
uv run python -m pet_sitting_palantir --scope all_nz --max-pages 1 --summary --pretty
```

Scrape one database-backed scope and persist normalized listings:

```bash
scripts/persist-local.sh auckland_central 1
```

If `DATABASE_URL` is set in the environment or in a local `.env` file, you can also run:

```bash
uv run python -m pet_sitting_palantir --scope auckland_central --max-pages 1 --persist --pretty
```

## Database

Schema SQL lives in `supabase/migrations`.

Initial scope seed data lives in `supabase/seed.sql`.

Database record contracts are documented in `docs/contracts`.

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
