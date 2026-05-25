"""HTTP client and pagination for KiwiHouseSitters."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from re import sub
from time import monotonic, sleep
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pet_sitting_palantir.kiwihousesitters.constants import (
    BASE_URL,
    DEFAULT_REQUEST_HEADERS,
    DEFAULT_USER_AGENT,
    HTTP_OK_STATUS,
    NEXT_PAGE_SELECTOR,
    PAGINATION_REQUEST_HEADERS,
)
from pet_sitting_palantir.settings import (
    KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS,
    KIWIHOUSESITTERS_TIMEOUT_SECONDS,
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
        timeout_seconds: int = KIWIHOUSESITTERS_TIMEOUT_SECONDS,
        request_interval_seconds: float = KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        clock: Callable[[], float] = monotonic,
        sleep_for: Callable[[float], None] = sleep,
        session_factory: Callable[[], requests.Session] = requests.Session,
    ) -> None:
        _validate_request_interval_seconds(request_interval_seconds)

        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = request_interval_seconds
        self._clock = clock
        self._sleep_for = sleep_for
        self._last_request_started_at: float | None = None
        self._requests_started = 0
        self._user_agent = user_agent
        self._session_factory = session_factory
        self._session = self._new_session()

    def fetch_html(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Fetch one HTML page and raise for non-success responses."""
        self._wait_for_request_slot()
        self._requests_started += 1
        response = self._session.get(
            url,
            headers=headers,
            timeout=self._timeout_seconds,
        )

        return _text_from_ok_response(
            response,
            method="GET",
            request_number=self._requests_started,
        )

    def post_html(self, url: str, *, data: Mapping[str, Any]) -> str:
        """POST one HTML form request and raise for non-success responses."""
        self._wait_for_request_slot()
        self._requests_started += 1
        response = self._session.post(url, data=data, timeout=self._timeout_seconds)

        return _text_from_ok_response(
            response,
            method="POST",
            request_number=self._requests_started,
        )

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
            elif page_number == 1:
                html = self.fetch_html(next_url)
            else:
                html = self.fetch_html(
                    next_url,
                    headers={
                        **PAGINATION_REQUEST_HEADERS,
                        "Referer": initial_url,
                    },
                )
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
        self._session = self._new_session()
        if first_page_form_data is not None:
            self.fetch_html(initial_url)
            html = self.post_html(initial_url, data=first_page_form_data)
        else:
            html = self.fetch_html(initial_url)

        return PageFetch(url=initial_url, html=html, page_number=1)

    def _new_session(self) -> requests.Session:
        session = self._session_factory()
        session.headers.update({**DEFAULT_REQUEST_HEADERS, "User-Agent": self._user_agent})
        return session

    def _wait_for_request_slot(self) -> None:
        now = self._clock()
        if self._last_request_started_at is not None:
            remaining_delay = (
                self._request_interval_seconds - (now - self._last_request_started_at)
            )
            if remaining_delay > 0:
                self._sleep_for(remaining_delay)
                now = self._clock()

        self._last_request_started_at = now


def _validate_request_interval_seconds(interval_seconds: float) -> None:
    if interval_seconds < 0:
        raise ValueError("request_interval_seconds must not be negative")


def _text_from_ok_response(
    response: requests.Response,
    *,
    method: str,
    request_number: int,
) -> str:
    if response.status_code != HTTP_OK_STATUS:
        raise KiwiHouseSittersHTTPError(
            _response_error_message(
                response,
                method=method,
                request_number=request_number,
            )
        )

    return response.text


def _response_error_message(
    response: requests.Response,
    *,
    method: str,
    request_number: int,
) -> str:
    return (
        f"Unexpected status code: {response.status_code}; "
        f"method={method}; "
        f"request_number={request_number}; "
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
