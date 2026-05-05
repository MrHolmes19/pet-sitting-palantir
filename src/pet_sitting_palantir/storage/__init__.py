"""Persistence boundaries for database-backed state."""

from pet_sitting_palantir.storage.conversions import listing_record_from_scraped_listing
from pet_sitting_palantir.storage.database import connect_database, database_connection
from pet_sitting_palantir.storage.lifecycle import (
    mark_expired_by_date,
    mark_missing_listings_for_scope,
)
from pet_sitting_palantir.storage.listings import upsert_listing, upsert_listings
from pet_sitting_palantir.storage.models import (
    ListingRecord,
    ListingUpsertResult,
    ListingUpsertSummary,
    ScrapeRunCounts,
    ScrapeScope,
)
from pet_sitting_palantir.storage.scrape_runs import close_scrape_run, create_scrape_run
from pet_sitting_palantir.storage.scrape_scopes import (
    read_enabled_scrape_scope,
    read_enabled_scrape_scopes,
)

__all__ = [
    "ListingRecord",
    "ListingUpsertResult",
    "ListingUpsertSummary",
    "ScrapeRunCounts",
    "ScrapeScope",
    "close_scrape_run",
    "connect_database",
    "create_scrape_run",
    "database_connection",
    "listing_record_from_scraped_listing",
    "mark_expired_by_date",
    "mark_missing_listings_for_scope",
    "read_enabled_scrape_scope",
    "read_enabled_scrape_scopes",
    "upsert_listing",
    "upsert_listings",
]
