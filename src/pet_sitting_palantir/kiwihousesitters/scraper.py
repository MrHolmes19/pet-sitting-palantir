"""High-level scraper orchestration for KiwiHouseSitters."""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.client import (
    KiwiHouseSittersClient,
    KiwiHouseSittersHTTPError,
    PageFetch,
)
from pet_sitting_palantir.kiwihousesitters.constants import (
    DEFAULT_MAX_PAGES,
    SEARCH_RESULT_CAP,
    SIT_LENGTH_IDS,
)
from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS
from pet_sitting_palantir.kiwihousesitters.parser import (
    parse_estimated_result_count,
    parse_search_page,
    search_page_has_cap_notice,
)
from pet_sitting_palantir.kiwihousesitters.search_filters import build_search_request


@dataclass(frozen=True)
class ScrapeResult:
    """Listings and fetch metadata from one scraper invocation."""

    search_url: str
    pages_fetched: int
    listings: tuple[Listing, ...]


@dataclass(frozen=True)
class LeafSearch:
    """A concrete search that is safe to paginate."""

    site_filter: Mapping[str, Any]
    first_page: PageFetch


def scrape_scope(
    site_filter: Mapping[str, Any] | None = None,
    *,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    client: KiwiHouseSittersClient | None = None,
) -> ScrapeResult:
    """Scrape a KiwiHouseSitters search scope."""
    scraper_client = client or KiwiHouseSittersClient()
    root_filter = dict(site_filter or {})
    search_request = build_search_request(root_filter)
    listings_by_external_id: dict[str, Listing] = {}
    pages_fetched = 0

    for leaf in _leaf_searches(root_filter, scraper_client):
        pages_fetched += _collect_leaf_listings(
            leaf,
            client=scraper_client,
            max_pages=max_pages,
            listings_by_external_id=listings_by_external_id,
        )

    return ScrapeResult(
        search_url=search_request.url,
        pages_fetched=pages_fetched,
        listings=tuple(listings_by_external_id.values()),
    )


def _collect_leaf_listings(
    leaf: LeafSearch,
    *,
    client: KiwiHouseSittersClient,
    max_pages: int | None,
    listings_by_external_id: dict[str, Listing],
) -> int:
    leaf_request = build_search_request(leaf.site_filter)
    leaf_listings: dict[str, Listing] = {}
    pages_fetched = 0

    try:
        for page in client.fetch_search_pages(
            leaf_request.url,
            max_pages=max_pages,
            first_page_form_data=leaf_request.form_data,
            first_page_html=leaf.first_page.html,
        ):
            pages_fetched += 1
            if search_page_has_cap_notice(page.html):
                for child_filter in _child_site_filters(leaf.site_filter):
                    for child_leaf in _leaf_searches(child_filter, client):
                        pages_fetched += _collect_leaf_listings(
                            child_leaf,
                            client=client,
                            max_pages=max_pages,
                            listings_by_external_id=listings_by_external_id,
                        )
                return pages_fetched

            for listing in parse_search_page(page.html):
                leaf_listings[listing.external_id] = listing
    except KiwiHouseSittersHTTPError as error:
        raise _http_error_with_search_context(
            error,
            site_filter=leaf.site_filter,
            phase="pagination",
        ) from error

    listings_by_external_id.update(leaf_listings)
    return pages_fetched


def _leaf_searches(
    site_filter: Mapping[str, Any],
    client: KiwiHouseSittersClient,
) -> Iterator[LeafSearch]:
    normalized_filter = dict(site_filter)

    if "state" not in normalized_filter:
        for child_filter in (
            {**normalized_filter, "state": "north-island"},
            {**normalized_filter, "state": "south-island"},
        ):
            yield from _leaf_searches(child_filter, client)
        return

    first_page = _fetch_first_page(normalized_filter, client)
    if _is_safe_to_paginate(normalized_filter, first_page.html):
        yield LeafSearch(site_filter=normalized_filter, first_page=first_page)
        return

    for child_filter in _child_site_filters(normalized_filter):
        yield from _leaf_searches(child_filter, client)


def _fetch_first_page(
    site_filter: Mapping[str, Any],
    client: KiwiHouseSittersClient,
) -> PageFetch:
    request = build_search_request(site_filter)
    try:
        return client.fetch_first_search_page(
            request.url,
            first_page_form_data=request.form_data,
        )
    except KiwiHouseSittersHTTPError as error:
        raise _http_error_with_search_context(
            error,
            site_filter=site_filter,
            phase="first_page",
        ) from error


def _is_safe_to_paginate(site_filter: Mapping[str, Any], html: str) -> bool:
    if search_page_has_cap_notice(html):
        return False

    if "sitlengths" in site_filter:
        return True

    estimated_count = parse_estimated_result_count(html)
    if estimated_count is not None:
        return estimated_count <= SEARCH_RESULT_CAP

    return True


def _child_site_filters(site_filter: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if "region" not in site_filter:
        state = _required_string(site_filter, "state")
        return tuple(_region_child_filters(state))

    if "subregion" not in site_filter:
        region = _required_string(site_filter, "region")
        return tuple(_subregion_child_filters(site_filter, region))

    if "sitlengths" not in site_filter:
        return tuple(_sitlength_child_filters(site_filter))

    raise RuntimeError(f"KiwiHouseSitters search is still over the cap: {dict(site_filter)}")


def _region_child_filters(state: str) -> Iterable[dict[str, Any]]:
    for region_slug, region_filter in REGION_FILTERS.items():
        if region_filter.state == state:
            yield {
                "state": state,
                "region": region_slug,
            }


def _subregion_child_filters(
    site_filter: Mapping[str, Any],
    region: str,
) -> Iterable[dict[str, Any]]:
    region_filter = REGION_FILTERS[region]
    for subregion_slug in region_filter.subregions:
        yield {
            "state": site_filter["state"],
            "region": region,
            "subregion": subregion_slug,
        }


def _sitlength_child_filters(site_filter: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for sitlengths in SIT_LENGTH_IDS:
        yield {
            **site_filter,
            "sitlengths": sitlengths,
        }


def _required_string(site_filter: Mapping[str, Any], key: str) -> str:
    value = site_filter.get(key)
    if not isinstance(value, str):
        raise TypeError(f"site_filter.{key} must be a string")
    return value


def _http_error_with_search_context(
    error: KiwiHouseSittersHTTPError,
    *,
    site_filter: Mapping[str, Any],
    phase: str,
) -> KiwiHouseSittersHTTPError:
    return KiwiHouseSittersHTTPError(
        f"{error}; phase={phase}; site_filter={dict(site_filter)}"
    )
