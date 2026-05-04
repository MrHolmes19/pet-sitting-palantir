"""Persistence boundaries for database-backed state."""

from pet_sitting_palantir.storage.database import connect_database, database_connection
from pet_sitting_palantir.storage.listings import upsert_listing, upsert_listings
from pet_sitting_palantir.storage.models import (
    ListingUpsertResult,
    ListingUpsertSummary,
    ScrapeRunCounts,
    ScrapeScope,
)
from pet_sitting_palantir.storage.scrape_runs import close_scrape_run, create_scrape_run
from pet_sitting_palantir.storage.scrape_scopes import read_enabled_scrape_scopes

__all__ = [
    "ListingUpsertResult",
    "ListingUpsertSummary",
    "ScrapeRunCounts",
    "ScrapeScope",
    "close_scrape_run",
    "connect_database",
    "create_scrape_run",
    "database_connection",
    "read_enabled_scrape_scopes",
    "upsert_listing",
    "upsert_listings",
]
