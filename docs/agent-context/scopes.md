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

`north_island` and `all_nz` remain enabled logical scopes with their existing
names, rows, and run history. A new campaign first tries the original complete
scope filter. The scraper may still split capped results internally, as it did
before. If that parent-sized attempt hits an AWS WAF challenge or exhausts its
background time budget, the campaign permanently converts that attempt into
persisted region leaves. An All New Zealand fallback has 15 region leaves; a
North Island fallback has 10. If the same scope has recorded a WAF challenge in
the previous 30 days, a new campaign starts in regional fallback mode instead
of repeating the known-risk parent strategy.

Leaf results are staged in `broad_scrape_campaign_leaves`. They do not create a
parent `scrape_run`, advance the parent scope, mark listings missing, or create
alerts. After every leaf succeeds, the staged results are deduplicated and
atomically persisted as one run under the original `all_nz` or `north_island`
scope. Only one region leaf runs per eligible tick, with a random 4-9 minute
delay before the next leaf. A restart resumes the active campaign from its
first pending leaf.

## Due Check

For every enabled scope:

```text
run_due = last_success_at is null
          or now - last_success_at >= interval_minutes

run_ready = run_due
            and no newer failed direct attempt is still in its retry cooldown
```

Use `last_success_at`, not `last_attempt_at`, so failed runs do not falsely
advance freshness. `last_success_at` means the scope was freshly covered by a
successful complete scrape. Ordinary successful priority scopes can advance
covered narrower priority scopes. Broad campaign completion advances only its
own logical parent, so `all_nz` and `north_island` retain independent schedules
and neither can make an Auckland scope appear fresh. `last_attempt_at` records
only direct requests for that scope and prevents an overdue failed scope from
retrying more often than its failure cooldown. The ordinary cooldown equals the
scope interval, capped at 60 minutes.

AWS WAF challenges have stronger persisted protection for background work. The
golden Auckland phase is never paused by a broad challenge; broad work rests
for at least 24 hours. If an Auckland scope itself receives a WAF challenge,
only that exact scope rests for 15 minutes so repeated requests do not reinforce
an IP-level block. Other Auckland scopes remain eligible. Repeated challenges
in the same broad campaign double its pause up to seven days. The failed region
stays pending and completed regions remain staged, so restarts cannot erase
progress or cooldown state.

The implementation allows a small scheduler grace window before the exact
interval boundary. External schedulers do not start on exact seconds, and without
grace a fast 5-minute scope can miss a whole external scheduler tick because the
previous successful run finished a few seconds after the previous tick.

## Overlapping Scope Selection

The home runner has two separate phases. It first runs the broadest due Auckland
priority scope, processes queued alert deliveries, and only then considers one
background campaign step. Broad selection and cooldown never suppress an
Auckland scope.

Examples:

- If `auckland_region` is due, skip `auckland_central` and `north_shore_city`
  in the priority phase because the complete Auckland Region scrape covers
  them.
- Background work runs only after that priority phase and only when enough time
  remains before the next five-minute tick. Its HTTP client stops at the
  deadline while preserving a one-minute safety margin for the next Auckland
  scan.
- Only one broad campaign may be active. If both broad scopes are due, start
  `all_nz`; after it completes, `north_island` remains due for its own complete
  logical run.

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
- Regional broad fallback may mark only non-Auckland listings in its completed
  region missing.

The implementation needs a deterministic function for checking whether a listing
is covered by a scope's `site_filter`.

Never mark listings missing from a scope's first successful baseline run. First
runs establish observation state; they are not evidence that previously inserted
overlapping listings disappeared.

Never mark listings missing from incomplete or capped searches.

Broad campaign safety is stricter than ordinary scope coverage. A direct parent
attempt does not infer missing listings because it has no independently staged
region boundaries. Regional fallback partitions missing authority so
overlapping campaigns cannot increment one shared listing twice: `all_nz` owns
South Island evidence, while `north_island` owns non-Auckland North Island
evidence. Auckland missing decisions belong only to the golden scopes. Evidence
is applied at the time each region completed, and a listing observed by a faster
scope afterward cannot be overwritten or marked missing by the eventual merge.
