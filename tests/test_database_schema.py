from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parents[1] / "supabase" / "migrations"
SEED_FILE = Path(__file__).parents[1] / "supabase" / "seed.sql"
INITIAL_SCHEMA = MIGRATIONS_DIR / "20260503000100_initial_schema.sql"


def _migration_sql() -> str:
    return "\n".join(path.read_text() for path in sorted(MIGRATIONS_DIR.glob("*.sql")))


def _seed_sql() -> str:
    return SEED_FILE.read_text()


def test_initial_schema_migration_exists() -> None:
    assert INITIAL_SCHEMA.exists()


def test_initial_schema_creates_expected_tables() -> None:
    sql = _migration_sql()

    for table_name in (
        "scrape_scopes",
        "scrape_runs",
        "listings",
        "alert_filters",
        "sent_alerts",
    ):
        assert f"create table {table_name}" in sql


def test_listings_schema_matches_persistence_decision() -> None:
    sql = _migration_sql()

    assert "external_id text not null unique" in sql
    assert "content_hash text not null" in sql
    assert "island text" in sql
    assert "region text" in sql
    assert "subregion text" in sql
    assert "city text" in sql
    assert "total_animals int not null default 0" in sql
    assert "reply_rating_score int" in sql

    assert "raw_data" not in sql
    assert "pets_raw" not in sql
    assert "reply_rating_text" not in sql


def test_listings_schema_keeps_preferred_column_order() -> None:
    sql = _migration_sql()

    ordered_columns = (
        "id bigserial primary key",
        "external_id text not null unique",
        "content_hash text not null",
        "island text",
        "region text",
        "subregion text",
        "city text",
        "duration_days int",
        "start_date date",
        "end_date date",
        "house_type text",
        "total_animals int not null default 0",
        "dogs_count int not null default 0",
        "cats_count int not null default 0",
        "starts_soon boolean not null default false",
        "reply_rating_score int",
        "listing_tag text",
        "title text",
        "intro text",
        "url text not null",
    )

    positions = []
    for column in ordered_columns:
        assert column in sql, f"Expected listings column not found: {column}"
        positions.append(sql.index(column))

    assert positions == sorted(positions)


def test_schema_has_core_constraints_and_indexes() -> None:
    sql = _migration_sql()

    expected_fragments = (
        "status in ('running', 'success', 'partial_failure', 'failed', 'suspicious')",
        "status in ('active', 'missing_once', 'missing_confirmed', 'expired_by_date')",
        "island is null or island in ('North Island', 'South Island')",
        "constraint listings_total_animals_non_negative check (total_animals >= 0)",
        "reply_rating_score is null or reply_rating_score between 0 and 10",
        "constraint sent_alerts_unique_listing_filter_channel_hash unique",
        "create index scrape_scopes_enabled_due_idx",
        "create index scrape_runs_scope_started_idx",
        "create index listings_location_idx",
        "create index listings_start_date_idx",
        "create index sent_alerts_filter_sent_idx",
    )

    for fragment in expected_fragments:
        assert fragment in sql


def test_seed_contains_initial_scrape_scopes() -> None:
    sql = _seed_sql()

    expected_scope_fragments = (
        "'auckland_central'",
        "'auckland_region'",
        "'north_island'",
        "'all_nz'",
        '{"state":"north-island","region":"auckland","subregion":"auckland-central"}',
        '{"state":"north-island","region":"auckland"}',
        '{"state":"north-island"}',
        "'{}'::jsonb",
    )

    for fragment in expected_scope_fragments:
        assert fragment in sql

    assert "on conflict (name) do update" in sql
