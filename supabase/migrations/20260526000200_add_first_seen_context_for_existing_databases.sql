-- `first_seen_context` was introduced before migration history was tracked.
-- Upgrade databases created from the earlier initial schema definition.
alter table listings
add column if not exists first_seen_context text not null default 'observed';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'listings'::regclass
      and conname = 'listings_first_seen_context_check'
  ) then
    alter table listings
    add constraint listings_first_seen_context_check
    check (first_seen_context in ('baseline', 'observed'));
  end if;
end;
$$;
