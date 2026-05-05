"""Listing lifecycle updates."""

from collections.abc import Mapping
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS, STATE_LABELS
from pet_sitting_palantir.storage.models import ScrapeScope


def mark_missing_listings_for_scope(
    connection: Connection,
    *,
    scope: ScrapeScope,
    seen_external_ids: set[str],
) -> int:
    """Mark covered listings missing when absent from a successful scope scrape."""
    where_sql, where_params = _scope_coverage_clause(scope.site_filter)
    seen_ids = list(seen_external_ids)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            update listings
            set
              missing_count = missing_count + 1,
              status = case
                when missing_count + 1 >= %s then 'missing_confirmed'
                else 'missing_once'
              end,
              missing_since = coalesce(missing_since, now()),
              closed_at = case
                when missing_count + 1 >= %s then coalesce(closed_at, now())
                else closed_at
              end
            where status in ('active', 'missing_once')
              and external_id <> all(%s)
              and {where_sql}
            """,
            (
                scope.missing_threshold_runs,
                scope.missing_threshold_runs,
                seen_ids,
                *where_params,
            ),
        )
        return cursor.rowcount


def mark_expired_by_date(connection: Connection) -> int:
    """Mark listings expired when their end date is before the database current date."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update listings
            set
              status = 'expired_by_date',
              closed_at = coalesce(closed_at, now())
            where status in ('active', 'missing_once', 'missing_confirmed')
              and end_date is not null
              and end_date < current_date
            """
        )
        return cursor.rowcount


def _scope_coverage_clause(site_filter: Mapping[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    state = site_filter.get("state")
    if state:
        _require_string("state", state)
        clauses.append("island = %s")
        params.append(_state_label(state))

    region = site_filter.get("region")
    if region:
        _require_string("region", region)
        clauses.append("region = %s")
        params.append(_region_label(region))

    subregion = site_filter.get("subregion")
    if subregion:
        _require_string("subregion", subregion)
        if not region:
            raise ValueError("subregion filters require a region")
        clauses.append("subregion = %s")
        params.append(_subregion_label(region, subregion))

    if not clauses:
        return "true", []

    return " and ".join(clauses), params


def _state_label(state: Any) -> str:
    try:
        return STATE_LABELS[state]
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters state filter: {state}") from error


def _region_label(region: Any) -> str:
    try:
        return REGION_FILTERS[region].label
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters region filter: {region}") from error


def _subregion_label(region: Any, subregion: Any) -> str:
    try:
        return REGION_FILTERS[region].subregions[subregion].label
    except KeyError as error:
        raise ValueError(
            f"Unsupported KiwiHouseSitters subregion filter: {region}/{subregion}"
        ) from error


def _require_string(key: str, value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError(f"site_filter.{key} must be a string")
