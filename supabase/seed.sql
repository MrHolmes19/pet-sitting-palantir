insert into scrape_scopes (
  name,
  interval_minutes,
  missing_threshold_runs,
  site_filter
)
values
  (
    'auckland_central',
    5,
    6,
    '{"state":"north-island","region":"auckland","subregion":"auckland-central"}'::jsonb
  ),
  (
    'auckland_region',
    15,
    4,
    '{"state":"north-island","region":"auckland"}'::jsonb
  ),
  (
    'north_island',
    720,
    3,
    '{"state":"north-island"}'::jsonb
  ),
  (
    'all_nz',
    1440,
    3,
    '{}'::jsonb
  )
on conflict (name) do update
set
  interval_minutes = excluded.interval_minutes,
  missing_threshold_runs = excluded.missing_threshold_runs,
  site_filter = excluded.site_filter,
  updated_at = now();
