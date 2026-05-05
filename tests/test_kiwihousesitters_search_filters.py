import pytest

from pet_sitting_palantir.kiwihousesitters.constants import SEARCH_URL
from pet_sitting_palantir.kiwihousesitters.search_filters import (
    build_search_request,
    search_form_data_from_site_filter,
)


def test_unfiltered_scope_uses_get_search_request() -> None:
    request = build_search_request({})

    assert request.url == SEARCH_URL
    assert request.method == "GET"
    assert request.form_data is None


def test_auckland_central_scope_uses_post_form_site_ids() -> None:
    request = build_search_request(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        }
    )

    assert request.url == SEARCH_URL
    assert request.method == "POST"
    assert request.form_data is not None
    assert request.form_data["view"] == "list"
    assert request.form_data["order"] == "newentries"
    assert request.form_data["state"] == "north-island"
    assert request.form_data["region"] == "33"
    assert request.form_data["subregion"] == "178"


def test_north_shore_city_scope_uses_discovered_subregion_id() -> None:
    form_data = search_form_data_from_site_filter(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "north-shore-city",
        }
    )

    assert form_data["state"] == "north-island"
    assert form_data["region"] == "33"
    assert form_data["subregion"] == "181"


def test_south_island_region_and_subregion_use_discovered_ids() -> None:
    form_data = search_form_data_from_site_filter(
        {
            "state": "south-island",
            "region": "canterbury",
            "subregion": "christchurch",
        }
    )

    assert form_data["state"] == "south-island"
    assert form_data["region"] == "41"
    assert form_data["subregion"] == "544"


def test_north_island_scope_uses_state_without_region_ids() -> None:
    form_data = search_form_data_from_site_filter({"state": "north-island"})

    assert form_data["state"] == "north-island"
    assert form_data["region"] == ""
    assert form_data["subregion"] == ""


def test_unsupported_region_fails_before_scraping() -> None:
    with pytest.raises(ValueError, match="Unsupported KiwiHouseSitters region"):
        search_form_data_from_site_filter({"region": "not-mapped"})


def test_region_must_belong_to_state() -> None:
    with pytest.raises(ValueError, match="does not belong"):
        search_form_data_from_site_filter({"state": "south-island", "region": "auckland"})


def test_unsupported_state_fails_before_scraping() -> None:
    with pytest.raises(ValueError, match="Unsupported KiwiHouseSitters state"):
        search_form_data_from_site_filter({"state": "not-mapped"})


def test_subregion_requires_region() -> None:
    with pytest.raises(ValueError, match="subregion filters require a region"):
        search_form_data_from_site_filter({"subregion": "auckland-central"})
