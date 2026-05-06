import pytest
import requests

from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient


class FakeResponse:
    def __init__(self, *, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses: FakeResponse | list[FakeResponse]) -> None:
        self.responses = responses if isinstance(responses, list) else [responses]
        self.requested_urls: list[str] = []
        self.posted_requests: list[tuple[str, object]] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, *, timeout: int) -> FakeResponse:
        self.requested_urls.append(url)
        return self.responses.pop(0)

    def post(self, url: str, *, data: object, timeout: int) -> FakeResponse:
        self.posted_requests.append((url, data))
        return self.responses.pop(0)


def test_fetch_html_rejects_non_ok_status() -> None:
    client = KiwiHouseSittersClient()
    client._session = FakeSession(FakeResponse(status_code=204))

    with pytest.raises(requests.HTTPError, match="Unexpected status code: 204"):
        client.fetch_html("https://example.test/search")


def test_fetch_search_pages_ignores_showmore_without_href() -> None:
    html = """
    <div id="showmore1">
      <a>Show more listings</a>
    </div>
    """
    client = KiwiHouseSittersClient()
    client._session = FakeSession(FakeResponse(status_code=200, text=html))

    pages = tuple(client.fetch_search_pages("https://example.test/search", max_pages=3))

    assert len(pages) == 1
    assert pages[0].html == html


def test_fetch_search_pages_follows_showmore_link_and_stops() -> None:
    page_one_html = """
    <div id="showmore1">
      <a href="/house-sitting-pet-sitting-jobs/search?searchid=test&amp;page=2">
        Show more listings
      </a>
    </div>
    """
    page_two_html = "<div class='search-list-results'></div>"
    fake_session = FakeSession(
        [
            FakeResponse(status_code=200, text=page_one_html),
            FakeResponse(status_code=200, text=page_two_html),
        ]
    )
    client = KiwiHouseSittersClient()
    client._session = fake_session

    pages = tuple(
        client.fetch_search_pages(
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            max_pages=3,
        )
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert [page.html for page in pages] == [page_one_html, page_two_html]
    assert fake_session.requested_urls == [
        "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
        "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search?searchid=test&page=2",
    ]


def test_fetch_search_pages_without_page_limit_stops_when_showmore_ends() -> None:
    page_one_html = """
    <div id="showmore1">
      <a href="/house-sitting-pet-sitting-jobs/search?searchid=test&amp;page=2">
        Show more listings
      </a>
    </div>
    """
    page_two_html = "<div class='search-list-results'></div>"
    fake_session = FakeSession(
        [
            FakeResponse(status_code=200, text=page_one_html),
            FakeResponse(status_code=200, text=page_two_html),
        ]
    )
    client = KiwiHouseSittersClient()
    client._session = fake_session

    pages = tuple(
        client.fetch_search_pages(
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            max_pages=None,
        )
    )

    assert [page.page_number for page in pages] == [1, 2]


def test_fetch_search_pages_posts_filtered_first_page_then_follows_showmore() -> None:
    initial_html = "<html></html>"
    filtered_page_html = """
    <div id="showmore1">
      <a href="/house-sitting-pet-sitting-jobs/search?searchid=test&amp;page=2">
        Show more listings
      </a>
    </div>
    """
    page_two_html = "<div class='search-list-results'></div>"
    fake_session = FakeSession(
        [
            FakeResponse(status_code=200, text=initial_html),
            FakeResponse(status_code=200, text=filtered_page_html),
            FakeResponse(status_code=200, text=page_two_html),
        ]
    )
    client = KiwiHouseSittersClient()
    client._session = fake_session

    pages = tuple(
        client.fetch_search_pages(
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            max_pages=2,
            first_page_form_data={"state": "north-island", "region": "33"},
        )
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert [page.html for page in pages] == [filtered_page_html, page_two_html]
    assert fake_session.requested_urls == [
        "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
        "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search?searchid=test&page=2",
    ]
    assert fake_session.posted_requests == [
        (
            "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            {"state": "north-island", "region": "33"},
        )
    ]
