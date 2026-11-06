import pytest
import requests
from curl_cffi import requests as browser_requests

from pet_sitting_palantir.kiwihousesitters.client import (
    KiwiHouseSittersClient,
    KiwiHouseSittersDeadlineExceeded,
    KiwiHouseSittersWAFChallengeError,
)


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
    def __init__(
        self,
        responses: FakeResponse
        | requests.RequestException
        | browser_requests.exceptions.RequestException
        | list[
            FakeResponse | requests.RequestException | browser_requests.exceptions.RequestException
        ],
    ) -> None:
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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url: str, *, data: object, timeout: int) -> FakeResponse:
        self.posted_requests.append((url, data))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_html_rejects_non_ok_status() -> None:
    client = KiwiHouseSittersClient(request_interval_seconds=0)
    client._session = FakeSession(FakeResponse(status_code=204))

    with pytest.raises(requests.HTTPError, match="Unexpected status code: 204"):
        client.fetch_html("https://example.test/search")


def test_client_uses_consistent_browser_profile(monkeypatch) -> None:
    options = {}
    fake_session = FakeSession(FakeResponse(status_code=200))

    def session_factory(**kwargs):
        options.update(kwargs)
        return fake_session

    monkeypatch.setattr(browser_requests, "Session", session_factory)
    KiwiHouseSittersClient(request_interval_seconds=0)

    assert options == {"impersonate": "chrome"}
    assert fake_session.headers == {}


def test_client_supports_explicit_user_agent_override() -> None:
    client = KiwiHouseSittersClient(user_agent="custom-agent", request_interval_seconds=0)

    assert client._session.headers["User-Agent"] == "custom-agent"


def test_client_rejects_negative_request_interval() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        KiwiHouseSittersClient(request_interval_seconds=-1)


def test_client_deadline_stops_background_request_before_it_starts() -> None:
    fake_session = FakeSession(FakeResponse(status_code=200))
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        deadline=10,
        clock=lambda: 10,
        session_factory=lambda: fake_session,
    )

    with pytest.raises(KiwiHouseSittersDeadlineExceeded):
        client.fetch_html("https://example.test/search")

    assert fake_session.requested_urls == []


def test_client_retries_transient_statuses_with_exponential_backoff() -> None:
    sleep_delays: list[float] = []
    fake_session = FakeSession(
        [
            FakeResponse(status_code=503),
            FakeResponse(status_code=503),
            FakeResponse(status_code=200, text="recovered"),
        ]
    )
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        transient_retry_attempts=2,
        transient_retry_backoff_seconds=5,
        sleep_for=sleep_delays.append,
        session_factory=lambda: fake_session,
    )

    assert client.fetch_html("https://example.test/search") == "recovered"
    assert sleep_delays == [5, 10]
    assert fake_session.requested_urls == ["https://example.test/search"] * 3


@pytest.mark.parametrize(
    "error_type",
    [
        requests.Timeout,
        browser_requests.exceptions.Timeout,
        browser_requests.exceptions.ConnectionError,
    ],
)
def test_client_retries_transient_connection_errors(error_type) -> None:
    fake_session = FakeSession(
        [error_type("slow"), FakeResponse(status_code=200, text="recovered")]
    )
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        transient_retry_attempts=1,
        transient_retry_backoff_seconds=0,
        session_factory=lambda: fake_session,
    )

    assert client.fetch_html("https://example.test/search") == "recovered"


def test_client_does_not_immediately_retry_rate_limit_response() -> None:
    fake_session = FakeSession(
        [
            FakeResponse(
                status_code=429,
                headers={"retry-after": "120", "server": "cloudflare"},
            ),
            FakeResponse(status_code=200, text="should not be requested"),
        ]
    )
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        transient_retry_attempts=2,
        session_factory=lambda: fake_session,
    )

    with pytest.raises(requests.HTTPError) as error:
        client.fetch_html("https://example.test/search")

    assert "Unexpected status code: 429" in str(error.value)
    assert "retry_after=120" in str(error.value)
    assert fake_session.requested_urls == ["https://example.test/search"]


def test_client_classifies_aws_waf_challenge_without_retrying() -> None:
    fake_session = FakeSession(
        [
            FakeResponse(
                status_code=202,
                text="<script>window.awsWafCookieDomainList = [];</script>",
                headers={"server": "cloudflare"},
            ),
            FakeResponse(status_code=200, text="should not be requested"),
        ]
    )
    client = KiwiHouseSittersClient(
        request_interval_seconds=0,
        transient_retry_attempts=2,
        session_factory=lambda: fake_session,
    )

    with pytest.raises(KiwiHouseSittersWAFChallengeError) as error:
        client.fetch_html("https://example.test/search")

    assert "kiwihousesitters_waf_challenge" in str(error.value)
    assert "Unexpected status code: 202" in str(error.value)
    assert fake_session.requested_urls == ["https://example.test/search"]


def test_client_classifies_waf_challenge_header_without_body_marker() -> None:
    client = KiwiHouseSittersClient(request_interval_seconds=0)
    client._session = FakeSession(
        FakeResponse(
            status_code=202,
            headers={"x-amzn-waf-action": "challenge"},
        )
    )

    with pytest.raises(KiwiHouseSittersWAFChallengeError):
        client.fetch_html("https://example.test/search")


@pytest.mark.parametrize(
    ("status", "headers", "body"),
    [
        (403, {"cf-mitigated": "challenge"}, "verification"),
        (200, {"cf-mitigated": "challenge"}, "verification"),
        (503, {"cf-mitigated": "challenge"}, "verification"),
        (403, {"server": "cloudflare"}, "<html><title>Just a moment...</title></html>"),
    ],
)
def test_client_classifies_cloudflare_challenge_without_retrying(status, headers, body) -> None:
    session = FakeSession(
        [
            FakeResponse(status_code=status, headers=headers, text=body),
            FakeResponse(status_code=200, text="should not be requested"),
        ]
    )
    client = KiwiHouseSittersClient(request_interval_seconds=0, session_factory=lambda: session)

    with pytest.raises(KiwiHouseSittersWAFChallengeError, match="kiwihousesitters_waf_challenge"):
        client.fetch_html("https://example.test/search")

    assert len(session.requested_urls) == 1


def test_filtered_first_page_spaces_get_and_post_requests() -> None:
    times = iter((100.0, 100.2, 101.0))
    sleep_delays: list[float] = []
    fake_session = FakeSession([FakeResponse(status_code=200), FakeResponse(status_code=200)])
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


def test_filtered_first_page_adds_bounded_request_jitter() -> None:
    times = iter((100.0, 100.2, 101.5))
    sleep_delays: list[float] = []
    fake_session = FakeSession([FakeResponse(status_code=200), FakeResponse(status_code=200)])
    client = KiwiHouseSittersClient(
        request_interval_seconds=1.0,
        request_interval_jitter_seconds=1.5,
        clock=lambda: next(times),
        sleep_for=sleep_delays.append,
        random_between=lambda lower, upper: 0.5,
        session_factory=lambda: fake_session,
    )

    client.fetch_first_search_page(
        "https://example.test/search",
        first_page_form_data={"state": "north-island"},
    )

    assert sleep_delays == [pytest.approx(1.3)]


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
