import pytest
import requests

from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        text: str = "",
        url: str = "https://example.test/search",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses: FakeResponse | list[FakeResponse]) -> None:
        self.responses = responses if isinstance(responses, list) else [responses]
        self.requested_urls: list[str] = []
        self.requested_headers: list[dict[str, str] | None] = []
        self.posted_requests: list[tuple[str, object]] = []
        self.headers: dict[str, str] = {}

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int,
    ) -> FakeResponse:
        self.requested_urls.append(url)
        self.requested_headers.append(headers)
        return self.responses.pop(0)

    def post(self, url: str, *, data: object, timeout: int) -> FakeResponse:
        self.posted_requests.append((url, data))
        return self.responses.pop(0)


def test_fetch_html_rejects_non_ok_status() -> None:
    client = KiwiHouseSittersClient(request_interval_seconds=0)
    client._session = FakeSession(FakeResponse(status_code=204))

    with pytest.raises(requests.HTTPError, match="Unexpected status code: 204"):
        client.fetch_html("https://example.test/search")


def test_client_uses_browser_like_default_headers() -> None:
    client = KiwiHouseSittersClient(user_agent="custom-agent", request_interval_seconds=0)

    assert client._session.headers["User-Agent"] == "custom-agent"
    assert client._session.headers["Accept"].startswith("text/html")
    assert client._session.headers["Accept-Language"] == "en-NZ,en;q=0.9"
    assert client._session.headers["Referer"] == "https://www.kiwihousesitters.co.nz"
    assert client._session.headers["Upgrade-Insecure-Requests"] == "1"


def test_client_rejects_negative_request_interval() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        KiwiHouseSittersClient(request_interval_seconds=-1)


def test_filtered_first_page_spaces_get_and_post_requests() -> None:
    times = iter((100.0, 100.2, 101.0))
    sleep_delays: list[float] = []
    fake_session = FakeSession(
        [FakeResponse(status_code=200), FakeResponse(status_code=200)]
    )
    client = KiwiHouseSittersClient(
        request_interval_seconds=1.0,
        clock=lambda: next(times),
        sleep_for=sleep_delays.append,
        session_factory=lambda: fake_session,
    )

    client.fetch_first_search_page(
        "https://example.test/search",
        first_page_form_data={"state": "north-island"},
    )

    assert sleep_delays == [pytest.approx(0.8)]


def test_filtered_first_pages_bootstrap_each_new_server_side_search() -> None:
    sessions: list[FakeSession] = []

    def session_factory() -> FakeSession:
        session = FakeSession(
            [
                FakeResponse(status_code=200),
                FakeResponse(status_code=200),
            ]
        )
        sessions.append(session)
        return session

    client = KiwiHouseSittersClient(request_interval_seconds=0, session_factory=session_factory)

    client.fetch_first_search_page(
        "https://example.test/search",
        first_page_form_data={"state": "north-island"},
    )
    client.fetch_first_search_page(
        "https://example.test/search",
        first_page_form_data={"state": "south-island"},
    )

    assert len(sessions) == 3
    assert sessions[1].requested_urls == ["https://example.test/search"]
    assert sessions[1].posted_requests == [
        ("https://example.test/search", {"state": "north-island"})
    ]
    assert sessions[2].requested_urls == ["https://example.test/search"]
    assert sessions[2].posted_requests == [
        ("https://example.test/search", {"state": "south-island"})
    ]


def test_fetch_html_error_includes_sanitized_response_details() -> None:
    client = KiwiHouseSittersClient(request_interval_seconds=0)
    client._session = FakeSession(
        FakeResponse(
            status_code=403,
            text="""
            <html>
              <head><title>Forbidden</title></head>
              <body>Request blocked by security rules.</body>
            </html>
            """,
            url="https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
            headers={"content-type": "text/html", "server": "cloudflare"},
        )
    )

    with pytest.raises(requests.HTTPError) as error:
        client.fetch_html("https://example.test/search")

    message = str(error.value)
    assert "Unexpected status code: 403" in message
    assert "method=GET" in message
    assert "request_number=1" in message
    assert "url=https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search" in message
    assert "content_type=text/html" in message
    assert "server=cloudflare" in message
    assert "body_snippet=<html> <head><title>Forbidden</title></head>" in message


def test_fetch_search_pages_ignores_showmore_without_href() -> None:
    html = """
    <div id="showmore1">
      <a>Show more listings</a>
    </div>
    """
    client = KiwiHouseSittersClient(request_interval_seconds=0)
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
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        session_factory=lambda: fake_session,
    )

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
    assert fake_session.requested_headers == [
        None,
        {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
        },
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
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        session_factory=lambda: fake_session,
    )

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
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        session_factory=lambda: fake_session,
    )

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
    assert fake_session.requested_headers == [
        None,
        {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.kiwihousesitters.co.nz/house-sitting-pet-sitting-jobs/search",
        },
    ]
