import pytest
import requests

from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient


class FakeResponse:
    def __init__(self, *, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.headers: dict[str, str] = {}

    def get(self, url: str, *, timeout: int) -> FakeResponse:
        return self.response


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
