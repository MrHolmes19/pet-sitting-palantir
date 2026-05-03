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

```sql
create table listings (
  id bigserial primary key,

  external_id text not null unique,
  url text not null,

  title text,
  listing_tag text,
  intro text,

  city text,
  region text,
  subregion text,

  start_date date,
  end_date date,
  duration_days int,

  pets_raw text,
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

  house_type text,
  starts_soon boolean not null default false,
  reply_rating_score int,
  reply_rating_text text,

  content_hash text,

  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  first_seen_run_id bigint references scrape_runs(id),
  last_seen_run_id bigint references scrape_runs(id),

  status text not null default 'active',
  missing_count int not null default 0,
  missing_since timestamptz,
  closed_at timestamptz,

  raw_data jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Suggested indexes:

```sql
create index listings_status_last_seen_idx
  on listings (status, last_seen_at);

create index listings_region_subregion_idx
  on listings (region, subregion);

create index listings_start_date_idx
  on listings (start_date);
```

Note: `external_id text not null unique` creates a unique index in PostgreSQL, so a separate plain index on `external_id` is not needed.

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
  "name": "Auckland Central good sits",
  "site_filter": {
    "state": "north-island",
    "region": "auckland",
    "subregion": ["auckland-central"]
  },
  "local_filter": {
    "min_duration_days": 7,
    "max_duration_days": 45,
    "max_dogs": 2,
    "allow_cats": true,
    "allow_farm_animals": false,
    "exclude_keywords": ["farm", "own transport required"]
  }
}
```

## `sent_alerts`

Tracks sent notifications and prevents alert spam.

Preferred v1 shape:

```sql
create table sent_alerts (
  id bigserial primary key,

  listing_id bigint not null references listings(id),
  filter_id bigint not null references alert_filters(id),

  sent_at timestamptz not null default now(),
  channel text not null default 'telegram',

  status text not null default 'sent',
  message text,
  error_message text,
  attempt_count int not null default 1,

  content_hash_at_alert text not null,

  unique (listing_id, filter_id, channel, content_hash_at_alert)
);
```

Using `content_hash_at_alert` allows a meaningful listing change, such as changed dates or pet counts, to trigger a new alert. Since `starts_soon` is excluded from `content_hash`, the site-provided `Starts soon` signal should not cause noisy duplicate alerts.

Suggested indexes:

```sql
create index sent_alerts_filter_sent_idx
  on sent_alerts (filter_id, sent_at desc);

create index sent_alerts_status_sent_idx
  on sent_alerts (status, sent_at desc);
```

## `raw_data`

`raw_data` is optional but useful for parser debugging. Keep it lightweight.

Example:

```json
{
  "dates_text": "20 May 2026 - 4 Jun 2026",
  "duration_text": "15 nights",
  "pets_text": "2 Dogs, 1 Cat",
  "reply_rating_alt": "Reply Rating 10"
}
```

Do not store full HTML in `raw_data` for every listing in v1.

## Content Hash

The content hash should represent meaningful listing content:

- `external_id`
- `title`
- `city`
- `region`
- `subregion`
- `start_date`
- `end_date`
- `duration_days`
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
