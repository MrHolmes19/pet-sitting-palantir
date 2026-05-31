"""Alerting boundaries for outbound notifications."""

from pet_sitting_palantir.alerts.events import (
    AlertEventCreationSummary,
    CreatedAlertEvent,
    create_alert_events,
    synchronize_alert_filters,
)
from pet_sitting_palantir.alerts.filter_config import (
    DEFAULT_ALERT_FILTER_DEFAULTS_PATH,
    DEFAULT_ALERT_FILTERS_PATH,
    AlertDelivery,
    AlertFilterDefaults,
    AlertFilterDefinition,
    AlertQuietHours,
    load_alert_filters,
)
from pet_sitting_palantir.alerts.matcher import (
    alert_fingerprint,
    deliver_after,
    listing_matches_filter,
)
from pet_sitting_palantir.alerts.messages import AlertMessage, format_alert_message
from pet_sitting_palantir.alerts.providers import (
    NotificationDispatchFailure,
    NotificationDispatchSummary,
    NotificationProvider,
    ProviderDeliveryResult,
    TelegramProvider,
    configured_notification_providers,
    send_notification,
)

__all__ = [
    "DEFAULT_ALERT_FILTER_DEFAULTS_PATH",
    "DEFAULT_ALERT_FILTERS_PATH",
    "AlertEventCreationSummary",
    "AlertDelivery",
    "AlertFilterDefaults",
    "AlertFilterDefinition",
    "AlertMessage",
    "AlertQuietHours",
    "CreatedAlertEvent",
    "NotificationDispatchFailure",
    "NotificationDispatchSummary",
    "NotificationProvider",
    "ProviderDeliveryResult",
    "TelegramProvider",
    "alert_fingerprint",
    "configured_notification_providers",
    "create_alert_events",
    "deliver_after",
    "format_alert_message",
    "load_alert_filters",
    "listing_matches_filter",
    "send_notification",
    "synchronize_alert_filters",
]
