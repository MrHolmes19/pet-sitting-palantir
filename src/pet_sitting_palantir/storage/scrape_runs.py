"""Storage functions for scrape runs."""

from datetime import datetime

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.constants import WAF_CHALLENGE_ERROR_MARKER
from pet_sitting_palantir.storage.models import ScrapeRunCounts, ScrapeRunStatus


def read_latest_waf_challenge_at(connection: Connection) -> datetime | None:
    """Return the latest persisted WAF challenge, including the legacy error format."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select coalesce(finished_at, started_at) as challenged_at
            from scrape_runs
            where status = 'failed'
              and (
                error_message like %s
                or (
                  error_message like '%%Unexpected status code: 202;%%'
                  and error_message like '%%awsWafCookieDomainList%%'
                )
              )
            order by coalesce(finished_at, started_at) desc
            limit 1
            """,
            (f"%{WAF_CHALLENGE_ERROR_MARKER}%",),
        )
        row = cursor.fetchone()
        return row["challenged_at"] if row else None


def read_latest_scope_waf_challenge_at(
    connection: Connection,
    *,
    scope_name: str,
) -> datetime | None:
    """Return the latest persisted WAF challenge for one logical scope."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select coalesce(finished_at, started_at) as challenged_at
            from scrape_runs
            where scope_name = %s
              and status = 'failed'
              and (
                error_message like %s
                or (
                  error_message like '%%Unexpected status code: 202;%%'
                  and error_message like '%%awsWafCookieDomainList%%'
                )
              )
            order by coalesce(finished_at, started_at) desc
            limit 1
            """,
            (scope_name, f"%{WAF_CHALLENGE_ERROR_MARKER}%"),
        )
        row = cursor.fetchone()
        return row["challenged_at"] if row else None


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
                set last_attempt_at = clock_timestamp()
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
    advance_covered_scopes: bool = True,
) -> None:
    """Close a scrape run with final status and counters."""
    final_counts = counts or ScrapeRunCounts()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_runs
            set
              finished_at = clock_timestamp(),
              status = %s,
              pages_fetched = %s,
              listings_seen = %s,
              new_listings = %s,
              changed_listings = %s,
              missing_marked = %s,
              alerts_sent = %s,
              error_message = %s
            where id = %s
            returning scope_id, finished_at
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
        if status == "success" and scope_id is not None and advance_covered_scopes:
            cursor.execute(
                """
                update scrape_scopes as covered
                set last_success_at = %s
                from scrape_scopes as completed
                where completed.id = %s
                  and covered.enabled = true
                  and covered.site_filter @> completed.site_filter
                  and (
                    covered.last_success_at is null
                    or covered.last_success_at < %s
                  )
                """,
                (row["finished_at"], scope_id, row["finished_at"]),
            )
        elif status == "success" and scope_id is not None:
            cursor.execute(
                """
                update scrape_scopes
                set last_success_at = %s
                where id = %s
                  and (
                    last_success_at is null
                    or last_success_at < %s
                  )
                """,
                (row["finished_at"], scope_id, row["finished_at"]),
            )
