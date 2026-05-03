"""HTTP client and pagination for KiwiHouseSitters."""

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pet_sitting_palantir.kiwihousesitters.constants import (
    BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    HTTP_OK_STATUS,
    NEXT_PAGE_SELECTOR,
)


@dataclass(frozen=True)
class PageFetch:
    """A fetched search result page."""

    url: str
    html: str
    page_number: int


class KiwiHouseSittersClient:
    """Small HTTP client wrapper for KiwiHouseSitters."""

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch_html(self, url: str) -> str:
        """Fetch one HTML page and raise for non-success responses."""
        response = self._session.get(url, timeout=self._timeout_seconds)

        if response.status_code != HTTP_OK_STATUS:
            raise requests.HTTPError(f"Unexpected status code: {response.status_code}")

        return response.text

    def fetch_search_pages(self, initial_url: str, *, max_pages: int) -> Iterator[PageFetch]:
        """Fetch search result pages by following the site's show-more links."""
        page_number = 1
        next_url: str | None = initial_url

        while next_url and page_number <= max_pages:
            html = self.fetch_html(next_url)
            yield PageFetch(url=next_url, html=html, page_number=page_number)

            soup = BeautifulSoup(html, "html.parser")
            next_link = soup.select_one(NEXT_PAGE_SELECTOR)
            next_href = next_link.get("href") if next_link else None
            next_url = urljoin(BASE_URL, next_href) if next_href else None
            page_number += 1
