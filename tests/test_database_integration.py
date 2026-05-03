import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.rows import dict_row

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

MIGRATION_FILE = (
    Path(__file__).parents[1]
    / "supabase"
    / "migrations"
    / "20260503000100_initial_schema.sql"
)
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
    migration_sql = MIGRATION_FILE.read_text()
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
                cursor.execute(migration_sql.replace("public.", ""))
                cursor.execute(seed_sql.replace("public.", ""))

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
                    "alert_filters",
                    "listings",
                    "scrape_runs",
                    "scrape_scopes",
                    "sent_alerts",
                }.issubset(table_names)

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
                }
                assert scopes["auckland_central"]["interval_minutes"] == 5
                assert scopes["auckland_central"]["missing_threshold_runs"] == 6
                assert scopes["all_nz"]["site_filter"] == {}
            finally:
                cursor.execute(
                    sql.SQL("drop schema {} cascade").format(sql.Identifier(schema_name))
                )
