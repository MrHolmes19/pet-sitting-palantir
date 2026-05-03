# Scheduling And Scopes

## Core Scheduling Decision

Use one GitHub Actions schedule every 5 minutes. Inside the script, decide which scopes are due based on database state.

This avoids hardcoded wall-clock schedules and tolerates:

- GitHub Actions delays.
- Failed runs.
- Long-running runs.
- Frequency changes made directly in the database.

## Initial Scope Cadence

| Scope | Interval | Purpose |
| --- | ---: | --- |
| `auckland_central` | 5 minutes | Fastest alerts for highest-value area. |
| `auckland_region` | 15 minutes | Broader Auckland awareness, including North Shore City as second alert priority. |
| `north_island` | 720 minutes | Wider market context. |
| `all_nz` | 1440 minutes | Full historical baseline. |

## Due Check

For every enabled scope:

```text
run_due = last_success_at is null
          or now - last_success_at >= interval_minutes
```

Use `last_success_at`, not `last_attempt_at`, so failed runs do not falsely advance the schedule.

## Scope Table

`scrape_scopes` should hold runtime scope configuration:

- `name`
- `enabled`
- `interval_minutes`
- `missing_threshold_runs`
- `site_filter`
- `last_attempt_at`
- `last_success_at`

`missing_threshold_runs` is per scope because a fixed threshold has different real-world meanings at different frequencies. For example, 3 missing runs is 15 minutes for Auckland Central but 3 days for All New Zealand.

Suggested initial values:

| Scope | Interval | Missing Threshold | Approx Time Before Confirmed Missing |
| --- | ---: | ---: | ---: |
| `auckland_central` | 5 min | 6 | 30 min |
| `auckland_region` | 15 min | 4 | 60 min |
| `north_island` | 720 min | 3 | 36 hours |
| `all_nz` | 1440 min | 3 | 3 days |

These values are starting points, not product law.

## Example Filters

`auckland_central`:

```json
{
  "state": "north-island",
  "region": "auckland",
  "subregion": "auckland-central"
}
```

`auckland_region`:

```json
{
  "state": "north-island",
  "region": "auckland"
}
```

`north_island`:

```json
{
  "state": "north-island"
}
```

`all_nz`:

```json
{}
```

## Scope Coverage And Missing Logic

A scope may only mark listings missing if those listings belong to that scope.

Examples:

- `auckland_central` may mark only Auckland Central listings missing.
- `auckland_region` may mark Auckland Region listings missing.
- `all_nz` may mark any New Zealand listing missing.

The implementation needs a deterministic function for checking whether a listing is covered by a scope's `site_filter`.

## Concurrency

Use GitHub Actions concurrency:

```yaml
concurrency:
  group: pet-sitter-scraper
  cancel-in-progress: false
```

This prevents overlapping runs from stepping on each other.
