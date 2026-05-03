create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

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
  updated_at timestamptz not null default now(),

  constraint scrape_scopes_interval_minutes_positive check (interval_minutes > 0),
  constraint scrape_scopes_missing_threshold_runs_positive check (missing_threshold_runs > 0)
);

create trigger scrape_scopes_set_updated_at
before update on scrape_scopes
for each row
execute function set_updated_at();

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

  error_message text,

  constraint scrape_runs_status_check check (
    status in ('running', 'success', 'partial_failure', 'failed', 'suspicious')
  ),
  constraint scrape_runs_pages_fetched_non_negative check (pages_fetched >= 0),
  constraint scrape_runs_listings_seen_non_negative check (listings_seen >= 0),
  constraint scrape_runs_new_listings_non_negative check (new_listings >= 0),
  constraint scrape_runs_changed_listings_non_negative check (changed_listings >= 0),
  constraint scrape_runs_missing_marked_non_negative check (missing_marked >= 0),
  constraint scrape_runs_alerts_sent_non_negative check (alerts_sent >= 0)
);

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

  status text not null default 'active',
  missing_count int not null default 0,
  missing_since timestamptz,
  closed_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint listings_island_check check (
    island is null or island in ('North Island', 'South Island')
  ),
  constraint listings_duration_days_non_negative check (
    duration_days is null or duration_days >= 0
  ),
  constraint listings_date_order_check check (
    start_date is null or end_date is null or end_date >= start_date
  ),
  constraint listings_total_animals_non_negative check (total_animals >= 0),
  constraint listings_dogs_count_non_negative check (dogs_count >= 0),
  constraint listings_cats_count_non_negative check (cats_count >= 0),
  constraint listings_fish_count_non_negative check (fish_count >= 0),
  constraint listings_birds_count_non_negative check (birds_count >= 0),
  constraint listings_rabbits_guinea_pigs_count_non_negative check (
    rabbits_guinea_pigs_count >= 0
  ),
  constraint listings_chickens_ducks_geese_count_non_negative check (
    chickens_ducks_geese_count >= 0
  ),
  constraint listings_farm_animals_count_non_negative check (farm_animals_count >= 0),
  constraint listings_horses_count_non_negative check (horses_count >= 0),
  constraint listings_reptiles_count_non_negative check (reptiles_count >= 0),
  constraint listings_other_pets_count_non_negative check (other_pets_count >= 0),
  constraint listings_reply_rating_score_range check (
    reply_rating_score is null or reply_rating_score between 0 and 10
  ),
  constraint listings_status_check check (
    status in ('active', 'missing_once', 'missing_confirmed', 'expired_by_date')
  ),
  constraint listings_missing_count_non_negative check (missing_count >= 0)
);

create trigger listings_set_updated_at
before update on listings
for each row
execute function set_updated_at();

create table alert_filters (
  id bigserial primary key,
  name text not null,
  enabled boolean not null default true,

  site_filter jsonb not null default '{}'::jsonb,
  local_filter jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger alert_filters_set_updated_at
before update on alert_filters
for each row
execute function set_updated_at();

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

  constraint sent_alerts_unique_listing_filter_channel_hash unique (
    listing_id,
    filter_id,
    channel,
    content_hash_at_alert
  ),
  constraint sent_alerts_status_check check (status in ('sent', 'failed')),
  constraint sent_alerts_attempt_count_positive check (attempt_count > 0)
);

create index scrape_scopes_enabled_due_idx
  on scrape_scopes (enabled, last_success_at);

create index scrape_runs_scope_started_idx
  on scrape_runs (scope_name, started_at desc);

create index scrape_runs_status_started_idx
  on scrape_runs (status, started_at desc);

create index listings_status_last_seen_idx
  on listings (status, last_seen_at);

create index listings_location_idx
  on listings (island, region, subregion, city);

create index listings_start_date_idx
  on listings (start_date);

create index listings_end_date_idx
  on listings (end_date);

create index sent_alerts_filter_sent_idx
  on sent_alerts (filter_id, sent_at desc);

create index sent_alerts_status_sent_idx
  on sent_alerts (status, sent_at desc);
