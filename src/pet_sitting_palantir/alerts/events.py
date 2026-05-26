"""Creation of channel-independent alert events from persisted observations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from psycopg import Connection
from psycopg.types.json import Jsonb

from pet_sitting_palantir.alerts.filter_config import AlertFilterDefinition, load_alert_filters
from pet_sitting_palantir.alerts.matcher import (
    alert_fingerprint,
    deliver_after,
    listing_matches_filter,
)
from pet_sitting_palantir.storage.models import ListingRecord, ListingUpsertResult

AlertEventType = Literal[
    "first_match",
    "became_match",
    "material_change",
    "confirmed_reappearance",
]


@dataclass(frozen=True)
class CreatedAlertEvent:
    """One semantic alert event inserted for later provider delivery."""

    id: int
    listing_id: int
    listing_external_id: str
    filter_name: str
    event_type: AlertEventType
    target_channels: tuple[str, ...]
    deliver_after: datetime
    listing_url: str


@dataclass(frozen=True)
class AlertEventCreationSummary:
    """Alert events produced for one complete scrape result."""

    events: tuple[CreatedAlertEvent, ...]

    @property
    def events_created(self) -> int:
        """Return the number of newly persisted alert events."""
        return len(self.events)


def create_alert_events(
    connection: Connection,
    *,
    observations: Iterable[tuple[ListingRecord, ListingUpsertResult]],
    run_id: int,
    filter_definitions: Iterable[AlertFilterDefinition] | None = None,
    detected_at: datetime | None = None,
) -> AlertEventCreationSummary:
    """Persist events for listings matching configured enabled filters."""
    definitions = tuple(
        load_alert_filters() if filter_definitions is None else filter_definitions
    )
    filter_ids = synchronize_alert_filters(connection, definitions)
    event_time = detected_at or datetime.now(UTC)
    created_events: list[CreatedAlertEvent] = []

    for listing, outcome in observations:
        for definition in definitions:
            if not listing_matches_filter(listing, definition):
                continue
            fingerprint = alert_fingerprint(listing)
            event_type = _event_type(
                connection,
                listing_id=outcome.listing_id,
                filter_id=filter_ids[definition.name],
                outcome=outcome,
                fingerprint=fingerprint,
            )
            if event_type is None:
                continue
            inserted = _insert_alert_event(
                connection,
                listing=listing,
                outcome=outcome,
                filter_id=filter_ids[definition.name],
                filter_name=definition.name,
                run_id=run_id,
                event_type=event_type,
                fingerprint=fingerprint,
                target_channels=definition.delivery.channels,
                event_time=event_time,
                delivery_time=deliver_after(event_time, definition.delivery.quiet_hours),
            )
            if inserted is not None:
                created_events.append(inserted)

    return AlertEventCreationSummary(events=tuple(created_events))


def synchronize_alert_filters(
    connection: Connection,
    definitions: Iterable[AlertFilterDefinition],
) -> dict[str, int]:
    """Mirror human-maintained filter definitions into stable database records."""
    filter_ids: dict[str, int] = {}
    definitions = tuple(definitions)
    names = [definition.name for definition in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Alert filter definitions must have unique names")

    with connection.cursor() as cursor:
        if names:
            cursor.execute(
                """
                update alert_filters
                set enabled = false
                where name <> all(%s)
                  and enabled = true
                """,
                (names,),
            )
        else:
            cursor.execute("update alert_filters set enabled = false where enabled = true")

        for definition in definitions:
            cursor.execute(
                """
                select id
                from alert_filters
                where name = %s
                for update
                """,
                (definition.name,),
            )
            existing_rows = cursor.fetchall()
            if len(existing_rows) > 1:
                raise ValueError(f"Multiple alert_filters rows have name: {definition.name}")

            if existing_rows:
                filter_id = existing_rows[0]["id"]
                cursor.execute(
                    """
                    update alert_filters
                    set
                      enabled = %s,
                      site_filter = %s,
                      local_filter = %s
                    where id = %s
                      and (
                        enabled is distinct from %s
                        or site_filter is distinct from %s
                        or local_filter is distinct from %s
                      )
                    """,
                    (
                        definition.enabled,
                        Jsonb(dict(definition.site_filter)),
                        Jsonb(dict(definition.local_filter)),
                        filter_id,
                        definition.enabled,
                        Jsonb(dict(definition.site_filter)),
                        Jsonb(dict(definition.local_filter)),
                    ),
                )
            else:
                cursor.execute(
                    """
                    insert into alert_filters (name, enabled, site_filter, local_filter)
                    values (%s, %s, %s, %s)
                    returning id
                    """,
                    (
                        definition.name,
                        definition.enabled,
                        Jsonb(dict(definition.site_filter)),
                        Jsonb(dict(definition.local_filter)),
                    ),
                )
                filter_id = cursor.fetchone()["id"]
            filter_ids[definition.name] = filter_id

    return filter_ids


def _event_type(
    connection: Connection,
    *,
    listing_id: int,
    filter_id: int,
    outcome: ListingUpsertResult,
    fingerprint: str,
) -> AlertEventType | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select alert_fingerprint
            from alert_events
            where listing_id = %s
              and filter_id = %s
            order by created_at desc, id desc
            limit 1
            """,
            (listing_id, filter_id),
        )
        prior_event = cursor.fetchone()

    if prior_event is None:
        return "first_match" if outcome.created else "became_match"
    if prior_event["alert_fingerprint"] == fingerprint:
        return None
    if outcome.confirmed_reappearance:
        return "confirmed_reappearance"
    return "material_change"


def _insert_alert_event(
    connection: Connection,
    *,
    listing: ListingRecord,
    outcome: ListingUpsertResult,
    filter_id: int,
    filter_name: str,
    run_id: int,
    event_type: AlertEventType,
    fingerprint: str,
    target_channels: tuple[str, ...],
    event_time: datetime,
    delivery_time: datetime,
) -> CreatedAlertEvent | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into alert_events (
              listing_id,
              filter_id,
              detected_run_id,
              event_type,
              appearance_sequence,
              alert_fingerprint,
              listing_content_hash,
              target_channels,
              deliver_after,
              created_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (listing_id, filter_id, appearance_sequence, alert_fingerprint)
            do nothing
            returning id
            """,
            (
                outcome.listing_id,
                filter_id,
                run_id,
                event_type,
                outcome.appearance_sequence,
                fingerprint,
                listing.content_hash,
                list(target_channels),
                delivery_time,
                event_time,
            ),
        )
        inserted = cursor.fetchone()
    if inserted is None:
        return None
    return CreatedAlertEvent(
        id=inserted["id"],
        listing_id=outcome.listing_id,
        listing_external_id=listing.external_id,
        filter_name=filter_name,
        event_type=event_type,
        target_channels=target_channels,
        deliver_after=delivery_time,
        listing_url=listing.url,
    )
