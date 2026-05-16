# Implementation Roadmap

## Phase 1 - Local Scraper

Goal: a pure Python scraper that receives a `site_filter` and returns normalized listing data.

Deliverable:

```python
scrape_scope(site_filter) -> list[ListingDTO]
```

No Supabase. No Telegram. No GitHub Actions.

## Phase 2 - Pagination And Scopes

Goal: support all planned scopes and pagination.

Deliverables:

- `build_search_request(site_filter)`
- site-filter slug to KiwiHouseSitters POST form conversion
- `fetch_all_pages(initial_url)`
- `parse_listing_card(card)`
- Fixture-backed parser tests if sample HTML is available.

Initial scopes:

- `auckland_central`
- `north_shore_city`
- `auckland_region`
- `north_island`
- `all_nz`

## Phase 3 - Database Schema

Goal: create Supabase/PostgreSQL schema.

Deliverables:

- SQL migrations for:
  - `scrape_scopes`
  - `scrape_runs`
  - `listings`
  - `alert_filters`
  - `sent_alerts`
- Seed data for initial scrape scopes.
- Basic indexes.

## Phase 4 - Upsert And Lifecycle

Goal: persist listings and track lifecycle.

Deliverables:

- `scrape_and_store_scope(scope_name)`
- New listing detection.
- Meaningful changed listing detection via `content_hash`.
- Silent volatile updates such as site-provided `starts_soon`.
- Missing logic using `scope.missing_threshold_runs`.
- Suspicious zero-result run handling that avoids missing inference.
- Expiration handling for `expired_by_date`.
- Due-scope runner using `last_success_at` and `interval_minutes`.
- Baseline tagging for listings found during a scope's first successful scrape.

## Phase 5 - Telegram Alerts

Goal: notify when listings match personal filters.

Deliverables:

- Local filter matcher.
- Telegram sender.
- `sent_alerts` insert/update logic.
- Duplicate prevention using `content_hash_at_alert`.

## Phase 6 - AWS Scheduled Production Run

Goal: alert-grade scheduled production run without relying on GitHub Actions
cron.

Deliverables:

- Lambda handler that calls the existing due-scope runner.
- Lambda zip packaging for project code and dependencies.
- AWS Lambda function in `ap-southeast-2`.
- EventBridge Scheduler rule in `ap-southeast-2` using `rate(5 minutes)`.
- Lambda reserved concurrency set to 1.
- Lambda 512 MB memory, 5 to 10 minute timeout, and 30-day CloudWatch log
  retention configured.
- Lambda environment variables for `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, and
  `TELEGRAM_CHAT_ID`.
- GitHub Actions deployment workflow that updates Lambda on push to `main`.
- Production run uses `--max-pages all`.
- Clear CloudWatch logs for the due-scope runner.
- Old GitHub Actions `schedule` trigger remains disabled or removed.

Expected secrets:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- AWS deploy credentials or GitHub OIDC role configuration.

## Phase 7 - Hardening

Add after the first working pipeline:

- Technical alert when a scope is suspicious or failed.
- Retry handling for failed Telegram alerts.
- Parser tests with HTML fixtures.
- Better structured logs.
- Optional detail-page scraping only for high-value matches.
