"""Resumable region-by-region execution for broad logical scrape scopes."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import uniform
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.client import (
    KiwiHouseSittersDeadlineExceeded,
    KiwiHouseSittersWAFChallengeError,
)
from pet_sitting_palantir.kiwihousesitters.constants import WAF_CHALLENGE_ERROR_MARKER
from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS
from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult
from pet_sitting_palantir.kiwihousesitters.search_filters import build_search_request
from pet_sitting_palantir.settings import (
    BROAD_SCRAPE_DIRECT_RETRY_DAYS,
    BROAD_SCRAPE_FAILURE_COOLDOWN_MINUTES,
    BROAD_SCRAPE_LEAF_DELAY_MAX_SECONDS,
    BROAD_SCRAPE_LEAF_DELAY_MIN_SECONDS,
    BROAD_SCRAPE_SPLIT_COOLDOWN_MINUTES,
    BROAD_SCRAPE_WAF_INITIAL_COOLDOWN_HOURS,
    BROAD_SCRAPE_WAF_MAX_COOLDOWN_HOURS,
)
from pet_sitting_palantir.storage import (
    BroadScrapeCampaign,
    BroadScrapeCampaignLeaf,
    ScrapeScope,
    close_scrape_run,
    complete_broad_scrape_campaign,
    create_broad_scrape_campaign,
    create_scrape_run,
    read_active_broad_scrape_campaign,
    read_broad_scrape_campaign_payload,
    read_broad_scrape_campaign_progress,
    read_latest_campaign_scope_waf_challenge_at,
    read_latest_scope_waf_challenge_at,
    read_next_broad_scrape_campaign_leaf,
    record_broad_scrape_leaf_failure,
    record_broad_scrape_leaf_success,
    split_broad_scrape_campaign_leaf,
)
from pet_sitting_palantir.workflows.scrape_and_store import (
    Scraper,
    StoredScrapeResult,
    store_completed_scrape_result_with_connection,
)

ALL_NZ_MISSING_EVIDENCE_STATES = frozenset({"south-island"})


@dataclass(frozen=True)
class BroadCampaignStep:
    """Observable outcome of one bounded campaign step."""

    scope_name: str
    campaign_id: int
    status: str
    leaf_key: str | None
    completed_leaves: int
    total_leaves: int
    next_attempt_at: datetime | None = None
    waf_challenge_count: int = 0
    error_message: str | None = None
    stored_result: StoredScrapeResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "scope_name": self.scope_name,
            "campaign_id": self.campaign_id,
            "status": self.status,
            "leaf_key": self.leaf_key,
            "completed_leaves": self.completed_leaves,
            "total_leaves": self.total_leaves,
            "next_attempt_at": (
                self.next_attempt_at.isoformat() if self.next_attempt_at is not None else None
            ),
            "waf_challenge_count": self.waf_challenge_count,
            "error_message": self.error_message,
            "stored_result": (
                self.stored_result.to_dict() if self.stored_result is not None else None
            ),
        }


def is_broad_scrape_scope(scope: ScrapeScope) -> bool:
    """Return whether a scope uses deadline-bounded campaign execution."""
    return "region" not in scope.site_filter


def run_broad_scrape_campaign_step(
    connection: Connection,
    *,
    scope: ScrapeScope,
    scraper: Scraper,
    current_time: datetime | None = None,
    random_between: Callable[[float, float], float] = uniform,
) -> BroadCampaignStep:
    """Run one direct or fallback leaf and atomically finalize the complete parent."""
    instant = current_time or datetime.now(tz=UTC)
    if instant.tzinfo is None:
        raise ValueError("current_time must include a timezone")

    campaign = read_active_broad_scrape_campaign(connection, scope_id=scope.id)
    if campaign is None:
        latest_scope_waf_at = _latest_instant(
            read_latest_scope_waf_challenge_at(
                connection,
                scope_name=scope.name,
            ),
            read_latest_campaign_scope_waf_challenge_at(
                connection,
                scope_id=scope.id,
            ),
        )
        use_regional_fallback = latest_scope_waf_at is not None and (
            instant - latest_scope_waf_at < timedelta(days=BROAD_SCRAPE_DIRECT_RETRY_DAYS)
        )
        campaign = create_broad_scrape_campaign(
            connection,
            scope=scope,
            leaves=_campaign_leaves(scope, use_regional_fallback=use_regional_fallback),
            next_attempt_at=instant,
        )
        _commit_if_transactional(connection)

    completed, total = read_broad_scrape_campaign_progress(
        connection,
        campaign_id=campaign.id,
    )
    if instant < campaign.next_attempt_at:
        return BroadCampaignStep(
            scope_name=scope.name,
            campaign_id=campaign.id,
            status="deferred",
            leaf_key=None,
            completed_leaves=completed,
            total_leaves=total,
            next_attempt_at=campaign.next_attempt_at,
            waf_challenge_count=campaign.waf_challenge_count,
        )

    leaf = read_next_broad_scrape_campaign_leaf(connection, campaign_id=campaign.id)
    if leaf is None:
        return _finalize_campaign(connection, scope=scope, campaign=campaign, instant=instant)

    try:
        result = scraper(leaf.site_filter, max_pages=None)
    except Exception as error:
        _rollback_if_transactional(connection)
        return _pause_failed_leaf(
            connection,
            scope=scope,
            campaign=campaign,
            leaf=leaf,
            error=error,
            instant=instant,
        )

    next_attempt_at = instant + timedelta(
        seconds=random_between(
            BROAD_SCRAPE_LEAF_DELAY_MIN_SECONDS,
            BROAD_SCRAPE_LEAF_DELAY_MAX_SECONDS,
        )
    )
    try:
        record_broad_scrape_leaf_success(
            connection,
            campaign_id=campaign.id,
            leaf_key=leaf.leaf_key,
            pages_fetched=result.pages_fetched,
            listings=tuple(listing.to_dict() for listing in result.listings),
            completed_at=instant,
            next_attempt_at=next_attempt_at,
        )
        completed, total = read_broad_scrape_campaign_progress(
            connection,
            campaign_id=campaign.id,
        )
        if completed == total:
            return _finalize_campaign(connection, scope=scope, campaign=campaign, instant=instant)
        _commit_if_transactional(connection)
    except Exception as error:
        _rollback_if_transactional(connection)
        return _pause_failed_leaf(
            connection,
            scope=scope,
            campaign=campaign,
            leaf=leaf,
            error=error,
            instant=instant,
        )

    return BroadCampaignStep(
        scope_name=scope.name,
        campaign_id=campaign.id,
        status="in_progress",
        leaf_key=leaf.leaf_key,
        completed_leaves=completed,
        total_leaves=total,
        next_attempt_at=next_attempt_at,
        waf_challenge_count=campaign.waf_challenge_count,
    )


def _pause_failed_leaf(
    connection: Connection,
    *,
    scope: ScrapeScope,
    campaign: BroadScrapeCampaign,
    leaf: BroadScrapeCampaignLeaf,
    error: Exception,
    instant: datetime,
) -> BroadCampaignStep:
    waf_challenge = isinstance(error, KiwiHouseSittersWAFChallengeError) or (
        WAF_CHALLENGE_ERROR_MARKER in str(error)
    )
    deadline_exceeded = isinstance(error, KiwiHouseSittersDeadlineExceeded)
    if waf_challenge:
        cooldown_hours = min(
            BROAD_SCRAPE_WAF_INITIAL_COOLDOWN_HOURS * (2**campaign.waf_challenge_count),
            BROAD_SCRAPE_WAF_MAX_COOLDOWN_HOURS,
        )
        next_attempt_at = instant + timedelta(hours=cooldown_hours)
        status = "waf_paused"
    elif deadline_exceeded:
        next_attempt_at = instant + timedelta(minutes=BROAD_SCRAPE_SPLIT_COOLDOWN_MINUTES)
        status = "split_paused"
    else:
        next_attempt_at = instant + timedelta(minutes=BROAD_SCRAPE_FAILURE_COOLDOWN_MINUTES)
        status = "failed_paused"

    message = WAF_CHALLENGE_ERROR_MARKER if waf_challenge else str(error) or type(error).__name__
    failed_run_id = create_scrape_run(
        connection,
        scope_id=scope.id,
        scope_name=scope.name,
        search_url=build_search_request(leaf.site_filter).url,
    )
    close_scrape_run(
        connection,
        run_id=failed_run_id,
        status="failed",
        error_message=message,
    )
    should_split = leaf.leaf_key == "__full__" and (waf_challenge or deadline_exceeded)
    if should_split:
        waf_challenge_count = split_broad_scrape_campaign_leaf(
            connection,
            leaf=leaf,
            children=_regional_campaign_leaves(scope),
            attempted_at=instant,
            next_attempt_at=next_attempt_at,
            error_message=message,
            waf_challenge=waf_challenge,
        )
    else:
        waf_challenge_count = record_broad_scrape_leaf_failure(
            connection,
            campaign_id=campaign.id,
            leaf_key=leaf.leaf_key,
            attempted_at=instant,
            next_attempt_at=next_attempt_at,
            error_message=message,
            waf_challenge=waf_challenge,
        )
    _commit_if_transactional(connection)
    completed, total = read_broad_scrape_campaign_progress(
        connection,
        campaign_id=campaign.id,
    )
    return BroadCampaignStep(
        scope_name=scope.name,
        campaign_id=campaign.id,
        status=status,
        leaf_key=leaf.leaf_key,
        completed_leaves=completed,
        total_leaves=total,
        next_attempt_at=next_attempt_at,
        waf_challenge_count=waf_challenge_count,
        error_message=message,
    )


def _finalize_campaign(
    connection: Connection,
    *,
    scope: ScrapeScope,
    campaign: BroadScrapeCampaign,
    instant: datetime,
) -> BroadCampaignStep:
    pages_fetched, payload, observed_at_by_external_id, coverage_observations = (
        read_broad_scrape_campaign_payload(
            connection,
            campaign_id=campaign.id,
        )
    )
    completed, total = read_broad_scrape_campaign_progress(
        connection,
        campaign_id=campaign.id,
    )
    if completed != total:
        raise RuntimeError(f"Campaign {campaign.id} cannot finish with incomplete leaves")

    listings = tuple(_listing_from_payload(item) for item in payload)
    scrape_result = ScrapeResult(
        search_url=build_search_request(scope.site_filter).url,
        pages_fetched=pages_fetched,
        listings=listings,
    )
    try:
        stored_result = store_completed_scrape_result_with_connection(
            connection,
            scope_name=scope.name,
            scrape_result=scrape_result,
            observed_at_by_external_id=observed_at_by_external_id,
            coverage_observations=coverage_observations,
            advance_covered_scopes=False,
            excluded_missing_regions=frozenset({"auckland"}),
            allowed_missing_states=_missing_evidence_states(scope),
            commit=False,
        )
        complete_broad_scrape_campaign(
            connection,
            campaign_id=campaign.id,
            completed_at=instant,
        )
        _commit_if_transactional(connection)
    except BaseException:
        _rollback_if_transactional(connection)
        raise

    return BroadCampaignStep(
        scope_name=scope.name,
        campaign_id=campaign.id,
        status="completed",
        leaf_key=None,
        completed_leaves=completed,
        total_leaves=total,
        waf_challenge_count=campaign.waf_challenge_count,
        stored_result=stored_result,
    )


def _campaign_leaves(
    scope: ScrapeScope,
    *,
    use_regional_fallback: bool = False,
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    if not use_regional_fallback:
        return (("__full__", dict(scope.site_filter)),)
    return _regional_campaign_leaves(scope)


def _regional_campaign_leaves(
    scope: ScrapeScope,
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    state = scope.site_filter.get("state")
    if state is not None and not isinstance(state, str):
        raise TypeError("site_filter.state must be a string")

    return tuple(
        (
            region_slug,
            {"state": region_filter.state, "region": region_slug},
        )
        for region_slug, region_filter in REGION_FILTERS.items()
        if state is None or region_filter.state == state
    )


def _missing_evidence_states(scope: ScrapeScope) -> frozenset[str]:
    """Partition broad missing authority so overlapping parents never double-count."""
    if scope.name == "all_nz":
        return ALL_NZ_MISSING_EVIDENCE_STATES

    state = scope.site_filter.get("state")
    if not isinstance(state, str):
        raise ValueError(f"Broad scope has no missing-evidence state: {scope.name}")
    return frozenset({state})


def _listing_from_payload(payload: Mapping[str, Any]) -> Listing:
    values = dict(payload)
    for field_name in ("start_date", "end_date"):
        value = values.get(field_name)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"Campaign listing {field_name} must be an ISO date")
            values[field_name] = date.fromisoformat(value)
    return Listing(**values)


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()


def _rollback_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.rollback()


def _latest_instant(*instants: datetime | None) -> datetime | None:
    present = tuple(instant for instant in instants if instant is not None)
    return max(present) if present else None
