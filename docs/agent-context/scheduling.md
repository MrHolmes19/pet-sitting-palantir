# Scheduling

## Current Direction

Run the production scraper from an always-on home machine over its residential
network connection. This is the current intended runtime because it is free with
already-owned hardware and is less likely to be rejected by KiwiHouseSitters
than a cloud data-centre IP address.

The unattended home-runner command and operating-system schedule are not
implemented yet. Do not treat local production scheduling as deployed until that
command and its verification are added.

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
- During active hours, the future local scheduler should invoke the due-scope
  workflow every 5 minutes.
- The scheduled/public `run_due_scrape_scopes` application entry point enforces
  quiet hours from `00:00` inclusive to `06:00` exclusive in
  `Pacific/Auckland`.
- During quiet hours, that entry point returns `status = "quiet_hours"` and does
  not connect to PostgreSQL or scrape KiwiHouseSitters.
- An external schedule may also omit overnight executions, but it must not be
  the only quiet-hours protection.
- The future home runner must prevent overlapping executions, since a local
  scheduler does not provide Lambda's former concurrency limit.

The workflow invoked during active hours remains conceptually:

```bash
python -m pet_sitting_palantir --run-due --max-pages all --pretty
```

Do not configure this manually as the permanent production command yet; a
dedicated safe activation command is intentionally still to be implemented.

## Runtime Configuration

The home runtime will need:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN` once Telegram notifications are implemented
- `TELEGRAM_CHAT_ID` once Telegram notifications are implemented

Keep production secrets in a gitignored production environment file or another
protected local environment mechanism. Existing `*-local.sh` development scripts
deliberately target local Docker PostgreSQL and must not be used as an unattended
production runner.

## Operational Priorities

- Preserve the 5-minute Auckland alert goal during active hours.
- Keep logs concise and free of HTML dumps, database URLs, or Telegram tokens.
- Keep the machine awake, connected, and using New Zealand local time semantics.
- Add production startup, locking, and log-handling instructions alongside the
  future home-runner command.
