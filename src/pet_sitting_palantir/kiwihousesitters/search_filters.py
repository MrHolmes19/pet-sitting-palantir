"""KiwiHouseSitters search filter request conversion."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pet_sitting_palantir.kiwihousesitters.constants import SEARCH_URL

SearchMethod = Literal["GET", "POST"]

DEFAULT_SEARCH_FORM = {
    "view": "list",
    "order": "newentries",
    "newentries": "0",
    "searchradius": "50",
    "latitude": "",
    "longitude": "",
    "stategroup": "",
    "state": "",
    "region": "",
    "subregion": "",
    "housetype": "",
    "features": "",
    "sitlengths": "",
    "petcares": "",
    "locationname": "",
    "dates": "",
}

REGION_SLUG_TO_SITE_ID = {
    "auckland": "33",
}

SUBREGION_SLUG_TO_SITE_ID = {
    ("auckland", "auckland-central"): "178",
}


@dataclass(frozen=True)
class SearchRequest:
    """HTTP request details for the first page of a search scope."""

    url: str
    method: SearchMethod
    form_data: Mapping[str, str] | None = None


def build_search_request(site_filter: Mapping[str, Any] | None = None) -> SearchRequest:
    """Build the first search request for a stored site_filter."""
    if not site_filter:
        return SearchRequest(url=SEARCH_URL, method="GET")

    return SearchRequest(
        url=SEARCH_URL,
        method="POST",
        form_data=search_form_data_from_site_filter(site_filter),
    )


def search_form_data_from_site_filter(site_filter: Mapping[str, Any]) -> dict[str, str]:
    """Translate stored readable filter slugs to the site's POST form fields."""
    form_data = dict(DEFAULT_SEARCH_FORM)

    state = _optional_string(site_filter, "state")
    region = _optional_string(site_filter, "region")
    subregion = _optional_string(site_filter, "subregion")

    if state:
        form_data["state"] = state
    if region:
        form_data["region"] = _site_region_id(region)
    if subregion:
        if not region:
            raise ValueError("subregion filters require a region")
        form_data["subregion"] = _site_subregion_id(region, subregion)

    return form_data


def _optional_string(site_filter: Mapping[str, Any], key: str) -> str | None:
    value = site_filter.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"site_filter.{key} must be a string")
    return value


def _site_region_id(region: str) -> str:
    try:
        return REGION_SLUG_TO_SITE_ID[region]
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters region filter: {region}") from error


def _site_subregion_id(region: str, subregion: str) -> str:
    try:
        return SUBREGION_SLUG_TO_SITE_ID[(region, subregion)]
    except KeyError as error:
        raise ValueError(
            f"Unsupported KiwiHouseSitters subregion filter: {region}/{subregion}"
        ) from error
