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
  - `alert_events`
  - `alert_delivery_attempts`
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
- Appearance sequencing and prior-status reporting for confirmed
  reappearance detection.

## Phase 5 - Telegram Alerts

Goal: notify when listings match personal filters.

Completed:

- Editable `config/alert_filters.json` filter and delivery configuration.
- Local filter matcher.
- Channel-neutral alert event and delivery tracking.
- Telegram sender behind a notification-provider interface.
- Duplicate prevention using an alert-relevant fingerprint limited to
  location, dates/duration, and animal fields.
- Due-event delivery workflow with retryable failed attempts and a manual
  delivery command.
- Plain-text listing notification formatter.

## Phase 6 - Home-Hosted Scheduled Production Run

Goal: alert-grade scheduled production run from an always-on home machine.

Completed:

- Application-enforced quiet hours for ongoing production due-scope runs.
- One safe restartable home-runner command with full pagination, single-instance
  locking, and retry-on-next-tick failure handling.
- Protected loading of `DATABASE_URL` from the production environment file.
- Concise local operational logs.
- Extended production environment example configuration with Telegram
  credentials.

## Phase 7 - Hardening

Add after the first working pipeline:

- Technical alert when a scope is suspicious or failed.
- Parser tests with HTML fixtures.
- Better structured logs.
- Optional detail-page scraping only for high-value matches.
