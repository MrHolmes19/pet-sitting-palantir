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
candidate_for_alert = true
```

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

If the first page succeeds but a later page fails:

```text
scrape_run.status = partial_failure
do not mark missing
keep successfully parsed listings if implementation can do so safely
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
scrape_scopes.last_success_at = now
scrape_scopes.last_attempt_at = now
```

On failure:

```text
scrape_run.status = failed or partial_failure or suspicious
scrape_scopes.last_attempt_at = now
do not update last_success_at
```

## Safety Defaults

- Empty scrape result is not proof that all listings disappeared.
- Failed pages are not proof that later listings disappeared.
- Broad scopes can mark broad missing state; narrow scopes can only mark listings within their area.
- Prefer fewer false closures over aggressive missing detection.
