"""KiwiHouseSitters search filter request conversion."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pet_sitting_palantir.kiwihousesitters.constants import SEARCH_URL, SIT_LENGTH_IDS
from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS, STATE_LABELS

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
    sitlengths = _optional_string(site_filter, "sitlengths")

    if state:
        _validate_state(state)
        form_data["state"] = state
    if region:
        region_filter = _region_filter(region)
        if state and region_filter.state != state:
            raise ValueError(f"KiwiHouseSitters region {region} does not belong to {state}")
        form_data["region"] = region_filter.site_id
    if subregion:
        if not region:
            raise ValueError("subregion filters require a region")
        form_data["subregion"] = _site_subregion_id(region, subregion)
    if sitlengths:
        _validate_sitlengths(sitlengths)
        form_data["sitlengths"] = sitlengths

    return form_data


def _optional_string(site_filter: Mapping[str, Any], key: str) -> str | None:
    value = site_filter.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"site_filter.{key} must be a string")
    return value


def _validate_state(state: str) -> None:
    if state not in STATE_LABELS:
        raise ValueError(f"Unsupported KiwiHouseSitters state filter: {state}")


def _region_filter(region: str):
    try:
        return REGION_FILTERS[region]
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters region filter: {region}") from error


def _site_subregion_id(region: str, subregion: str) -> str:
    region_filter = _region_filter(region)
    try:
        return region_filter.subregions[subregion].site_id
    except KeyError as error:
        raise ValueError(
            f"Unsupported KiwiHouseSitters subregion filter: {region}/{subregion}"
        ) from error


def _validate_sitlengths(sitlengths: str) -> None:
    if sitlengths not in SIT_LENGTH_IDS:
        raise ValueError(f"Unsupported KiwiHouseSitters sitlengths filter: {sitlengths}")
