"""Notification provider interfaces and Telegram implementation."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from pet_sitting_palantir.alerts.messages import AlertMessage
from pet_sitting_palantir.config import load_settings
from pet_sitting_palantir.settings import TELEGRAM_TIMEOUT_SECONDS

TELEGRAM_API_ROOT = "https://api.telegram.org"
MAX_PROVIDER_ERROR_LENGTH = 300


@dataclass(frozen=True)
class ProviderDeliveryResult:
    """Result of one provider send request."""

    sent: bool
    provider_message_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class NotificationDispatchFailure:
    """One failed provider attempt for a direct notification."""

    channel: str
    error_message: str


@dataclass(frozen=True)
class NotificationDispatchSummary:
    """Provider-neutral result for a direct notification send."""

    providers_configured: int
    sent: int
    failed: int
    provider_message_ids: Mapping[str, str]
    failures: tuple[NotificationDispatchFailure, ...]


class NotificationProvider(Protocol):
    """Outbound notification channel adapter."""

    channel: str

    def send(self, message: AlertMessage) -> ProviderDeliveryResult: ...


class TelegramProvider:
    """Send plain-text messages to one Telegram chat via the Bot API."""

    channel = "telegram"

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        post: Callable[..., requests.Response] = requests.post,
        timeout_seconds: int = TELEGRAM_TIMEOUT_SECONDS,
    ) -> None:
        self._endpoint = f"{TELEGRAM_API_ROOT}/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._post = post
        self._timeout_seconds = timeout_seconds

    def send(self, message: AlertMessage) -> ProviderDeliveryResult:
        try:
            response = self._post(
                self._endpoint,
                json={"chat_id": self._chat_id, "text": message.text},
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            return ProviderDeliveryResult(
                sent=False,
                error_message=f"Telegram request failed: {type(error).__name__}",
            )

        payload = _response_payload(response)
        if response.status_code != 200 or payload.get("ok") is not True:
            description = payload.get("description")
            detail = (
                description
                if isinstance(description, str) and description.strip()
                else f"HTTP {response.status_code}"
            )
            return ProviderDeliveryResult(
                sent=False,
                error_message=f"Telegram send failed: {detail}"[:MAX_PROVIDER_ERROR_LENGTH],
            )

        result = payload.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return ProviderDeliveryResult(
            sent=True,
            provider_message_id=str(message_id) if message_id is not None else None,
        )


def configured_notification_providers() -> Mapping[str, NotificationProvider]:
    """Return providers whose runtime credentials are available."""
    settings = load_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {}
    telegram = TelegramProvider(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    return {telegram.channel: telegram}


def send_notification(
    message: AlertMessage,
    *,
    providers: Mapping[str, NotificationProvider] | None = None,
) -> NotificationDispatchSummary:
    """Send one direct notification through every configured provider."""
    registry = configured_notification_providers() if providers is None else providers
    provider_message_ids: dict[str, str] = {}
    failures: list[NotificationDispatchFailure] = []

    for channel, provider in sorted(registry.items()):
        result = provider.send(message)
        if result.sent:
            if result.provider_message_id is not None:
                provider_message_ids[channel] = result.provider_message_id
        else:
            failures.append(
                NotificationDispatchFailure(
                    channel=channel,
                    error_message=result.error_message or "Notification send failed",
                )
            )

    return NotificationDispatchSummary(
        providers_configured=len(registry),
        sent=len(registry) - len(failures),
        failed=len(failures),
        provider_message_ids=provider_message_ids,
        failures=tuple(failures),
    )


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
