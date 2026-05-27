from datetime import date

import requests

from pet_sitting_palantir.alerts import AlertMessage, TelegramProvider, format_alert_message
from pet_sitting_palantir.storage.models import ListingRecord


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_formats_compact_message_with_alert_name_and_key_listing_fields() -> None:
    message = format_alert_message(alert_name="Post grisesitos", listing=_listing())

    assert message.text.startswith("Post grisesitos\n\nMISSION BAY, AUCKLAND")
    assert "MISSION BAY, AUCKLAND" in message.text
    assert "DATES: 13 Aug 2026 - 3 Sep 2026" in message.text
    assert "LENGTH: 3 weeks" in message.text
    assert "PETS: 1 dog, 2 cats" in message.text
    assert "VIEW HOUSE AD: https://example.test/listing/mission-bay" in message.text
    assert "Lovely spacious" not in message.text
    assert "TYPE:" not in message.text


def test_telegram_provider_posts_message_and_returns_message_id() -> None:
    posted = {}

    def post(url: str, *, json: dict, timeout: int) -> FakeResponse:
        posted.update({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200, {"ok": True, "result": {"message_id": 42}})

    provider = TelegramProvider(bot_token="secret-token", chat_id="1234", post=post)

    result = provider.send(AlertMessage(text="A matching sit"))

    assert result.sent is True
    assert result.provider_message_id == "42"
    assert posted == {
        "url": "https://api.telegram.org/botsecret-token/sendMessage",
        "json": {"chat_id": "1234", "text": "A matching sit"},
        "timeout": 15,
    }


def test_telegram_network_error_does_not_expose_token() -> None:
    def post(url: str, *, json: dict, timeout: int) -> FakeResponse:
        raise requests.ConnectionError(f"failed to reach {url}")

    provider = TelegramProvider(bot_token="never-store-this", chat_id="1234", post=post)

    result = provider.send(AlertMessage(text="A matching sit"))

    assert result.sent is False
    assert result.error_message == "Telegram request failed: ConnectionError"
    assert "never-store-this" not in result.error_message


def _listing() -> ListingRecord:
    return ListingRecord(
        external_id="mission-bay",
        content_hash="hash-v1",
        island="North Island",
        region="Auckland",
        subregion="Auckland - Central",
        city="Mission Bay",
        duration_days=21,
        start_date=date(2026, 8, 13),
        end_date=date(2026, 9, 3),
        house_type="Flat",
        total_animals=3,
        dogs_count=1,
        cats_count=2,
        intro="Lovely spacious open plan living with indoor outdoor flow.",
        url="https://example.test/listing/mission-bay",
    )
