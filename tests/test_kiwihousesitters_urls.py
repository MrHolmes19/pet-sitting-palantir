from pet_sitting_palantir.kiwihousesitters.urls import build_search_url


def test_build_search_url_uses_site_filter_query_params() -> None:
    url = build_search_url(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        }
    )

    assert url.endswith("?state=north-island&region=auckland&subregion=auckland-central")
