# Lifecycle And Safety Rules

## Listing Statuses

Supported statuses:

- `active`
- `missing_once`
- `missing_confirmed`
- `expired_by_date`

## When A Listing Appears

If a listing appears in a successful scrape:

```text
status = active
last_seen_at = now
last_seen_run_id = current run
missing_count = 0
missing_since = null
```

If it is new:

```text
first_seen_at = now
first_seen_run_id = current run
first_seen_context = baseline if this scope has no previous successful run, else observed
candidate_for_alert = true
```

Use `first_seen_context` to keep analytics honest:

- `baseline` listings were discovered during a scope's first successful scrape and may have been live before observation started.
- `observed` listings were discovered after the scope had already established a baseline.

Average listing-lifetime analytics should normally exclude `baseline` rows or treat them as left-censored observations.

If it already exists:

```text
if content_hash changed:
    update meaningful fields
    candidate_for_alert = true
else:
    update volatile fields and last_seen_at
    candidate_for_alert = false
```

Volatile fields include `starts_soon`, which is a site-provided signal rather than our own calculation. It should update silently and should not affect `content_hash`.

## Missing Logic

Only mark missing after a fully successful scope scrape.

Do not mark missing when run status is:

- `failed`
- `partial_failure`
- `suspicious`

For a successful run, compare active or missing listings covered by that scope against the external IDs seen in the run.

If a covered listing was not seen:

```text
missing_count += 1

if missing_count == 1:
    status = missing_once
    missing_since = now

if missing_count >= scope.missing_threshold_runs:
    status = missing_confirmed
    closed_at = now
```

Use `scope.missing_threshold_runs`, not one global value.

## Suspicious Runs

If a scope returns zero listings, treat it as suspicious:

```text
scrape_run.status = suspicious
do not mark any listing missing
optionally send a technical alert
```

Possible causes:

- Parser broke.
- Site changed.
- Site was down.
- Request was blocked.
- Search URL was built incorrectly.

## Partial Failures

If any request or parser step fails before a complete scoped result is collected:

```text
scrape_run.status = failed
do not mark missing
do not persist partial scoped results
```

Partial data should not be used to infer disappearance.

## Expiration By Date

`expired_by_date` is useful for clean analytics and should have explicit logic if the status exists.

Recommended v1 rule:

```text
if end_date is not null and end_date < current_date:
    status = expired_by_date
    closed_at = coalesce(closed_at, now)
```

This can run as part of every scraper invocation or as a separate lightweight cleanup step. Do not apply it before alert matching for new listings unless the listing is clearly stale.

## Run Status Completion

On success:

```text
scrape_run.status = success
direct_scope.last_attempt_at = actual attempt time
direct_scope.last_success_at = actual completion time
covered_enabled_narrower_scopes.last_success_at = actual completion time
```

A complete broader run provides baseline coverage for its contained scopes.
After that coverage timestamp has been established, a narrower run may apply
missing-listing logic because the system has already successfully observed that
area.

On failure:

```text
scrape_run.status = failed or suspicious
direct_scope.last_attempt_at = actual attempt time
do not update last_success_at
```

An orderly process interruption during an active scrape closes that run as
`failed` before the process stops. Abrupt machine or process termination can
still leave a historical `running` row; scheduling recovery remains based on
`last_success_at`.

## Safety Defaults

- Empty scrape result is not proof that all listings disappeared.
- Failed pages are not proof that later listings disappeared.
- Broad scopes can mark broad missing state; narrow scopes can only mark listings within their area.
- Prefer fewer false closures over aggressive missing detection.
