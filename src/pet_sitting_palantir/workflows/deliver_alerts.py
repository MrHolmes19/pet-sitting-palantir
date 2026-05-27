"""Delivery of persisted alert events through configured notification providers."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.alerts.messages import format_alert_message
from pet_sitting_palantir.alerts.providers import (
    NotificationProvider,
    ProviderDeliveryResult,
    configured_notification_providers,
)
from pet_sitting_palantir.storage import ListingRecord, connect_database


@dataclass(frozen=True)
class PendingAlertDelivery:
    """One event/channel pair eligible for an outbound attempt."""

    alert_event_id: int
    channel: str
    alert_name: str
    listing: ListingRecord


@dataclass(frozen=True)
class AlertDeliveryFailure:
    """One unsent delivery and its concise failure detail."""

    alert_event_id: int
    channel: str
    error_message: str


@dataclass(frozen=True)
class AlertDeliverySummary:
    """Result of processing currently due event/channel deliveries."""

    deliveries_due: int
    attempts_made: int
    sent: int
    failed: int
    unconfigured: int
    failures: tuple[AlertDeliveryFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload["failures"] = [asdict(failure) for failure in self.failures]
        return payload


def deliver_due_alerts(
    *,
    database_url: str | None = None,
    providers: Mapping[str, NotificationProvider] | None = None,
    current_time: datetime | None = None,
) -> AlertDeliverySummary:
    """Open a database connection and deliver all currently eligible alerts."""
    connection = connect_database(database_url)
    try:
        return deliver_due_alerts_with_connection(
            connection,
            providers=providers,
            current_time=current_time,
        )
    finally:
        connection.close()


def deliver_due_alerts_with_connection(
    connection: Connection,
    *,
    providers: Mapping[str, NotificationProvider] | None = None,
    current_time: datetime | None = None,
) -> AlertDeliverySummary:
    """Deliver eligible alerts using a provided connection and provider registry."""
    instant = current_time or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("current_time must include a timezone")

    pending = _read_pending_deliveries(connection, instant)
    registry = configured_notification_providers() if providers is None else providers
    attempts_made = 0
    sent = 0
    failed = 0
    unconfigured = 0
    failures: list[AlertDeliveryFailure] = []

    for delivery in pending:
        provider = registry.get(delivery.channel)
        if provider is None:
            unconfigured += 1
            failures.append(
                AlertDeliveryFailure(
                    alert_event_id=delivery.alert_event_id,
                    channel=delivery.channel,
                    error_message=f"No configured notification provider for {delivery.channel}",
                )
            )
            continue

        message = format_alert_message(alert_name=delivery.alert_name, listing=delivery.listing)
        try:
            result = provider.send(message)
        except Exception as error:
            result = ProviderDeliveryResult(
                sent=False,
                error_message=f"Provider request raised: {type(error).__name__}",
            )
        attempts_made += 1
        _record_attempt(
            connection,
            delivery=delivery,
            message=message.text,
            result=result,
        )
        _commit_if_transactional(connection)

        if result.sent:
            sent += 1
        else:
            failed += 1
            failures.append(
                AlertDeliveryFailure(
                    alert_event_id=delivery.alert_event_id,
                    channel=delivery.channel,
                    error_message=result.error_message or "Provider send failed",
                )
            )

    return AlertDeliverySummary(
        deliveries_due=len(pending),
        attempts_made=attempts_made,
        sent=sent,
        failed=failed,
        unconfigured=unconfigured,
        failures=tuple(failures),
    )


def _read_pending_deliveries(
    connection: Connection,
    instant: datetime,
) -> tuple[PendingAlertDelivery, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              alert_events.id as alert_event_id,
              target.channel,
              alert_filters.name as alert_name,
              listings.external_id,
              listings.content_hash,
              listings.island,
              listings.region,
              listings.subregion,
              listings.city,
              listings.duration_days,
              listings.start_date,
              listings.end_date,
              listings.house_type,
              listings.total_animals,
              listings.dogs_count,
              listings.cats_count,
              listings.fish_count,
              listings.birds_count,
              listings.rabbits_guinea_pigs_count,
              listings.chickens_ducks_geese_count,
              listings.farm_animals_count,
              listings.horses_count,
              listings.reptiles_count,
              listings.other_pets_count,
              listings.no_pets,
              listings.starts_soon,
              listings.reply_rating_score,
              listings.listing_tag,
              listings.title,
              listings.intro,
              listings.url
            from alert_events
            cross join lateral unnest(alert_events.target_channels) as target(channel)
            join alert_filters on alert_filters.id = alert_events.filter_id
            join listings on listings.id = alert_events.listing_id
            where alert_events.deliver_after <= %s
              and not exists (
                select 1
                from alert_delivery_attempts
                where alert_delivery_attempts.alert_event_id = alert_events.id
                  and alert_delivery_attempts.channel = target.channel
                  and alert_delivery_attempts.status = 'sent'
              )
            order by alert_events.deliver_after, alert_events.id, target.channel
            """,
            (instant,),
        )
        return tuple(_delivery_from_row(row) for row in cursor.fetchall())


def _delivery_from_row(row: Mapping[str, Any]) -> PendingAlertDelivery:
    return PendingAlertDelivery(
        alert_event_id=row["alert_event_id"],
        channel=row["channel"],
        alert_name=row["alert_name"],
        listing=ListingRecord(
            external_id=row["external_id"],
            content_hash=row["content_hash"],
            island=row["island"],
            region=row["region"],
            subregion=row["subregion"],
            city=row["city"],
            duration_days=row["duration_days"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            house_type=row["house_type"],
            total_animals=row["total_animals"],
            dogs_count=row["dogs_count"],
            cats_count=row["cats_count"],
            fish_count=row["fish_count"],
            birds_count=row["birds_count"],
            rabbits_guinea_pigs_count=row["rabbits_guinea_pigs_count"],
            chickens_ducks_geese_count=row["chickens_ducks_geese_count"],
            farm_animals_count=row["farm_animals_count"],
            horses_count=row["horses_count"],
            reptiles_count=row["reptiles_count"],
            other_pets_count=row["other_pets_count"],
            no_pets=row["no_pets"],
            starts_soon=row["starts_soon"],
            reply_rating_score=row["reply_rating_score"],
            listing_tag=row["listing_tag"],
            title=row["title"],
            intro=row["intro"],
            url=row["url"],
        ),
    )


def _record_attempt(
    connection: Connection,
    *,
    delivery: PendingAlertDelivery,
    message: str,
    result: ProviderDeliveryResult,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into alert_delivery_attempts (
              alert_event_id,
              channel,
              status,
              message,
              provider_message_id,
              error_message
            )
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                delivery.alert_event_id,
                delivery.channel,
                "sent" if result.sent else "failed",
                message,
                result.provider_message_id,
                result.error_message,
            ),
        )


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()
