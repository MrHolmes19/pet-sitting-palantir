"""HTTP client and pagination for KiwiHouseSitters."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from re import sub
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pet_sitting_palantir.kiwihousesitters.constants import (
    BASE_URL,
    DEFAULT_REQUEST_HEADERS,
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


class KiwiHouseSittersHTTPError(requests.HTTPError):
    """HTTP error with sanitized response details useful for production diagnosis."""


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
        self._session.headers.update({**DEFAULT_REQUEST_HEADERS, "User-Agent": user_agent})

    def fetch_html(self, url: str) -> str:
        """Fetch one HTML page and raise for non-success responses."""
        response = self._session.get(url, timeout=self._timeout_seconds)

        return _text_from_ok_response(response)

    def post_html(self, url: str, *, data: Mapping[str, Any]) -> str:
        """POST one HTML form request and raise for non-success responses."""
        response = self._session.post(url, data=data, timeout=self._timeout_seconds)

        return _text_from_ok_response(response)

    def fetch_search_pages(
        self,
        initial_url: str,
        *,
        max_pages: int | None,
        first_page_form_data: Mapping[str, str] | None = None,
        first_page_html: str | None = None,
    ) -> Iterator[PageFetch]:
        """Fetch search result pages by following the site's show-more links."""
        page_number = 1
        next_url: str | None = initial_url

        while next_url and (max_pages is None or page_number <= max_pages):
            if page_number == 1 and first_page_html is not None:
                html = first_page_html
            elif page_number == 1 and first_page_form_data is not None:
                html = self.fetch_first_search_page(
                    next_url,
                    first_page_form_data=first_page_form_data,
                ).html
            else:
                html = self.fetch_html(next_url)
            yield PageFetch(url=next_url, html=html, page_number=page_number)

            soup = BeautifulSoup(html, "html.parser")
            next_link = soup.select_one(NEXT_PAGE_SELECTOR)
            next_href = next_link.get("href") if next_link else None
            next_url = urljoin(BASE_URL, next_href) if next_href else None
            page_number += 1

    def fetch_first_search_page(
        self,
        initial_url: str,
        *,
        first_page_form_data: Mapping[str, str] | None = None,
    ) -> PageFetch:
        """Fetch the first page of a search request."""
        if first_page_form_data is not None:
            self.fetch_html(initial_url)
            html = self.post_html(initial_url, data=first_page_form_data)
        else:
            html = self.fetch_html(initial_url)

        return PageFetch(url=initial_url, html=html, page_number=1)


def _text_from_ok_response(response: requests.Response) -> str:
    if response.status_code != HTTP_OK_STATUS:
        raise KiwiHouseSittersHTTPError(_response_error_message(response))

    return response.text


def _response_error_message(response: requests.Response) -> str:
    return (
        f"Unexpected status code: {response.status_code}; "
        f"url={response.url or 'unknown'}; "
        f"content_type={response.headers.get('content-type', 'unknown')}; "
        f"server={response.headers.get('server', 'unknown')}; "
        f"body_snippet={_body_snippet(response.text)}"
    )


def _body_snippet(text: str, *, max_length: int = 300) -> str:
    collapsed = sub(r"\s+", " ", text).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[:max_length]}..."
