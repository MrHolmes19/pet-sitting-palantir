import pytest

from pet_sitting_palantir.kiwihousesitters.client import PageFetch
from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS
from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult


def test_scrape_result_listings_are_immutable_sequence() -> None:
    result = ScrapeResult(
        search_url="https://example.test/search",
        pages_fetched=0,
        listings=(),
    )

    assert result.listings == ()


def test_scrape_scope_uses_post_form_data_for_filtered_scope() -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    class FakeClient:
        def __init__(self) -> None:
            self.first_page_calls = []
            self.paginated_calls = []

        def fetch_first_search_page(self, initial_url, *, first_page_form_data=None):
            self.first_page_calls.append((initial_url, first_page_form_data))
            return PageFetch(url=initial_url, html=_count_page(1), page_number=1)

        def fetch_search_pages(
            self,
            initial_url,
            *,
            max_pages,
            first_page_form_data=None,
            first_page_html=None,
        ):
            self.paginated_calls.append(
                (initial_url, max_pages, first_page_form_data, first_page_html)
            )
            return ()

    client = FakeClient()

    result = scrape_scope(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        },
        max_pages=1,
        client=client,
    )

    assert result.pages_fetched == 0
    expected_form_data = {
        "view": "list",
        "order": "newentries",
        "newentries": "0",
        "searchradius": "50",
        "latitude": "",
        "longitude": "",
        "stategroup": "",
        "state": "north-island",
        "region": "33",
        "subregion": "178",
        "housetype": "",
        "features": "",
        "sitlengths": "",
        "petcares": "",
        "locationname": "",
        "dates": "",
    }
    assert client.first_page_calls == [
        (
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            expected_form_data,
        )
    ]
    assert client.paginated_calls == [
        (
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            1,
            expected_form_data,
            _count_page(1),
        )
    ]


def test_scrape_scope_expands_all_nz_into_islands_without_fetching_unfiltered_search() -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    client = PlanningClient(default_html=_count_page(1))

    result = scrape_scope({}, max_pages=None, client=client)

    assert result.pages_fetched == 2
    assert result.listings == ()
    assert client.first_page_form_data == [
        {"state": "north-island", "region": "", "subregion": "", "sitlengths": ""},
        {"state": "south-island", "region": "", "subregion": "", "sitlengths": ""},
    ]
    assert None not in client.first_page_form_data


def test_scrape_scope_splits_over_cap_state_into_region_searches() -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    north_region_ids = [
        region.site_id for region in REGION_FILTERS.values() if region.state == "north-island"
    ]
    client = PlanningClient(
        default_html=_count_page(1),
        html_by_form_key={
            ("north-island", "", "", ""): _count_page(201),
        },
    )

    result = scrape_scope({"state": "north-island"}, max_pages=None, client=client)

    assert result.pages_fetched == len(north_region_ids)
    assert [form_data["region"] for form_data in client.paginated_form_data] == north_region_ids
    assert {"state": "north-island", "region": "", "subregion": "", "sitlengths": ""} not in (
        client.paginated_form_data
    )


def test_scrape_scope_splits_over_cap_subregion_by_sit_length() -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    over_cap_form = ("north-island", "33", "178", "")
    client = PlanningClient(
        default_html=_count_page(1),
        html_by_form_key={over_cap_form: _count_page(201)},
    )

    result = scrape_scope(
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        },
        max_pages=None,
        client=client,
    )

    assert result.pages_fetched == 5
    assert [form_data["sitlengths"] for form_data in client.paginated_form_data] == [
        "60",
        "61",
        "62",
        "63",
        "64",
    ]


def test_scrape_scope_raises_when_leaf_search_still_shows_cap_notice() -> None:
    from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope

    client = PlanningClient(default_html=_count_page(1, capped=True))

    with pytest.raises(RuntimeError, match="still over the cap"):
        scrape_scope(
            {
                "state": "north-island",
                "region": "auckland",
                "subregion": "auckland-central",
                "sitlengths": "60",
            },
            max_pages=None,
            client=client,
        )


class PlanningClient:
    def __init__(
        self,
        *,
        default_html: str,
        html_by_form_key: dict[tuple[str, str, str, str], str] | None = None,
    ) -> None:
        self.default_html = default_html
        self.html_by_form_key = html_by_form_key or {}
        self.first_page_form_data: list[dict[str, str]] = []
        self.paginated_form_data: list[dict[str, str]] = []

    def fetch_first_search_page(self, initial_url, *, first_page_form_data=None):
        assert first_page_form_data is not None
        form_data = dict(first_page_form_data)
        self.first_page_form_data.append(_summary_form_data(form_data))
        return PageFetch(
            url=initial_url,
            html=self.html_by_form_key.get(_form_key(form_data), self.default_html),
            page_number=1,
        )

    def fetch_search_pages(
        self,
        initial_url,
        *,
        max_pages,
        first_page_form_data=None,
        first_page_html=None,
    ):
        assert first_page_form_data is not None
        assert first_page_html is not None
        self.paginated_form_data.append(_summary_form_data(dict(first_page_form_data)))
        yield PageFetch(url=initial_url, html=first_page_html, page_number=1)


def _summary_form_data(form_data: dict[str, str]) -> dict[str, str]:
    return {
        "state": form_data["state"],
        "region": form_data["region"],
        "subregion": form_data["subregion"],
        "sitlengths": form_data["sitlengths"],
    }


def _form_key(form_data: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        form_data["state"],
        form_data["region"],
        form_data["subregion"],
        form_data["sitlengths"],
    )


def _count_page(count: int, *, capped: bool = False) -> str:
    cap_notice = "<h3>And there's more...</h3>" if capped else ""
    return f"""
    <html>
      <body>
        <li id="sit-length-options" class="check-list" style="display:none;">
          <div data-featureid="60" class="feature-filter">
            <a href="/house-sitting-pet-sitting-jobs/search?display=list&sitlengths=60">
              <span class="label">0 - 1 week ({count})</span>
            </a>
          </div>
        </li>
        {cap_notice}
      </body>
    </html>
    """
