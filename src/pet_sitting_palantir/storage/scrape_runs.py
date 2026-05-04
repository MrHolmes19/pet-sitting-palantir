"""Storage functions for scrape runs."""

from psycopg import Connection

from pet_sitting_palantir.storage.models import ScrapeRunCounts, ScrapeRunStatus


def create_scrape_run(
    connection: Connection,
    *,
    scope_id: int | None,
    scope_name: str,
    search_url: str | None = None,
) -> int:
    """Create a running scrape_runs row and mark the scope attempted."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into scrape_runs (scope_id, scope_name, search_url)
            values (%s, %s, %s)
            returning id
            """,
            (scope_id, scope_name, search_url),
        )
        run_id = cursor.fetchone()["id"]

        if scope_id is not None:
            cursor.execute(
                """
                update scrape_scopes
                set last_attempt_at = now()
                where id = %s
                """,
                (scope_id,),
            )

        return run_id


def close_scrape_run(
    connection: Connection,
    *,
    run_id: int,
    status: ScrapeRunStatus,
    counts: ScrapeRunCounts | None = None,
    error_message: str | None = None,
) -> None:
    """Close a scrape run with final status and counters."""
    final_counts = counts or ScrapeRunCounts()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_runs
            set
              finished_at = now(),
              status = %s,
              pages_fetched = %s,
              listings_seen = %s,
              new_listings = %s,
              changed_listings = %s,
              missing_marked = %s,
              alerts_sent = %s,
              error_message = %s
            where id = %s
            returning scope_id
            """,
            (
                status,
                final_counts.pages_fetched,
                final_counts.listings_seen,
                final_counts.new_listings,
                final_counts.changed_listings,
                final_counts.missing_marked,
                final_counts.alerts_sent,
                error_message,
                run_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Scrape run does not exist: {run_id}")

        scope_id = row["scope_id"]
        if status == "success" and scope_id is not None:
            cursor.execute(
                """
                update scrape_scopes
                set last_success_at = now()
                where id = %s
                """,
                (scope_id,),
            )
