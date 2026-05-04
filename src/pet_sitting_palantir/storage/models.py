"""Shared storage data models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ScrapeRunStatus = Literal["running", "success", "partial_failure", "failed", "suspicious"]


@dataclass(frozen=True)
class ScrapeScope:
    """Enabled scrape scope read from the database."""

    id: int
    name: str
    enabled: bool
    interval_minutes: int
    missing_threshold_runs: int
    site_filter: Mapping[str, Any]
    last_attempt_at: datetime | None
    last_success_at: datetime | None


@dataclass(frozen=True)
class ScrapeRunCounts:
    """Counters persisted when a scrape run closes."""

    pages_fetched: int = 0
    listings_seen: int = 0
    new_listings: int = 0
    changed_listings: int = 0
    missing_marked: int = 0
    alerts_sent: int = 0


@dataclass(frozen=True)
class ListingUpsertResult:
    """Outcome for one listing upsert."""

    listing_id: int
    created: bool
    changed: bool


@dataclass(frozen=True)
class ListingUpsertSummary:
    """Aggregate outcome for a batch of listing upserts."""

    listings_seen: int
    new_listings: int
    changed_listings: int
