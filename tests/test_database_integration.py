import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.rows import dict_row

from pet_sitting_palantir.storage import initialize_database

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

MIGRATIONS_DIR = Path(__file__).parents[1] / "supabase" / "migrations"
SEED_FILE = Path(__file__).parents[1] / "supabase" / "seed.sql"


def _database_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


@pytest.mark.integration
def test_initial_schema_and_seed_apply_to_real_postgres() -> None:
    if psycopg is None:
        pytest.skip("psycopg is not installed")

    database_url = _database_url()
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to run this integration test")

    schema_name = f"test_schema_{uuid4().hex}"
    migration_sql = "\n".join(path.read_text() for path in sorted(MIGRATIONS_DIR.glob("*.sql")))
    seed_sql = SEED_FILE.read_text()

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("create schema {}").format(sql.Identifier(schema_name))
            )
            cursor.execute(
                sql.SQL("set search_path to {}, public").format(sql.Identifier(schema_name))
            )

            try:
                cursor.execute(migration_sql)
                cursor.execute(seed_sql)

                cursor.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = %s
                    order by table_name
                    """,
                    (schema_name,),
                )
                table_names = {row["table_name"] for row in cursor.fetchall()}

                assert {
                    "alert_delivery_attempts",
                    "alert_events",
                    "alert_filters",
                    "listings",
                    "scrape_runs",
                    "scrape_scopes",
                }.issubset(table_names)
                assert "sent_alerts" not in table_names

                cursor.execute(
                    """
                    select name, interval_minutes, missing_threshold_runs, site_filter
                    from scrape_scopes
                    order by name
                    """
                )
                scopes = {row["name"]: row for row in cursor.fetchall()}

                assert set(scopes) == {
                    "all_nz",
                    "auckland_central",
                    "auckland_region",
                    "north_island",
                    "north_shore_city",
                }
                assert scopes["auckland_central"]["interval_minutes"] == 5
                assert scopes["auckland_central"]["missing_threshold_runs"] == 6
                assert scopes["north_shore_city"]["interval_minutes"] == 10
                assert scopes["north_shore_city"]["missing_threshold_runs"] == 3
                assert scopes["auckland_region"]["interval_minutes"] == 60
                assert scopes["all_nz"]["site_filter"] == {}
            finally:
                cursor.execute(
                    sql.SQL("drop schema {} cascade").format(sql.Identifier(schema_name))
                )


@pytest.mark.integration
def test_initialize_database_applies_schema_and_seed_to_real_postgres() -> None:
    if psycopg is None:
        pytest.skip("psycopg is not installed")

    database_url = _database_url()
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to run this integration test")

    schema_name = f"test_schema_{uuid4().hex}"

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("create schema {}").format(sql.Identifier(schema_name)))
            cursor.execute(
                sql.SQL("set search_path to {}, public").format(sql.Identifier(schema_name))
            )

            try:
                first_result = initialize_database(connection)
                second_result = initialize_database(connection)

                cursor.execute("select count(*) as scope_count from scrape_scopes")
                row = cursor.fetchone()
                cursor.execute("select filename from schema_migrations order by filename")
                migrations = [migration["filename"] for migration in cursor.fetchall()]

                assert first_result.schema_applied is True
                assert first_result.seed_applied is True
                assert second_result.schema_applied is False
                assert second_result.seed_applied is False
                assert row["scope_count"] == 5
                assert migrations == [
                    "20260503000100_initial_schema.sql",
                    "20260526000100_alert_events_and_delivery_attempts.sql",
                ]
            finally:
                cursor.execute(
                    sql.SQL("drop schema {} cascade").format(sql.Identifier(schema_name))
                )


@pytest.mark.integration
def test_initialize_database_upgrades_schema_created_before_migration_history() -> None:
    if psycopg is None:
        pytest.skip("psycopg is not installed")

    database_url = _database_url()
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to run this integration test")

    schema_name = f"test_schema_{uuid4().hex}"
    initial_sql = (MIGRATIONS_DIR / "20260503000100_initial_schema.sql").read_text()

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("create schema {}").format(sql.Identifier(schema_name)))
            cursor.execute(
                sql.SQL("set search_path to {}, public").format(sql.Identifier(schema_name))
            )

            try:
                cursor.execute(initial_sql)

                result = initialize_database(connection)

                cursor.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = %s
                    """,
                    (schema_name,),
                )
                table_names = {row["table_name"] for row in cursor.fetchall()}
                cursor.execute("select filename from schema_migrations order by filename")
                migrations = [migration["filename"] for migration in cursor.fetchall()]

                assert result.schema_applied is True
                assert "alert_events" in table_names
                assert "alert_delivery_attempts" in table_names
                assert "sent_alerts" not in table_names
                assert migrations == [
                    "20260503000100_initial_schema.sql",
                    "20260526000100_alert_events_and_delivery_attempts.sql",
                ]
            finally:
                cursor.execute(
                    sql.SQL("drop schema {} cascade").format(sql.Identifier(schema_name))
                )
