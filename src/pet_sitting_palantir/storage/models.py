"""Shared storage data models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
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
class ListingRecord:
    """Persisted listing fields derived from a scraped listing."""

    external_id: str
    content_hash: str
    island: str | None = None
    region: str | None = None
    subregion: str | None = None
    city: str | None = None
    duration_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    house_type: str | None = None
    total_animals: int = 0
    dogs_count: int = 0
    cats_count: int = 0
    fish_count: int = 0
    birds_count: int = 0
    rabbits_guinea_pigs_count: int = 0
    chickens_ducks_geese_count: int = 0
    farm_animals_count: int = 0
    horses_count: int = 0
    reptiles_count: int = 0
    other_pets_count: int = 0
    no_pets: bool = False
    starts_soon: bool = False
    reply_rating_score: int | None = None
    listing_tag: str | None = None
    title: str | None = None
    intro: str | None = None
    url: str = ""


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
