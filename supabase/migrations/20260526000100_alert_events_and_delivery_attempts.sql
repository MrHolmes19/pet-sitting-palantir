-- Alert delivery has not been implemented; replace its placeholder table with
-- event and attempt records before it can receive production data.
drop table sent_alerts;

alter table listings
add column appearance_sequence int not null default 1;

alter table listings
add constraint listings_appearance_sequence_positive
check (appearance_sequence > 0);

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

  constraint alert_events_event_type_check check (
    event_type in ('first_match', 'became_match', 'material_change', 'confirmed_reappearance')
  ),
  constraint alert_events_appearance_sequence_positive check (appearance_sequence > 0),
  constraint alert_events_target_channels_non_empty check (cardinality(target_channels) > 0),
  constraint alert_events_unique_listing_filter_appearance_fingerprint unique (
    listing_id,
    filter_id,
    appearance_sequence,
    alert_fingerprint
  )
);

create table alert_delivery_attempts (
  id bigserial primary key,

  alert_event_id bigint not null references alert_events(id),
  channel text not null,

  attempted_at timestamptz not null default now(),
  status text not null,
  message text,
  provider_message_id text,
  error_message text,

  constraint alert_delivery_attempts_status_check check (status in ('sent', 'failed'))
);

create index alert_events_filter_created_idx
  on alert_events (filter_id, created_at desc);

create index alert_events_delivery_due_idx
  on alert_events (deliver_after, created_at);

create index alert_delivery_attempts_event_attempted_idx
  on alert_delivery_attempts (alert_event_id, attempted_at desc);

create index alert_delivery_attempts_status_attempted_idx
  on alert_delivery_attempts (status, attempted_at desc);

create unique index alert_delivery_attempts_unique_success_idx
  on alert_delivery_attempts (alert_event_id, channel)
  where status = 'sent';
