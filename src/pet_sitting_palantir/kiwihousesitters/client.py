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
    KIWIHOUSESITTERS_TRANSIENT_RETRY_ATTEMPTS,
    KIWIHOUSESITTERS_TRANSIENT_RETRY_BACKOFF_SECONDS,
)

RETRYABLE_STATUS_CODES = frozenset({408, 500, 502, 503, 504})


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
        transient_retry_attempts: int = KIWIHOUSESITTERS_TRANSIENT_RETRY_ATTEMPTS,
        transient_retry_backoff_seconds: float = (KIWIHOUSESITTERS_TRANSIENT_RETRY_BACKOFF_SECONDS),
        user_agent: str = DEFAULT_USER_AGENT,
        clock: Callable[[], float] = monotonic,
        sleep_for: Callable[[float], None] = sleep,
        session_factory: Callable[[], requests.Session] = requests.Session,
    ) -> None:
        _validate_request_interval_seconds(request_interval_seconds)
        _validate_retry_settings(
            attempts=transient_retry_attempts,
            backoff_seconds=transient_retry_backoff_seconds,
        )

        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = request_interval_seconds
        self._transient_retry_attempts = transient_retry_attempts
        self._transient_retry_backoff_seconds = transient_retry_backoff_seconds
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
        return self._request_html(
            method="GET",
            request=lambda: self._session.get(
                url,
                headers=headers,
                timeout=self._timeout_seconds,
            ),
        )

    def post_html(self, url: str, *, data: Mapping[str, Any]) -> str:
        """POST one HTML form request and raise for non-success responses."""
        return self._request_html(
            method="POST",
            request=lambda: self._session.post(
                url,
                data=data,
                timeout=self._timeout_seconds,
            ),
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

    def _request_html(
        self,
        *,
        method: str,
        request: Callable[[], requests.Response],
    ) -> str:
        for retry_number in range(self._transient_retry_attempts + 1):
            self._wait_for_request_slot()
            self._requests_started += 1
            try:
                response = request()
            except requests.ConnectionError, requests.Timeout:
                if retry_number >= self._transient_retry_attempts:
                    raise
                self._wait_before_retry(retry_number)
                continue

            if response.status_code == HTTP_OK_STATUS:
                return response.text
            if (
                response.status_code not in RETRYABLE_STATUS_CODES
                or retry_number >= self._transient_retry_attempts
            ):
                return _text_from_ok_response(
                    response,
                    method=method,
                    request_number=self._requests_started,
                )
            self._wait_before_retry(retry_number)

        raise AssertionError("transient retry loop ended unexpectedly")

    def _wait_before_retry(self, retry_number: int) -> None:
        self._sleep_for(self._transient_retry_backoff_seconds * (2**retry_number))

    def _wait_for_request_slot(self) -> None:
        now = self._clock()
        if self._last_request_started_at is not None:
            remaining_delay = self._request_interval_seconds - (now - self._last_request_started_at)
            if remaining_delay > 0:
                self._sleep_for(remaining_delay)
                now = self._clock()

        self._last_request_started_at = now


def _validate_request_interval_seconds(interval_seconds: float) -> None:
    if interval_seconds < 0:
        raise ValueError("request_interval_seconds must not be negative")


def _validate_retry_settings(*, attempts: int, backoff_seconds: float) -> None:
    if attempts < 0:
        raise ValueError("transient_retry_attempts must not be negative")
    if backoff_seconds < 0:
        raise ValueError("transient_retry_backoff_seconds must not be negative")


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
        f"retry_after={response.headers.get('retry-after', 'unknown')}; "
        f"body_snippet={_body_snippet(response.text)}"
    )


def _body_snippet(text: str, *, max_length: int = 300) -> str:
    collapsed = sub(r"\s+", " ", text).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[:max_length]}..."
