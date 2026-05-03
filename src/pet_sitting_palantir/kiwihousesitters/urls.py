"""URL construction for KiwiHouseSitters search scopes."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from pet_sitting_palantir.kiwihousesitters.constants import SEARCH_URL


def build_search_url(site_filter: Mapping[str, Any] | None = None) -> str:
    """Build an initial KiwiHouseSitters search URL from site filter values."""
    if not site_filter:
        return SEARCH_URL

    query = urlencode(site_filter, doseq=True)
    return f"{SEARCH_URL}?{query}"
