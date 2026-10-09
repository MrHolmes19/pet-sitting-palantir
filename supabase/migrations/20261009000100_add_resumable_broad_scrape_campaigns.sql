create table broad_scrape_campaigns (
  id bigserial primary key,
  scope_id bigint not null references scrape_scopes(id),
  scope_name text not null,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  next_attempt_at timestamptz not null default now(),
  waf_challenge_count int not null default 0,
  error_message text,

  constraint broad_scrape_campaigns_status_check check (
    status in ('running', 'paused', 'completed', 'abandoned')
  ),
  constraint broad_scrape_campaigns_waf_challenge_count_non_negative check (
    waf_challenge_count >= 0
  )
);

create trigger broad_scrape_campaigns_set_updated_at
before update on broad_scrape_campaigns
for each row
execute function set_updated_at();

create unique index broad_scrape_campaigns_active_scope_idx
  on broad_scrape_campaigns (scope_id)
  where status in ('running', 'paused');

create unique index broad_scrape_campaigns_single_active_idx
  on broad_scrape_campaigns ((true))
  where status in ('running', 'paused');

create index broad_scrape_campaigns_status_next_attempt_idx
  on broad_scrape_campaigns (status, next_attempt_at);

create table broad_scrape_campaign_leaves (
  campaign_id bigint not null references broad_scrape_campaigns(id) on delete cascade,
  leaf_key text not null,
  ordinal int not null,
  site_filter jsonb not null,
  status text not null default 'pending',
  attempt_count int not null default 0,
  pages_fetched int not null default 0,
  listings jsonb not null default '[]'::jsonb,
  last_attempt_at timestamptz,
  completed_at timestamptz,
  error_message text,

  constraint broad_scrape_campaign_leaves_pkey primary key (campaign_id, leaf_key),
  constraint broad_scrape_campaign_leaves_status_check check (
    status in ('pending', 'success', 'split')
  ),
  constraint broad_scrape_campaign_leaves_ordinal_non_negative check (ordinal >= 0),
  constraint broad_scrape_campaign_leaves_attempt_count_non_negative check (
    attempt_count >= 0
  ),
  constraint broad_scrape_campaign_leaves_pages_fetched_non_negative check (
    pages_fetched >= 0
  ),
  constraint broad_scrape_campaign_leaves_listings_array check (
    jsonb_typeof(listings) = 'array'
  )
);

create index broad_scrape_campaign_leaves_pending_idx
  on broad_scrape_campaign_leaves (campaign_id, status, ordinal);

create index broad_scrape_campaign_leaves_waf_attempt_idx
  on broad_scrape_campaign_leaves (last_attempt_at desc)
  where error_message = 'kiwihousesitters_waf_challenge';
