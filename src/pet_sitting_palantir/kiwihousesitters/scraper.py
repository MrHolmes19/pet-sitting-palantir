"""High-level scraper orchestration for KiwiHouseSitters."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient
from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.kiwihousesitters.parser import parse_search_page
from pet_sitting_palantir.kiwihousesitters.urls import build_search_url


@dataclass(frozen=True)
class ScrapeResult:
    """Listings and fetch metadata from one scraper invocation."""

    search_url: str
    pages_fetched: int
    listings: tuple[Listing, ...]


def scrape_scope(
    site_filter: Mapping[str, Any] | None = None,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    client: KiwiHouseSittersClient | None = None,
) -> ScrapeResult:
    """Scrape a KiwiHouseSitters search scope."""
    search_url = build_search_url(site_filter)
    scraper_client = client or KiwiHouseSittersClient()
    listings: list[Listing] = []
    pages_fetched = 0

    for page in scraper_client.fetch_search_pages(search_url, max_pages=max_pages):
        pages_fetched += 1
        listings.extend(parse_search_page(page.html))

    return ScrapeResult(
        search_url=search_url,
        pages_fetched=pages_fetched,
        listings=tuple(listings),
    )
