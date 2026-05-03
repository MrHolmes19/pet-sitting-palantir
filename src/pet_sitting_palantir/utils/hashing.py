"""Stable hashing helpers."""

from collections.abc import Mapping
from hashlib import sha256
from json import dumps
from typing import Any


def stable_content_hash(data: Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 hash for JSON-serializable content."""
    payload = dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()
