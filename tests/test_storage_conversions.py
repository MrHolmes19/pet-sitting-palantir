from datetime import date

import pytest

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.storage import listing_record_from_scraped_listing


def test_converts_scraped_listing_to_persisted_record() -> None:
    record = listing_record_from_scraped_listing(_listing())

    assert record.external_id == "614587"
    assert record.content_hash == "hash-v1"
    assert record.region == "Auckland"
    assert record.subregion == "Auckland - Central"
    assert record.starts_soon is True
    assert record.url == "https://example.test/listing/614587"
    assert not hasattr(record, "raw_data")
    assert not hasattr(record, "reply_rating_text")
    assert not hasattr(record, "pets_raw")


def test_converted_listing_requires_content_hash() -> None:
    with pytest.raises(ValueError, match="content_hash"):
        listing_record_from_scraped_listing(_listing(content_hash=""))


def test_converted_listing_requires_url() -> None:
    with pytest.raises(ValueError, match="url"):
        listing_record_from_scraped_listing(_listing(url=None))


def _listing(
    *,
    content_hash: str = "hash-v1",
    url: str | None = "https://example.test/listing/614587",
) -> Listing:
    return Listing(
        external_id="614587",
        content_hash=content_hash,
        island="North Island",
        region="Auckland",
        subregion="Auckland - Central",
        city="Stonefields",
        duration_days=6,
        start_date=date(2026, 5, 5),
        end_date=date(2026, 5, 11),
        house_type="Duplex",
        total_animals=1,
        dogs_count=1,
        starts_soon=True,
        reply_rating_score=10,
        listing_tag="Goofy Dog in Stonefields",
        title="Stonefields Auckland - Auckland - Auckland - Central",
        intro="Looking for someone to look after one dog.",
        url=url,
    )
