"""Storage functions for listings."""

from collections.abc import Iterable
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.storage.models import (
    ListingRecord,
    ListingUpsertResult,
    ListingUpsertSummary,
)

LISTING_COLUMNS = (
    "external_id",
    "content_hash",
    "island",
    "region",
    "subregion",
    "city",
    "duration_days",
    "start_date",
    "end_date",
    "house_type",
    "total_animals",
    "dogs_count",
    "cats_count",
    "fish_count",
    "birds_count",
    "rabbits_guinea_pigs_count",
    "chickens_ducks_geese_count",
    "farm_animals_count",
    "horses_count",
    "reptiles_count",
    "other_pets_count",
    "no_pets",
    "starts_soon",
    "reply_rating_score",
    "listing_tag",
    "title",
    "intro",
    "url",
)


def upsert_listing(
    connection: Connection,
    *,
    listing: ListingRecord,
    run_id: int,
) -> ListingUpsertResult:
    """Insert or update a listing by external_id."""
    _validate_listing_for_persistence(listing)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select id, content_hash
            from listings
            where external_id = %s
            for update
            """,
            (listing.external_id,),
        )
        existing = cursor.fetchone()

        values = _listing_values(listing)
        if existing is None:
            cursor.execute(
                f"""
                insert into listings (
                  {", ".join(LISTING_COLUMNS)},
                  first_seen_run_id,
                  last_seen_run_id
                )
                values (
                  {", ".join(["%s"] * len(LISTING_COLUMNS))},
                  %s,
                  %s
                )
                returning id
                """,
                (*values, run_id, run_id),
            )
            return ListingUpsertResult(
                listing_id=cursor.fetchone()["id"],
                created=True,
                changed=False,
            )

        changed = existing["content_hash"] != listing.content_hash
        assignments = ",\n              ".join(f"{column} = %s" for column in LISTING_COLUMNS[1:])
        cursor.execute(
            f"""
            update listings
            set
              {assignments},
              last_seen_at = now(),
              last_seen_run_id = %s,
              status = 'active',
              missing_count = 0,
              missing_since = null,
              closed_at = null
            where id = %s
            """,
            (*values[1:], run_id, existing["id"]),
        )
        return ListingUpsertResult(
            listing_id=existing["id"],
            created=False,
            changed=changed,
        )


def upsert_listings(
    connection: Connection,
    *,
    listings: Iterable[ListingRecord],
    run_id: int,
) -> ListingUpsertSummary:
    """Upsert a batch of listings and return counters for scrape_runs."""
    seen = 0
    created = 0
    changed = 0

    for listing in listings:
        seen += 1
        result = upsert_listing(connection, listing=listing, run_id=run_id)
        created += int(result.created)
        changed += int(result.changed)

    return ListingUpsertSummary(
        listings_seen=seen,
        new_listings=created,
        changed_listings=changed,
    )


def _listing_values(listing: ListingRecord) -> tuple[Any, ...]:
    return tuple(getattr(listing, column) for column in LISTING_COLUMNS)


def _validate_listing_for_persistence(listing: ListingRecord) -> None:
    if not listing.content_hash:
        raise ValueError(f"Listing {listing.external_id} cannot be persisted without content_hash")
    if not listing.url:
        raise ValueError(f"Listing {listing.external_id} cannot be persisted without url")
