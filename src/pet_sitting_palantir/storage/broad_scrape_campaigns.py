"""Persistence for resumable broad-scope scrape campaigns."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from pet_sitting_palantir.kiwihousesitters.constants import WAF_CHALLENGE_ERROR_MARKER
from pet_sitting_palantir.storage.models import (
    BroadScrapeCampaign,
    BroadScrapeCampaignCoverage,
    BroadScrapeCampaignLeaf,
    ScrapeScope,
)


def read_active_broad_scrape_campaign(
    connection: Connection,
    *,
    scope_id: int,
) -> BroadScrapeCampaign | None:
    """Read the active campaign for a scope, if one exists."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select *
            from broad_scrape_campaigns
            where scope_id = %s
              and status in ('running', 'paused')
            order by id desc
            limit 1
            """,
            (scope_id,),
        )
        row = cursor.fetchone()
        return _campaign_from_row(row) if row else None


def create_broad_scrape_campaign(
    connection: Connection,
    *,
    scope: ScrapeScope,
    leaves: Sequence[tuple[str, Mapping[str, Any]]],
    next_attempt_at: datetime,
) -> BroadScrapeCampaign:
    """Create a campaign and its stable ordered direct or fallback leaves."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into broad_scrape_campaigns (
              scope_id,
              scope_name,
              next_attempt_at
            )
            values (%s, %s, %s)
            returning *
            """,
            (scope.id, scope.name, next_attempt_at),
        )
        campaign = _campaign_from_row(cursor.fetchone())
        cursor.executemany(
            """
            insert into broad_scrape_campaign_leaves (
              campaign_id,
              leaf_key,
              ordinal,
              site_filter
            )
            values (%s, %s, %s, %s)
            """,
            [
                (campaign.id, leaf_key, ordinal, Jsonb(dict(site_filter)))
                for ordinal, (leaf_key, site_filter) in enumerate(leaves)
            ],
        )
    return campaign


def read_next_broad_scrape_campaign_leaf(
    connection: Connection,
    *,
    campaign_id: int,
) -> BroadScrapeCampaignLeaf | None:
    """Read the first unfinished leaf in deterministic order."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select *
            from broad_scrape_campaign_leaves
            where campaign_id = %s
              and status = 'pending'
            order by ordinal
            limit 1
            """,
            (campaign_id,),
        )
        row = cursor.fetchone()
        return _leaf_from_row(row) if row else None


def record_broad_scrape_leaf_success(
    connection: Connection,
    *,
    campaign_id: int,
    leaf_key: str,
    pages_fetched: int,
    listings: Sequence[Mapping[str, Any]],
    completed_at: datetime,
    next_attempt_at: datetime,
) -> None:
    """Persist one complete leaf and schedule the next campaign step."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update broad_scrape_campaign_leaves
            set
              status = 'success',
              attempt_count = attempt_count + 1,
              pages_fetched = %s,
              listings = %s,
              last_attempt_at = %s,
              completed_at = %s,
              error_message = null
            where campaign_id = %s
              and leaf_key = %s
              and status = 'pending'
            """,
            (
                pages_fetched,
                Jsonb(list(dict(listing) for listing in listings)),
                completed_at,
                completed_at,
                campaign_id,
                leaf_key,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Pending campaign leaf does not exist: {campaign_id}/{leaf_key}")
        cursor.execute(
            """
            update broad_scrape_campaigns
            set
              status = 'running',
              next_attempt_at = %s,
              error_message = null
            where id = %s
              and status in ('running', 'paused')
            """,
            (next_attempt_at, campaign_id),
        )


def record_broad_scrape_leaf_failure(
    connection: Connection,
    *,
    campaign_id: int,
    leaf_key: str,
    attempted_at: datetime,
    next_attempt_at: datetime,
    error_message: str,
    waf_challenge: bool,
) -> int:
    """Keep a failed leaf pending and pause its campaign until retry time."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update broad_scrape_campaign_leaves
            set
              attempt_count = attempt_count + 1,
              last_attempt_at = %s,
              error_message = %s
            where campaign_id = %s
              and leaf_key = %s
              and status = 'pending'
            """,
            (attempted_at, error_message, campaign_id, leaf_key),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Pending campaign leaf does not exist: {campaign_id}/{leaf_key}")
        cursor.execute(
            """
            update broad_scrape_campaigns
            set
              status = 'paused',
              next_attempt_at = %s,
              error_message = %s,
              waf_challenge_count = waf_challenge_count + %s
            where id = %s
              and status in ('running', 'paused')
            returning waf_challenge_count
            """,
            (next_attempt_at, error_message, int(waf_challenge), campaign_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Active campaign does not exist: {campaign_id}")
        return row["waf_challenge_count"]


def split_broad_scrape_campaign_leaf(
    connection: Connection,
    *,
    leaf: BroadScrapeCampaignLeaf,
    children: Sequence[tuple[str, Mapping[str, Any]]],
    attempted_at: datetime,
    next_attempt_at: datetime,
    error_message: str,
    waf_challenge: bool,
) -> int:
    """Replace a failed parent-sized leaf with smaller pending leaves."""
    if not children:
        raise ValueError("A split campaign leaf requires at least one child")

    ordinal_shift = len(children)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update broad_scrape_campaign_leaves
            set
              status = 'split',
              attempt_count = attempt_count + 1,
              last_attempt_at = %s,
              error_message = %s
            where campaign_id = %s
              and leaf_key = %s
              and status = 'pending'
            """,
            (attempted_at, error_message, leaf.campaign_id, leaf.leaf_key),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"Pending campaign leaf does not exist: {leaf.campaign_id}/{leaf.leaf_key}"
            )
        if ordinal_shift:
            cursor.execute(
                """
                update broad_scrape_campaign_leaves
                set ordinal = ordinal + %s
                where campaign_id = %s
                  and ordinal > %s
                """,
                (ordinal_shift, leaf.campaign_id, leaf.ordinal),
            )
        cursor.executemany(
            """
            insert into broad_scrape_campaign_leaves (
              campaign_id,
              leaf_key,
              ordinal,
              site_filter
            )
            values (%s, %s, %s, %s)
            """,
            [
                (
                    leaf.campaign_id,
                    child_key,
                    leaf.ordinal + offset + 1,
                    Jsonb(dict(site_filter)),
                )
                for offset, (child_key, site_filter) in enumerate(children)
            ],
        )
        cursor.execute(
            """
            update broad_scrape_campaigns
            set
              status = 'paused',
              next_attempt_at = %s,
              error_message = %s,
              waf_challenge_count = waf_challenge_count + %s
            where id = %s
              and status in ('running', 'paused')
            returning waf_challenge_count
            """,
            (
                next_attempt_at,
                error_message,
                int(waf_challenge),
                leaf.campaign_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Active campaign does not exist: {leaf.campaign_id}")
        return row["waf_challenge_count"]


def read_broad_scrape_campaign_progress(
    connection: Connection,
    *,
    campaign_id: int,
) -> tuple[int, int]:
    """Return completed and total leaf counts."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              count(*) filter (where status = 'success') as completed,
              count(*) filter (where status in ('pending', 'success')) as total
            from broad_scrape_campaign_leaves
            where campaign_id = %s
            """,
            (campaign_id,),
        )
        row = cursor.fetchone()
        return row["completed"], row["total"]


def read_broad_scrape_campaign_payload(
    connection: Connection,
    *,
    campaign_id: int,
) -> tuple[
    int,
    tuple[Mapping[str, Any], ...],
    Mapping[str, datetime],
    tuple[BroadScrapeCampaignCoverage, ...],
]:
    """Merge successful leaf payloads and deduplicate listings by external id."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select site_filter, pages_fetched, listings, completed_at
            from broad_scrape_campaign_leaves
            where campaign_id = %s
              and status = 'success'
            order by ordinal
            """,
            (campaign_id,),
        )
        pages_fetched = 0
        listings_by_external_id: dict[str, tuple[Mapping[str, Any], datetime]] = {}
        coverages: list[BroadScrapeCampaignCoverage] = []
        for row in cursor.fetchall():
            pages_fetched += row["pages_fetched"]
            completed_at = row["completed_at"]
            if completed_at is None:
                raise ValueError("Successful campaign leaf is missing completed_at")
            seen_external_ids: set[str] = set()
            for listing in row["listings"]:
                external_id = listing.get("external_id")
                if not isinstance(external_id, str):
                    raise ValueError("Campaign listing is missing external_id")
                seen_external_ids.add(external_id)
                previous = listings_by_external_id.get(external_id)
                if previous is None or previous[1] <= completed_at:
                    listings_by_external_id[external_id] = (listing, completed_at)
            coverages.append(
                BroadScrapeCampaignCoverage(
                    site_filter=row["site_filter"],
                    completed_at=completed_at,
                    seen_external_ids=frozenset(seen_external_ids),
                )
            )
        return (
            pages_fetched,
            tuple(item[0] for item in listings_by_external_id.values()),
            {external_id: item[1] for external_id, item in listings_by_external_id.items()},
            tuple(coverages),
        )


def complete_broad_scrape_campaign(
    connection: Connection,
    *,
    campaign_id: int,
    completed_at: datetime,
) -> None:
    """Discard staged payloads and close a campaign with its parent transaction."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            update broad_scrape_campaign_leaves
            set listings = '[]'::jsonb
            where campaign_id = %s
              and listings <> '[]'::jsonb
            """,
            (campaign_id,),
        )
        cursor.execute(
            """
            update broad_scrape_campaigns
            set
              status = 'completed',
              completed_at = %s,
              next_attempt_at = %s,
              error_message = null
            where id = %s
              and status in ('running', 'paused')
            """,
            (completed_at, completed_at, campaign_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Active campaign does not exist: {campaign_id}")


def read_latest_campaign_waf_challenge_at(connection: Connection) -> datetime | None:
    """Return when a broad campaign most recently encountered a WAF challenge."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select max(last_attempt_at) as challenged_at
            from broad_scrape_campaign_leaves
            where error_message = %s
            """,
            (WAF_CHALLENGE_ERROR_MARKER,),
        )
        row = cursor.fetchone()
        return row["challenged_at"]


def read_latest_campaign_scope_waf_challenge_at(
    connection: Connection,
    *,
    scope_id: int,
) -> datetime | None:
    """Return the latest campaign WAF challenge for one logical scope."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select max(leaves.last_attempt_at) as challenged_at
            from broad_scrape_campaign_leaves as leaves
            join broad_scrape_campaigns as campaigns on campaigns.id = leaves.campaign_id
            where campaigns.scope_id = %s
              and leaves.error_message = %s
            """,
            (scope_id, WAF_CHALLENGE_ERROR_MARKER),
        )
        row = cursor.fetchone()
        return row["challenged_at"]


def _campaign_from_row(row: Mapping[str, Any]) -> BroadScrapeCampaign:
    return BroadScrapeCampaign(
        id=row["id"],
        scope_id=row["scope_id"],
        scope_name=row["scope_name"],
        status=row["status"],
        started_at=row["started_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        next_attempt_at=row["next_attempt_at"],
        waf_challenge_count=row["waf_challenge_count"],
        error_message=row["error_message"],
    )


def _leaf_from_row(row: Mapping[str, Any]) -> BroadScrapeCampaignLeaf:
    return BroadScrapeCampaignLeaf(
        campaign_id=row["campaign_id"],
        leaf_key=row["leaf_key"],
        ordinal=row["ordinal"],
        site_filter=row["site_filter"],
        status=row["status"],
        attempt_count=row["attempt_count"],
        pages_fetched=row["pages_fetched"],
        listings=tuple(row["listings"]),
        last_attempt_at=row["last_attempt_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )
