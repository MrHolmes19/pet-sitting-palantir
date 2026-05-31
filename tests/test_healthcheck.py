from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from pet_sitting_palantir.alerts import NotificationDispatchSummary
from pet_sitting_palantir.workflows.healthcheck import (
    HealthcheckSummary,
    ScopeFreshness,
    ScopeRunCount,
    format_healthcheck_message,
    send_healthcheck,
)


def test_formats_healthcheck_with_scan_counts_and_freshness() -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland"))

    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=now,
            successful_runs=306,
            failed_runs=1,
            new_listings=4,
            changed_listings=9,
            scope_runs=(
                ScopeRunCount(scope_name="auckland_central", runs=198, new_listings=2),
                ScopeRunCount(scope_name="auckland_region", runs=18, new_listings=1),
                ScopeRunCount(scope_name="north_shore_city", runs=90, new_listings=1),
            ),
            oldest_scope=ScopeFreshness(
                scope_name="auckland_region",
                last_success_at=now.astimezone(UTC) - timedelta(minutes=58),
            ),
        )
    )

    assert message == "\n".join(
        (
            "-- Health check -- WARN",
            "- auckland_central: 198",
            "- auckland_region: 18",
            "- north_shore_city: 90",
            "Total: 306 scans, 4 new, 9 changed",
            "Failures: 1",
        )
    )


def test_formats_healthcheck_database_error() -> None:
    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland")),
            successful_runs=0,
            failed_runs=0,
            new_listings=0,
            changed_listings=0,
            scope_runs=(),
            oldest_scope=None,
            database_error="OperationalError",
        )
    )

    assert message == "\n".join(
        (
            "-- Health check -- ERROR",
            "Database: unavailable (OperationalError)",
        )
    )


def test_healthcheck_uses_notification_layer_without_selecting_provider(monkeypatch) -> None:
    sent_messages = []

    def fail_to_connect(database_url=None):
        raise ConnectionError("offline")

    def send(message):
        sent_messages.append(message.text)
        return NotificationDispatchSummary(
            providers_configured=1,
            sent=1,
            failed=0,
            provider_message_ids={"test": "message-42"},
            failures=(),
        )

    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.healthcheck.connect_database",
        fail_to_connect,
    )

    result = send_healthcheck(
        current_time=datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland")),
        notification_sender=send,
    )

    assert result.status == "sent"
    assert result.provider_message_id == "test:message-42"
    assert sent_messages == [
        "\n".join(
            (
                "-- Health check -- ERROR",
                "Database: unavailable (ConnectionError)",
            )
        )
    ]
