"""Provider-neutral formatting of alert notification content."""

from dataclasses import dataclass
from datetime import date

from pet_sitting_palantir.storage.models import ListingRecord

ANIMAL_LABELS = (
    ("dogs_count", "dog", "dogs"),
    ("cats_count", "cat", "cats"),
    ("fish_count", "fish", "fish"),
    ("birds_count", "bird", "birds"),
    ("rabbits_guinea_pigs_count", "rabbit/guinea pig", "rabbits/guinea pigs"),
    ("chickens_ducks_geese_count", "chicken/duck/goose", "chickens/ducks/geese"),
    ("farm_animals_count", "farm animal", "farm animals"),
    ("horses_count", "horse", "horses"),
    ("reptiles_count", "reptile", "reptiles"),
    ("other_pets_count", "other pet", "other pets"),
)


@dataclass(frozen=True)
class AlertMessage:
    """Text content suitable for a notification channel."""

    text: str


def format_alert_message(*, alert_name: str, listing: ListingRecord) -> AlertMessage:
    """Create a compact message identifying the matching alert and listing."""
    location = ", ".join(
        value.upper() for value in (listing.city, listing.region) if value
    ) or "NEW MATCHING HOUSE SIT"
    lines = [
        alert_name,
        "",
        location,
        "",
        f"DATES: {_date_text(listing.start_date)} - {_date_text(listing.end_date)}",
        f"LENGTH: {_duration_text(listing.duration_days)}",
        f"PETS: {_pets_text(listing)}",
        "",
        f"VIEW HOUSE AD: {listing.url}",
    ]
    return AlertMessage(text="\n".join(lines))


def _date_text(value: date | None) -> str:
    if value is None:
        return "Not stated"
    return f"{value.day} {value.strftime('%b %Y')}"


def _duration_text(duration_days: int | None) -> str:
    if duration_days is None:
        return "Not stated"
    if duration_days % 7 == 0:
        weeks = duration_days // 7
        return f"{weeks} {'week' if weeks == 1 else 'weeks'}"
    return f"{duration_days} {'day' if duration_days == 1 else 'days'}"


def _pets_text(listing: ListingRecord) -> str:
    if listing.no_pets:
        return "No pets"
    animals = [
        f"{count} {singular if count == 1 else plural}"
        for field, singular, plural in ANIMAL_LABELS
        if (count := getattr(listing, field)) > 0
    ]
    return ", ".join(animals) if animals else "Not stated"
