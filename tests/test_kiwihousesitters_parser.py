from datetime import date
from pathlib import Path

from pet_sitting_palantir.kiwihousesitters.parser import parse_search_page

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def test_parse_search_page_extracts_listing_fields() -> None:
    listings = parse_search_page(_fixture("search_listing_auckland_central.html"))

    assert len(listings) == 1
    listing = listings[0]
    assert listing.external_id == "614587"
    assert listing.island == "North Island"
    assert listing.city == "Stonefields Auckland"
    assert listing.region == "Auckland"
    assert listing.subregion == "Auckland - Central"
    assert listing.start_date == date(2026, 6, 12)
    assert listing.end_date == date(2026, 6, 28)
    assert listing.duration_days == 16
    assert listing.total_animals == 1
    assert listing.dogs_count == 1
    assert listing.cats_count == 0
    assert listing.house_type == "House"
    assert listing.starts_soon is True
    assert listing.reply_rating_score == 10
    assert listing.content_hash is not None
    assert "raw_data" not in listing.to_dict()
    assert "pets_raw" not in listing.to_dict()
    assert "reply_rating_text" not in listing.to_dict()


def test_parse_search_page_handles_leading_separator_location() -> None:
    listing = parse_search_page(_fixture("search_listing_leading_separator.html"))[0]

    assert listing.city == "New Plymouth"
    assert listing.region == "Taranaki"
    assert listing.subregion == "New Plymouth"
