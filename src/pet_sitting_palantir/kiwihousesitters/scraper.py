"""High-level scraper orchestration for KiwiHouseSitters."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient
from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.kiwihousesitters.parser import parse_search_page
from pet_sitting_palantir.kiwihousesitters.search_filters import build_search_request


@dataclass(frozen=True)
class ScrapeResult:
    """Listings and fetch metadata from one scraper invocation."""

    search_url: str
    pages_fetched: int
    listings: tuple[Listing, ...]


def scrape_scope(
    site_filter: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    client: KiwiHouseSittersClient | None = None,
) -> ScrapeResult:
    """Scrape a KiwiHouseSitters search scope."""
    search_request = build_search_request(site_filter)
    scraper_client = client or KiwiHouseSittersClient()
    listings: list[Listing] = []
    pages_fetched = 0

    for page in scraper_client.fetch_search_pages(
        search_request.url,
        max_pages=max_pages,
        first_page_form_data=search_request.form_data,
    ):
        pages_fetched += 1
        listings.extend(parse_search_page(page.html))

    return ScrapeResult(
        search_url=search_request.url,
        pages_fetched=pages_fetched,
        listings=tuple(listings),
    )
