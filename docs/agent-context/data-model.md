# Data Model

This is the intended v1 schema direction. It may be implemented as SQL migrations once code begins.

## `scrape_scopes`

One row per scheduled search scope.

```sql
create table scrape_scopes (
  id bigserial primary key,
  name text not null unique,
  enabled boolean not null default true,

  interval_minutes int not null,
  missing_threshold_runs int not null default 3,
  site_filter jsonb not null default '{}'::jsonb,

  last_attempt_at timestamptz,
  last_success_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Suggested indexes:

```sql
create index scrape_scopes_enabled_due_idx
  on scrape_scopes (enabled, last_success_at);
```

`last_attempt_at` records a direct request for that configured scope.
`last_success_at` records the latest complete successful coverage for the
scope, whether produced directly or by a successful broader containing scope.
Use actual completion timestamps rather than transaction-start timestamps for
scheduling freshness.

## `scrape_runs`

One row per execution of one scope.

```sql
create table scrape_runs (
  id bigserial primary key,

  scope_id bigint references scrape_scopes(id),
  scope_name text not null,

  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',

  search_url text,

  pages_fetched int not null default 0,
  listings_seen int not null default 0,
  new_listings int not null default 0,
  changed_listings int not null default 0,
  missing_marked int not null default 0,
  alerts_sent int not null default 0,

  error_message text
);
```

Status values:

- `running`
- `success`
- `partial_failure`
- `failed`
- `suspicious`

Suggested indexes:

```sql
create index scrape_runs_scope_started_idx
  on scrape_runs (scope_name, started_at desc);

create index scrape_runs_status_started_idx
  on scrape_runs (status, started_at desc);
```

## `listings`

One row per KiwiHouseSitters job.

Persist normalized fields that are useful for alerting, lifecycle, and analytics. Do not persist parser/debug raw text fields in v1:

- Do not persist `raw_data`.
- Do not persist `pets_raw`.
- Do not persist `reply_rating_text`.
- Persist `reply_rating_score`.

Preferred field order for persisted listing data:

1. Identifiers: `id`, `external_id`, `content_hash`.
2. Location: `island`, `region`, `subregion`, `city`.
3. Timing: `duration_days`, `start_date`, `end_date`.
4. Home: `house_type`.
5. Animals: `total_animals`, then individual animal counts.
6. Site signals: `starts_soon`, `reply_rating_score`.
7. Listing text and links: `listing_tag`, `title`, `intro`, `url`.
8. Lifecycle and audit fields.

```sql
create table listings (
  id bigserial primary key,

  external_id text not null unique,
  content_hash text not null,

  island text,
  region text,
  subregion text,
  city text,

  duration_days int,
  start_date date,
  end_date date,

  house_type text,

  total_animals int not null default 0,
  dogs_count int not null default 0,
  cats_count int not null default 0,
  fish_count int not null default 0,
  birds_count int not null default 0,
  rabbits_guinea_pigs_count int not null default 0,
  chickens_ducks_geese_count int not null default 0,
  farm_animals_count int not null default 0,
  horses_count int not null default 0,
  reptiles_count int not null default 0,
  other_pets_count int not null default 0,
  no_pets boolean not null default false,

  starts_soon boolean not null default false,
  reply_rating_score int,

  listing_tag text,
  title text,
  intro text,
  url text not null,

  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  first_seen_run_id bigint references scrape_runs(id),
  last_seen_run_id bigint references scrape_runs(id),
  first_seen_context text not null default 'observed',

  status text not null default 'active',
  missing_count int not null default 0,
  missing_since timestamptz,
  closed_at timestamptz,
  appearance_sequence int not null default 1,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

`first_seen_context` marks whether a listing is safe for listing-lifetime analytics:

- `baseline`: first seen during a scope's first successful scrape. The listing may have been live before this system started observing, so it is left-censored and should be excluded from average listing-time calculations unless handled separately.
- `observed`: first seen after that scope already had a successful baseline observation.

`appearance_sequence` identifies distinct confirmed online appearances of the
same external listing id. It starts at `1` and increments when a listing
previously marked `missing_confirmed` is observed again. It does not increment
after `missing_once`, since that status is not sufficient evidence that the
listing was genuinely offline.

Suggested indexes:

```sql
create index listings_status_last_seen_idx
  on listings (status, last_seen_at);

create index listings_location_idx
  on listings (island, region, subregion, city);

create index listings_start_date_idx
  on listings (start_date);
```

Note: `external_id text not null unique` creates a unique index in PostgreSQL, so a separate plain index on `external_id` is not needed.

## Location Aggregation

`island` is aggregated by this system from the listing `region`. Use one named mapping constant in code, not scattered conditionals.

North Island regions:

- `Auckland`
- `Bay of Plenty`
- `Gisborne`
- `Hawke's Bay`
- `Manawatū-Whanganui`
- `Northland`
- `Taranaki`
- `Waikato`
- `Wairarapa`
- `Wellington`

South Island regions:

- `Canterbury`
- `Nelson / Marlborough`
- `Otago`
- `Southland`
- `West Coast`

If a region is not in the mapping, keep `island` null and preserve the original `region` value.

## Animal Aggregation

`total_animals` is aggregated by this system as:

```text
dogs_count
+ cats_count
+ fish_count
+ birds_count
+ rabbits_guinea_pigs_count
+ chickens_ducks_geese_count
+ farm_animals_count
+ horses_count
+ reptiles_count
+ other_pets_count
```

## `alert_filters`

Personal alert rules. Keep site filters and local filters separate.

```sql
create table alert_filters (
  id bigserial primary key,
  name text not null,
  enabled boolean not null default true,

  site_filter jsonb not null default '{}'::jsonb,
  local_filter jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Example:

```json
{
  "name": "Auckland Central sample rule",
  "site_filter": {
    "state": "north-island",
    "region": "auckland",
    "subregion": "auckland-central"
  },
  "local_filter": {
    "date_window_match": "contained",
    "start_date_on_or_after": "2027-06-01",
    "end_date_on_or_before": "2027-08-31",
    "min_duration_days": 7,
    "max_duration_days": 45,
    "allowed_islands": ["North Island"],
    "allowed_regions": ["Auckland"],
    "allowed_subregions": ["Auckland - Central"],
    "max_total_animals": 3,
    "max_dogs": 2,
    "dogs_allowed": true,
    "cats_allowed": true,
    "fish_allowed": false,
    "birds_allowed": false,
    "rabbits_guinea_pigs_allowed": false,
    "chickens_ducks_geese_allowed": false,
    "farm_animals_allowed": false,
    "horses_allowed": false,
    "reptiles_allowed": false,
    "other_pets_allowed": false,
    "no_pets_allowed": false,
    "min_reply_rating_score": 5,
    "allowed_house_types": ["House", "Unit", "Flat"],
    "excluded_house_types": ["Farm House"],
    "include_keywords": ["wifi"],
    "exclude_keywords": ["rural", "own transport required"]
  }
}
```

Editable filter defaults live in `config/alert_filter_defaults.json`, and named
filter overrides live in `config/alert_filters.json`; a later synchronization
step will populate the table from the merged definitions. The JSON above
illustrates supported fields, not a permanent personal filter.

## `alert_events`

One row represents the channel-independent decision that a listing matches an
alert filter for a particular relevant version of one online appearance.

```sql
create table alert_events (
  id bigserial primary key,

  listing_id bigint not null references listings(id),
  filter_id bigint not null references alert_filters(id),
  detected_run_id bigint not null references scrape_runs(id),

  event_type text not null,
  appearance_sequence int not null,
  alert_fingerprint text not null,
  listing_content_hash text not null,

  target_channels text[] not null,
  deliver_after timestamptz not null default now(),
  created_at timestamptz not null default now(),

  unique (listing_id, filter_id, appearance_sequence, alert_fingerprint)
);
```

`event_type` values:

- `first_match`
- `became_match`
- `material_change`
- `confirmed_reappearance`

`alert_fingerprint` must include only alert-relevant location, date/duration,
and animal data. `listing_content_hash` stores the observed general listing
version for audit, but is not the duplicate key.

`appearance_sequence` allows an external listing id to alert in a later
confirmed reappearance even if its fields return to a version seen in an older
appearance. `target_channels` and `deliver_after` snapshot the delivery plan
when an event is created, so quiet-hour deferral remains deterministic after
filter configuration changes.

## `alert_delivery_attempts`

One row records each outbound call to a notification provider. Failed attempts
remain as history and later retries create additional rows. A partial unique
index permits at most one successful attempt for an event and channel.

```sql
create table alert_delivery_attempts (
  id bigserial primary key,

  alert_event_id bigint not null references alert_events(id),
  channel text not null,

  attempted_at timestamptz not null default now(),
  status text not null,
  message text,
  provider_message_id text,
  error_message text
);

create unique index alert_delivery_attempts_unique_success_idx
  on alert_delivery_attempts (alert_event_id, channel)
  where status = 'sent';
```

## Content Hash

The content hash should represent meaningful listing content:

- `external_id`
- `title`
- `island`
- `city`
- `region`
- `subregion`
- `start_date`
- `end_date`
- `duration_days`
- `total_animals`
- pet counts
- `house_type`
- `reply_rating_score`
- `listing_tag`
- `intro`

Exclude:

- `starts_soon`
- `last_seen_at`
- `missing_count`
- `status`
- any scrape run metadata
