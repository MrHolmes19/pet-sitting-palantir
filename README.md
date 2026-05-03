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
