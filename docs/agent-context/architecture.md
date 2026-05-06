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

The KiwiHouseSitters search page returns server-side rendered HTML. Filtered searches use a form POST to the base search URL after an initial GET, so v1 should use `requests.Session` and BeautifulSoup, not Playwright.

## Runtime Flow

1. GitHub Actions starts every 5 minutes.
2. Python script reads enabled `scrape_scopes`.
3. For each scope, the script checks whether `now - last_success_at >= interval_minutes`.
4. For each due scope, create a `scrape_runs` row with `status = running`.
5. Build the initial KiwiHouseSitters search request from `site_filter`.
6. Fetch and parse all paginated search result pages.
7. Normalize listing data.
8. Upsert listings.
9. Track new and meaningfully changed listings as alert candidates.
10. Mark missing listings only if the scrape succeeded.
11. Apply enabled alert filters.
12. Send Telegram notifications when needed.
13. Close the scrape run and update scope timestamps.

## Component Boundaries

Current module boundaries:

- `config`: environment variables and repo-root `.env` loading.
- `kiwihousesitters.client`: HTTP fetching and pagination.
- `kiwihousesitters.search_filters`: stored site-filter slug to KiwiHouseSitters POST form conversion.
- `kiwihousesitters.parser`: BeautifulSoup parsing and normalization.
- `domain.models`: typed scraped listing objects.
- `storage`: PostgreSQL reads, writes, and storage DTOs.
- `workflows.scrape_and_store`: orchestration for scraping one scope and persisting results.
- `storage.lifecycle`: missing and expiration updates for persisted listings.
- `workflows.run_due_scopes`: orchestration for database scopes whose interval is due.
- `alerts`: local filter matching, Telegram sending, sent alert records.

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

The production workflow uses `--max-pages all` so each due scope follows pagination until the site has no next page. The secret must not be printed to workflow logs.

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
