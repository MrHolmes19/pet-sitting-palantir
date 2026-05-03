# Architecture

## Chosen Stack

- Scheduler: GitHub Actions
- Language: Python
- Scraping: `requests` + BeautifulSoup
- Database: Supabase/PostgreSQL
- Alerts: Telegram Bot API

## Why This Stack

GitHub Actions is enough for a low-cost scheduled personal scraper. Its schedule interval is limited, so the external workflow runs every 5 minutes and the script decides which scopes are due.

Supabase provides hosted PostgreSQL with a free tier suitable for early development. PostgreSQL also keeps the data model ready for later analytics.

Telegram is the primary notification channel. Email is not a v1 channel.

The KiwiHouseSitters search page appears to return server-side rendered HTML in the initial response. v1 should therefore use `requests` and BeautifulSoup, not Playwright.

## Runtime Flow

1. GitHub Actions starts every 5 minutes.
2. Python script reads enabled `scrape_scopes`.
3. For each scope, the script checks whether `now - last_success_at >= interval_minutes`.
4. For each due scope, create a `scrape_runs` row with `status = running`.
5. Build the initial KiwiHouseSitters search URL from `site_filter`.
6. Fetch and parse all paginated search result pages.
7. Normalize listing data.
8. Upsert listings.
9. Track new and meaningfully changed listings as alert candidates.
10. Mark missing listings only if the scrape succeeded.
11. Apply enabled alert filters.
12. Send Telegram notifications when needed.
13. Close the scrape run and update scope timestamps.

## Component Boundaries

Suggested modules once implementation starts:

- `config`: environment variables and constants.
- `kiwihousesitters_client`: HTTP fetching, retry basics, URL building.
- `kiwihousesitters_parser`: BeautifulSoup parsing and normalization.
- `models` or `dto`: typed listing and scope objects.
- `repository`: Supabase/PostgreSQL reads and writes.
- `lifecycle`: upsert, changed detection, missing handling.
- `alerts`: local filter matching, Telegram sending, sent alert records.
- `runner`: orchestration for due scopes.

## GitHub Actions

External schedule:

```yaml
on:
  schedule:
    - cron: "*/5 * * * *"
```

Prevent overlapping runs:

```yaml
concurrency:
  group: pet-sitter-scraper
  cancel-in-progress: false
```

## Expected Secrets

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Prefer `DATABASE_URL` for server-side SQL workflows if direct PostgreSQL access is chosen. Prefer Supabase client credentials if using the Supabase API client.

## Operational Principles

- One scheduled workflow, many database-configured scopes.
- Store enough raw text to debug parsers, but do not overbuild snapshots in v1.
- Treat parser failures as data quality risks, not as empty market signals.
- Keep site load modest by using staggered scopes.
- Add fixtures before making parser behavior broad or fragile.
