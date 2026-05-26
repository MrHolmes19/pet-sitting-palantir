# Alerts

## Configuration Source

Keep reusable values in `config/alert_filter_defaults.json` and named personal
filter overrides in `config/alert_filters.json`. These are the human-maintained
sources for filters and delivery policy; later alert-table synchronization
should read from them rather than require manual SQL editing.

Telegram is the first delivery channel, but filtering and alert-event decisions
must be channel-independent.

## Filter Model

Each configured alert filter contains:

- `site_filter`: the listing geography covered by the alert, using the same
  readable slugs as scrape scopes.
- `local_filter`: overrides to matching defaults applied to normalized
  listings.
- Optional `delivery`: overrides to the default channels or quiet hours.

Animal permissions are opt-in. Treat an omitted or false `*_allowed` flag as
excluding listings with that animal category. This makes cat-only or similarly
narrow filters straightforward.

The defaults file must list every supported local-filter field with an explicit
value. Use `null` to disable optional limits or allow-lists and empty arrays to
disable keyword or exclusion rules. Local filter rules support year-specific
date windows, `contained` or `overlaps` date-window interpretation, duration
bounds, opt-in animal categories, animal count limits, response rating,
dwelling type, and keyword rules. Keep concrete personal filter values in
configuration files, not in agent-context documentation.

## Scope Evaluation

Alert filters are not attached to scrape scope rows. Evaluate a candidate
listing against every enabled filter after a successful complete scrape,
regardless of whether the listing arrived from the exact filter area or a
broader containing scrape.

For example, a narrow Auckland Central alert filter may match a listing
observed during `auckland_region`, `north_island`, or `all_nz`. Listings
outside that configured geography cannot trigger it.

## Alert Candidates And Repeats

Generate an alert candidate when:

1. A new listing matches an enabled filter, including a matching listing first
   observed as part of a baseline run.
2. A previously notified active listing has an alert-relevant material change:
   location, dates or duration, or animal counts.
3. A listing previously marked `missing_confirmed` reappears, still matches,
   and differs from the last notified alert-relevant version.

Do not alert for display-only changes such as `starts_soon`, title, intro,
listing tag, response rating, or house-type changes. The current general
`content_hash` includes some of those fields, so delivery deduplication must
eventually use a narrower alert-relevant fingerprint rather than
`content_hash` alone. This comparison uses already parsed fields and requires
no detail-page request.

Do not treat `missing_once` followed by another observation as a reappearance;
only `missing_confirmed` is sufficient evidence that a listing went offline.

## Delivery Boundary

Keep alert decisions separate from notification providers:

```text
candidate transition -> filter matcher -> alert event -> delivery attempt
                                          -> Telegram sender
                                          -> future email/WhatsApp sender
```

One semantic alert event may have delivery attempts through multiple channels.
Persist the event before sending so a provider success is not lost if later
database work fails.

`alert_events` deduplicates semantic decisions by listing, filter, confirmed
appearance, and alert-relevant fingerprint. `alert_delivery_attempts` stores
individual provider calls and permits failed retries while enforcing at most
one successful attempt for an event/channel.

## Quiet Hours

Each alert filter owns delivery quiet hours. These may align with the scrape
pause or use a different interval. When delivery is implemented, a qualifying
event during delivery quiet hours must be retained for delivery after the
window instead of discarded.
