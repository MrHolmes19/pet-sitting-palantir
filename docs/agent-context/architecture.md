# Architecture

## Chosen Stack

- Scheduler: AWS EventBridge Scheduler
- Runtime: AWS Lambda in `ap-southeast-2`
- Language: Python
- Scraping: `requests` + BeautifulSoup
- Database: Supabase/PostgreSQL
- Alerts: Telegram Bot API

## Why This Stack

AWS EventBridge Scheduler plus Lambda replaces GitHub Actions for production
timekeeping. GitHub Actions scheduled workflows proved too unreliable for
alert-grade 5-minute Auckland checks, while EventBridge Scheduler provides a
managed recurring trigger and Lambda can run the existing Python due-scope
workflow with a small handler.

Supabase provides hosted PostgreSQL with a free tier suitable for early development. PostgreSQL also keeps the data model ready for later analytics.

Telegram is the primary notification channel. Email is not a v1 channel.

The KiwiHouseSitters search page returns server-side rendered HTML. Filtered searches use a form POST to the base search URL after an initial GET, so v1 should use `requests.Session` and BeautifulSoup, not Playwright.

## Runtime Flow

1. EventBridge Scheduler invokes Lambda every 5 minutes.
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
- `lambda_handler`: AWS Lambda entry point for EventBridge scheduled due-scope runs.

## Scheduler And Deployment

Production scheduling should run in AWS `ap-southeast-2`:

- EventBridge Scheduler expression: `rate(5 minutes)`.
- Target: Lambda function.
- Lambda handler: `pet_sitting_palantir.lambda_handler.lambda_handler`.
- Lambda command path: call the existing due-scope workflow equivalent to
  `python -m pet_sitting_palantir --run-due --max-pages all --pretty`.
- Lambda reserved concurrency: 1.
- Lambda timeout: initially 5 to 10 minutes.
- CloudWatch log retention: 30 days.

GitHub Actions should be used for CI and deployment only. A push to `main` can
run tests, build a Lambda zip package, and update the Lambda function. Do not
rely on GitHub Actions `schedule` for alert timing.

The production run uses `--max-pages all` so each due scope follows pagination
until the site has no next page. Secrets must not be printed to workflow or
CloudWatch logs.

## Expected Runtime Secrets

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Prefer `DATABASE_URL` for the AWS Lambda production path. Use
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` only if a future implementation
switches to the Supabase API client.

## Operational Principles

- One scheduled invocation path, many database-configured scopes.
- Store enough raw text to debug parsers, but do not overbuild snapshots in v1.
- Treat parser failures as data quality risks, not as empty market signals.
- Keep site load modest by using staggered scopes.
- Add fixtures before making parser behavior broad or fragile.
