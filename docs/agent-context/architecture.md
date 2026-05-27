# Architecture

## Chosen Stack

- Scheduler/runtime: restartable home-hosted Python supervisor
- Language: Python
- Scraping: `requests` + BeautifulSoup
- Database: Supabase/PostgreSQL
- Alerts: Telegram Bot API

## Why This Stack

Supabase provides hosted PostgreSQL with a free tier suitable for early development. PostgreSQL also keeps the data model ready for later analytics.

Telegram is the primary notification channel. Email is not a v1 channel.

The KiwiHouseSitters search page returns server-side rendered HTML. Filtered searches use a form POST to the base search URL after an initial GET, so v1 should use `requests.Session` and BeautifulSoup, not Playwright.

Runtime selection and scheduling constraints are documented in
[scheduling.md](scheduling.md).

## Runtime Flow

1. The production trigger invokes the due-scope workflow.
2. Python applies runtime scheduling policy and reads enabled `scrape_scopes`.
3. For each due scope, create a `scrape_runs` row with `status = running`.
4. Build the initial KiwiHouseSitters search request from `site_filter`.
5. Fetch and parse all paginated search result pages.
6. Normalize listing data.
7. Upsert listings.
8. Track new and meaningfully changed listings as alert candidates.
9. Mark missing listings only if the scrape succeeded.
10. Apply enabled alert filters.
11. Persist channel-neutral alert events and close the scrape run.
12. In the delivery phase of the same runner tick, send due Telegram events
    and record provider attempts.

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
- `alerts`: local filter matching, provider-neutral message formatting, and
  provider adapters including Telegram.
- `workflows.deliver_alerts`: persisted due-event delivery and attempt
  recording, independent of scraping.
- `lambda_handler`: retained legacy cloud entry point; not the current runtime plan.

## Scheduler And Deployment

See [scheduling.md](scheduling.md) for the production runtime decision, quiet
hours, rejected hosted approaches, and pending home-runner requirements.

## Expected Runtime Secrets

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Use `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` only if a future
implementation switches to the Supabase API client.

## Operational Principles

- One scheduled invocation path, many database-configured scopes.
- Store enough raw text to debug parsers, but do not overbuild snapshots in v1.
- Treat parser failures as data quality risks, not as empty market signals.
- Keep site load modest by using staggered scopes.
- Add fixtures before making parser behavior broad or fragile.
