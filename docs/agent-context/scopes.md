# Scopes

## Scope Cadence

The external scheduler should tick every 5 minutes. The app decides which scopes
are due from database state.

Initial scope cadence:

| Scope | Interval | Purpose |
| --- | ---: | --- |
| `auckland_central` | 5 minutes | Fastest alerts for highest-value area. |
| `north_shore_city` | 10 minutes | Dedicated alerts for second-priority Auckland area. |
| `auckland_region` | 60 minutes | Broader Auckland awareness and history collection. |
| `north_island` | 720 minutes | Wider market context. |
| `all_nz` | 1440 minutes | Full historical baseline. |

These are legacy seed scopes. The next scope model should avoid scraping broad
uncapped searches directly. `all_nz` may remain as a logical root if that keeps
scheduling simpler, but runtime execution should expand it into island-level
child searches rather than scraping one unfiltered All New Zealand search.

If maintaining two broad scheduled scopes is no more complex or expensive than
one logical root, prefer explicit `north_island` and `south_island` roots. If the
scheduler mechanism makes one root simpler, keep `all_nz` and expand it at
runtime into `north_island` and `south_island`.

## Due Check

For every enabled scope:

```text
run_due = last_success_at is null
          or now - last_success_at >= interval_minutes
```

Use `last_success_at`, not `last_attempt_at`, so failed runs do not falsely
advance the schedule. `last_success_at` means the scope was freshly covered by
a successful complete scrape: a successful broader scope also advances covered
narrower scopes. `last_attempt_at` records only direct requests for that scope.

The implementation allows a small scheduler grace window before the exact
interval boundary. External schedulers do not start on exact seconds, and without
grace a fast 5-minute scope can miss a whole external scheduler tick because the
previous successful run finished a few seconds after the previous tick.

## Overlapping Scope Selection

When multiple overlapping scopes are due in one invocation, run only the
broadest applicable scope.

Examples:

- If `auckland_region` is due, skip `auckland_central` and `north_shore_city`
  for that invocation because the broader scrape should include them.
- If `all_nz` remains as a logical root, it should expand into island child
  searches and suppress narrower due scopes for that invocation.
- On a fresh database, do not run every seeded overlapping scope just because all
  `last_success_at` values are null. Establish the broad baseline first and
  initialize the covered narrower schedules from that successful observation.

This reduces duplicate site requests, avoids redundant upserts, and prevents
overlapping scopes from making lifecycle decisions from inconsistent partial
views in the same runner invocation.

## Scope Table

`scrape_scopes` should hold runtime scope configuration:

- `name`
- `enabled`
- `interval_minutes`
- `missing_threshold_runs`
- `site_filter`
- `last_attempt_at`
- `last_success_at`

`missing_threshold_runs` is per scope because a fixed threshold has different
real-world meanings at different frequencies. For example, 3 missing runs is 15
minutes for Auckland Central but 3 days for All New Zealand.

Suggested initial values:

| Scope | Interval | Missing Threshold | Approx Time Before Confirmed Missing |
| --- | ---: | ---: | ---: |
| `auckland_central` | 5 min | 6 | 30 min |
| `north_shore_city` | 10 min | 3 | 30 min |
| `auckland_region` | 60 min | 3 | 3 hours |
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

`north_shore_city`:

```json
{
  "state": "north-island",
  "region": "auckland",
  "subregion": "north-shore-city"
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
- `north_shore_city` may mark only North Shore City listings missing.
- `auckland_region` may mark Auckland Region listings missing.
- `all_nz` may mark any New Zealand listing missing.

The implementation needs a deterministic function for checking whether a listing
is covered by a scope's `site_filter`.

Never mark listings missing from a scope's first successful baseline run. First
runs establish observation state; they are not evidence that previously inserted
overlapping listings disappeared.

Never mark listings missing from incomplete or capped searches.
