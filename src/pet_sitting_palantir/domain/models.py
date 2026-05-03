"""Domain models for scraped listing data."""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Listing:
    """A normalized KiwiHouseSitters listing from a search result card."""

    external_id: str
    url: str
    title: str | None = None
    listing_tag: str | None = None
    intro: str | None = None
    city: str | None = None
    region: str | None = None
    subregion: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int | None = None
    pets_raw: str | None = None
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
    house_type: str | None = None
    starts_soon: bool = False
    reply_rating_score: int | None = None
    reply_rating_text: str | None = None
    content_hash: str | None = None
    raw_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        result = asdict(self)
        result["start_date"] = self.start_date.isoformat() if self.start_date else None
        result["end_date"] = self.end_date.isoformat() if self.end_date else None
        return result
