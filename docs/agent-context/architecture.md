# Architecture

## Chosen Stack

- Scheduler: local operating-system scheduler on an always-on home machine, to be implemented
- Runtime: Python process on a home machine using its residential connection
- Language: Python
- Scraping: `requests` + BeautifulSoup
- Database: Supabase/PostgreSQL
- Alerts: Telegram Bot API

## Why This Stack

GitHub Actions scheduled workflows proved too unreliable for alert-grade
5-minute Auckland checks. AWS EventBridge Scheduler plus Lambda was then
prepared as the replacement, but KiwiHouseSitters blocked requests from the AWS
cloud IP range used by Lambda. The current direction is to run the same Python
due-scope workflow on already-owned home hardware over a residential network.

Supabase provides hosted PostgreSQL with a free tier suitable for early development. PostgreSQL also keeps the data model ready for later analytics.

Telegram is the primary notification channel. Email is not a v1 channel.

The KiwiHouseSitters search page returns server-side rendered HTML. Filtered searches use a form POST to the base search URL after an initial GET, so v1 should use `requests.Session` and BeautifulSoup, not Playwright.

## Runtime Flow

1. A future local scheduler invokes the due-scope workflow every 5 minutes.
2. The application returns `quiet_hours` without scraping between `00:00` and
   `06:00` in `Pacific/Auckland`.
3. During active hours, Python reads enabled `scrape_scopes`.
4. For each scope, the script checks whether `now - last_success_at >= interval_minutes`.
5. For each due scope, create a `scrape_runs` row with `status = running`.
6. Build the initial KiwiHouseSitters search request from `site_filter`.
7. Fetch and parse all paginated search result pages.
8. Normalize listing data.
9. Upsert listings.
10. Track new and meaningfully changed listings as alert candidates.
11. Mark missing listings only if the scrape succeeded.
12. Apply enabled alert filters.
13. Send Telegram notifications when needed.
14. Close the scrape run and update scope timestamps.

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
- `lambda_handler`: retained entry point from the abandoned AWS deployment path.

## Scheduler And Deployment

The next deployment task is a single safe activation command for an always-on
home machine. It should execute the existing due-scope workflow with full
pagination, prevent overlapping runs, load protected production configuration,
and provide concise local logs.

The application already enforces overnight quiet hours; a future OS schedule may
also avoid overnight invocations to reduce useless process startup.

Keep GitHub Actions for CI if needed, but do not rely on its scheduled workflows
for alert timing. Keep the existing Lambda code only as a record of the previous
attempt unless cloud-IP access becomes viable.

## Expected Runtime Secrets

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN` once alert delivery is implemented
- `TELEGRAM_CHAT_ID` once alert delivery is implemented

Prefer `DATABASE_URL` for the home-runner path. Use `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` only if a future implementation switches to the
Supabase API client.

## Operational Principles

- One scheduled invocation path, many database-configured scopes.
- Pause all due-scope scraping overnight in New Zealand time.
- Prevent overlapping home-hosted executions when the activation command is added.
- Store enough raw text to debug parsers, but do not overbuild snapshots in v1.
- Treat parser failures as data quality risks, not as empty market signals.
- Keep site load modest by using staggered scopes.
- Add fixtures before making parser behavior broad or fragile.
