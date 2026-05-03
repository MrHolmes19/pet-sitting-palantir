# Alerts

## Alert Channel

Telegram is the v1 alert channel.

Email is not planned for v1.

## Alert Candidates

A listing can become an alert candidate when:

1. It is newly discovered.
2. It already exists but its meaningful `content_hash` changed.
3. It did not match before but now matches a filter because meaningful fields changed.

Do not create alert candidates for silent volatile changes such as the site-provided `starts_soon` signal becoming true.

## Filter Model

Alert filters have two parts:

- `site_filter`: mirrors KiwiHouseSitters search constraints.
- `local_filter`: personal matching rules applied after scraping.

Keep these separate. Site filters control what is searched. Local filters control what is worth notifying.

Example local filter fields:

- `min_duration_days`
- `max_duration_days`
- `max_dogs`
- `allow_cats`
- `allow_farm_animals`
- `exclude_keywords`

## Matching Rules

To send an alert:

```text
listing is alert candidate
and listing is covered by alert_filter.site_filter
and listing matches alert_filter.local_filter
and no successful alert exists for listing + filter + channel + content_hash
```

The dedupe key should include `content_hash_at_alert` so meaningful changes can alert again. Since the site-provided `starts_soon` is excluded from the hash, this signal should not cause duplicate alerts.

## Do Not Alert When

- The listing does not match local filters.
- The listing only changed in volatile fields.
- A successful sent alert already exists for the same listing, filter, channel, and content hash.
- The listing came from a broad scope but does not match any enabled alert filter.

## Telegram Message Shape

Keep messages compact and decision-oriented.

Example:

```text
New sit matched: cat-signal in auckland central

Location: Grey Lynn, Auckland
Dates: 12 Jun - 28 Jun
Duration: 16 nights
Dogs: 0
Cats: 1
Home: House

https://www.kiwihousesitters.co.nz/...
```

Emoji can be added later if desired, but plain text is easier to test.

## Telegram Failure Handling

Preferred behavior:

```text
if send succeeds:
    insert sent_alerts status = sent

if send fails:
    insert or update sent_alerts status = failed
    store error_message
    increment attempt_count
    retry in a later run
```

Minimal acceptable v1 behavior:

```text
if send fails:
    log failure
    do not insert a successful sent alert
```

Do not mark a failed Telegram send as successfully sent.
