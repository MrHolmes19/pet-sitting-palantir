"""Persistence boundaries for database-backed state."""

from pet_sitting_palantir.storage.broad_scrape_campaigns import (
    complete_broad_scrape_campaign,
    create_broad_scrape_campaign,
    read_active_broad_scrape_campaign,
    read_broad_scrape_campaign_payload,
    read_broad_scrape_campaign_progress,
    read_latest_campaign_scope_waf_challenge_at,
    read_latest_campaign_waf_challenge_at,
    read_next_broad_scrape_campaign_leaf,
    record_broad_scrape_leaf_failure,
    record_broad_scrape_leaf_success,
    split_broad_scrape_campaign_leaf,
)
from pet_sitting_palantir.storage.conversions import listing_record_from_scraped_listing
from pet_sitting_palantir.storage.database import connect_database, database_connection
from pet_sitting_palantir.storage.lifecycle import (
    mark_expired_by_date,
    mark_missing_listings_for_scope,
)
from pet_sitting_palantir.storage.listings import upsert_listing, upsert_listings
from pet_sitting_palantir.storage.models import (
    BroadScrapeCampaign,
    BroadScrapeCampaignCoverage,
    BroadScrapeCampaignLeaf,
    ListingRecord,
    ListingUpsertResult,
    ListingUpsertSummary,
    ScrapeRunCounts,
    ScrapeScope,
)
from pet_sitting_palantir.storage.schema import DatabaseInitResult, initialize_database
from pet_sitting_palantir.storage.scrape_runs import (
    close_scrape_run,
    create_scrape_run,
    read_latest_scope_waf_challenge_at,
    read_latest_waf_challenge_at,
)
from pet_sitting_palantir.storage.scrape_scopes import (
    read_due_scrape_scopes,
    read_enabled_scrape_scope,
    read_enabled_scrape_scopes,
)

__all__ = [
    "DatabaseInitResult",
    "BroadScrapeCampaign",
    "BroadScrapeCampaignCoverage",
    "BroadScrapeCampaignLeaf",
    "ListingRecord",
    "ListingUpsertResult",
    "ListingUpsertSummary",
    "ScrapeRunCounts",
    "ScrapeScope",
    "close_scrape_run",
    "complete_broad_scrape_campaign",
    "connect_database",
    "create_broad_scrape_campaign",
    "create_scrape_run",
    "database_connection",
    "initialize_database",
    "listing_record_from_scraped_listing",
    "mark_expired_by_date",
    "mark_missing_listings_for_scope",
    "read_due_scrape_scopes",
    "read_active_broad_scrape_campaign",
    "read_broad_scrape_campaign_payload",
    "read_broad_scrape_campaign_progress",
    "read_enabled_scrape_scope",
    "read_enabled_scrape_scopes",
    "read_latest_waf_challenge_at",
    "read_latest_scope_waf_challenge_at",
    "read_latest_campaign_waf_challenge_at",
    "read_latest_campaign_scope_waf_challenge_at",
    "read_next_broad_scrape_campaign_leaf",
    "record_broad_scrape_leaf_failure",
    "record_broad_scrape_leaf_success",
    "split_broad_scrape_campaign_leaf",
    "upsert_listing",
    "upsert_listings",
]
