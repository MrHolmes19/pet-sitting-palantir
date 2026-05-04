"""Conversions from scraped domain objects to persisted records."""

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.storage.models import ListingRecord


def listing_record_from_scraped_listing(listing: Listing) -> ListingRecord:
    """Convert a normalized scraped listing into the persisted listing shape."""
    if not listing.content_hash:
        raise ValueError(f"Listing {listing.external_id} cannot be persisted without content_hash")
    if not listing.url:
        raise ValueError(f"Listing {listing.external_id} cannot be persisted without url")

    return ListingRecord(
        external_id=listing.external_id,
        content_hash=listing.content_hash,
        island=listing.island,
        region=listing.region,
        subregion=listing.subregion,
        city=listing.city,
        duration_days=listing.duration_days,
        start_date=listing.start_date,
        end_date=listing.end_date,
        house_type=listing.house_type,
        total_animals=listing.total_animals,
        dogs_count=listing.dogs_count,
        cats_count=listing.cats_count,
        fish_count=listing.fish_count,
        birds_count=listing.birds_count,
        rabbits_guinea_pigs_count=listing.rabbits_guinea_pigs_count,
        chickens_ducks_geese_count=listing.chickens_ducks_geese_count,
        farm_animals_count=listing.farm_animals_count,
        horses_count=listing.horses_count,
        reptiles_count=listing.reptiles_count,
        other_pets_count=listing.other_pets_count,
        no_pets=listing.no_pets,
        starts_soon=listing.starts_soon,
        reply_rating_score=listing.reply_rating_score,
        listing_tag=listing.listing_tag,
        title=listing.title,
        intro=listing.intro,
        url=listing.url,
    )
