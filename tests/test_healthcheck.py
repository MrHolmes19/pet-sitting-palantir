from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

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
            stalest_scope=ScopeFreshness(
                scope_name="auckland_region",
                interval_minutes=60,
                last_success_at=now.astimezone(UTC) - timedelta(minutes=58),
            ),
        )
    )

    assert message == "\n".join(
        (
            "-- Health check -- OK",
            "- auckland_central: 198",
            "- auckland_region: 18",
            "- north_shore_city: 90",
            "Total: 306 scans, 4 new, 9 changed",
            "Failed scan attempts: 1",
            "Stalest coverage: 58m (auckland_region, interval 60m)",
        )
    )


@pytest.mark.parametrize(
    ("failed_runs", "expected_status"),
    (
        (0, "FLAWLESS"),
        (1, "OK"),
        (4, "OK"),
        (5, "WARN"),
        (19, "WARN"),
        (20, "CRITICAL"),
        (206, "CRITICAL"),
    ),
)
def test_healthcheck_status_uses_failure_thresholds(
    failed_runs: int,
    expected_status: str,
) -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=now,
            successful_runs=10,
            failed_runs=failed_runs,
            new_listings=0,
            changed_listings=0,
            scope_runs=(ScopeRunCount(scope_name="auckland_central", runs=10),),
            stalest_scope=ScopeFreshness(
                scope_name="auckland_central",
                interval_minutes=5,
                last_success_at=now.astimezone(UTC) - timedelta(minutes=4),
            ),
        )
    )

    assert message.startswith(f"-- Health check -- {expected_status}\n")


def test_healthcheck_is_critical_when_no_successful_scans_exist() -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=now,
            successful_runs=0,
            failed_runs=0,
            new_listings=0,
            changed_listings=0,
            scope_runs=(),
            stalest_scope=ScopeFreshness(
                scope_name="auckland_central",
                interval_minutes=5,
                last_success_at=now.astimezone(UTC) - timedelta(minutes=4),
            ),
        )
    )

    assert message.startswith("-- Health check -- CRITICAL\n")


def test_healthcheck_is_critical_when_a_scope_exceeds_twice_its_interval() -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=now,
            successful_runs=10,
            failed_runs=0,
            new_listings=0,
            changed_listings=0,
            scope_runs=(ScopeRunCount(scope_name="auckland_central", runs=10),),
            stalest_scope=ScopeFreshness(
                scope_name="auckland_central",
                interval_minutes=5,
                last_success_at=now.astimezone(UTC) - timedelta(minutes=11),
            ),
        )
    )

    assert message.startswith("-- Health check -- CRITICAL\n")
    assert "Stalest coverage: 11m (auckland_central, interval 5m)" in message


def test_formats_healthcheck_database_error() -> None:
    message = format_healthcheck_message(
        HealthcheckSummary(
            generated_at=datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland")),
            successful_runs=0,
            failed_runs=0,
            new_listings=0,
            changed_listings=0,
            scope_runs=(),
            stalest_scope=None,
            database_error="OperationalError",
        )
    )

    assert message == "\n".join(
        (
            "-- Health check -- CRITICAL",
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
                "-- Health check -- CRITICAL",
                "Database: unavailable (ConnectionError)",
            )
        )
    ]
