# Scheduling

## Current Direction

Run the production scraper from an always-on home machine over its residential
network connection. This is the current intended runtime because it is free with
already-owned hardware and is less likely to be rejected by KiwiHouseSitters
than a cloud data-centre IP address.

The unattended home-runner command is:

```bash
scripts/run-production.sh
```

It is a foreground process: leave it running on the home machine and use
`Ctrl+C` for an intentional stop. It can be started again later without
manually repairing schedule state.

On startup, `scripts/run-production.sh` applies pending database migrations
before launching the runner. This keeps schema updates aligned with newly
deployed home-runner code; a failed migration must stop startup before scraping.

## Why The Cloud Path Was Dropped

GitHub Actions cron was tested first, but scheduled executions were not reliable
enough for 5-minute Auckland alerting.

AWS EventBridge Scheduler plus AWS Lambda was the next intended production
runtime, and the repository retains a Lambda handler and packaging artifact.
When attempted, KiwiHouseSitters blocked requests from the AWS IP range used by
Lambda. Therefore AWS is no longer the active deployment path unless the site
access constraint changes.

The retained Lambda code is harmless historical/fallback material; do not spend
time completing Lambda deployment instructions for the current plan.

## Scheduling Contract

- Use one generic due-scope invocation; keep each scope's cadence in PostgreSQL
  through `scrape_scopes.interval_minutes` and `last_success_at`.
- The home runner invokes the due-scope workflow immediately on startup and on
  subsequent 5-minute clock boundaries.
- The home runner attempts one daily health check through the configured
  notification layer from 10:00 inclusive to 10:05 exclusive in
  `Pacific/Auckland`. The compact message summarizes successful scrape runs by
  executed scope over the previous 24 hours, new and changed listings, failed
  runs over the same window. A runner started after that window does not send a
  catch-up health check for that day.
- The scheduled/public `run_due_scrape_scopes` application entry point enforces
  quiet hours from `00:00` inclusive to `06:00` exclusive in
  `Pacific/Auckland`.
- During quiet hours, that entry point returns `status = "quiet_hours"` and does
  not connect to PostgreSQL or scrape KiwiHouseSitters.
- The home runner processes pending notification deliveries after the scrape
  phase of every tick, independently of scrape quiet hours. Delivery respects
  each event's filter-derived `deliver_after` timestamp.
- An external schedule may also omit overnight executions, but it must not be
  the only quiet-hours protection.
- The home runner holds a single-instance lock and refuses a second concurrent
  runner.
- Monitor broad-scope runtime; if it grows beyond a five-minute tick, budget
  broad catch-up work so it cannot delay short-cadence Auckland scopes.
- Keep code-owned operational values centralized in
  `src/pet_sitting_palantir/settings.py`; keep scope cadences in PostgreSQL.

The home runner invokes the workflow with full pagination:

```bash
python -m pet_sitting_palantir --run-continuously --max-pages all
```

## Restart And Failure Recovery

- PostgreSQL is the scheduling source of truth. Each tick re-reads enabled
  scopes and decides what is due from `last_success_at`.
- A successful scrape advances `last_success_at` for the directly scraped scope
  and for enabled narrower scopes covered by the same complete result.
  `last_attempt_at` changes only for the scope that issued requests. This
  prevents a successful `all_nz` or regional baseline from immediately causing
  redundant narrower baseline scrapes.
- Restarting the home runner does not reset intervals or postpone work that was
  due while the machine was offline.
- If overlapping scopes became due during downtime, the existing broadest-scope
  selection runs the broader due scope for that tick. For example, if Auckland
  Central and Auckland Region are both overdue, Auckland Region covers the
  Central catch-up work.
- A scope that is not due remains anchored to its last successful run. For
  example, an island-level 12-hour scope does not become due just because the
  runner restarted after a shorter outage.
- Network or database connectivity failures are logged at `ERROR` level and the
  process keeps running; the next 5-minute tick attempts recovery.
- Every tick logs start and completion at `INFO` level, including ticks that
  perform no scrape because nothing is due or quiet hours apply. If a start log
  appears without completion, investigate a blocked database or scrape request.
- If the daily health check does not arrive by 10:05 New Zealand time,
  investigate whether the home machine is powered on, connected, and still
  running `scripts/run-production.sh`.
- Scope scrape failures do not update `last_success_at`, so they remain eligible
  for later retry.
- A matching event due immediately is sent after its scrape transaction commits
  and before the runner sleeps for the next tick. Telegram failure does not
  fail the scrape; it records a failed delivery attempt and retries later.

## Runtime Configuration

The home runtime will need:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Keep production secrets in a gitignored production environment file or another
protected local environment mechanism. Existing `*-local.sh` development scripts
deliberately target local Docker PostgreSQL and must not be used as an unattended
production runner.

For the initial private-chat Telegram destination, create a bot through
`@BotFather`, send a message to the bot from the destination account, retrieve
that chat's id from the Bot API `getUpdates` response, and add the token and
chat id only to `.env.production`.

Code-owned operational values such as request pacing (`0.5` seconds), the
five-minute tick, quiet hours, and PostgreSQL connection failure limits live in
`src/pet_sitting_palantir/settings.py`.

## Operational Priorities

- Preserve the 5-minute Auckland alert goal during active hours.
- Keep logs concise and free of HTML dumps, database URLs, or Telegram tokens.
- Keep the machine awake, connected, and using New Zealand local time semantics.
