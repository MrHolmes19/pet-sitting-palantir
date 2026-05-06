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

## Phase 6 - GitHub Actions

Goal: scheduled production run.

Deliverables:

- Workflow that runs every 5 minutes.
- Secrets wiring.
- Concurrency configuration.
- Clear logs for the due-scope runner.

Expected secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Phase 7 - Hardening

Add after the first working pipeline:

- Technical alert when a scope is suspicious or failed.
- Retry handling for failed Telegram alerts.
- Parser tests with HTML fixtures.
- Better structured logs.
- Optional detail-page scraping only for high-value matches.
