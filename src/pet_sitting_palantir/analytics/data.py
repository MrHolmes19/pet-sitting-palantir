"""Data loading and transformations for analytics dashboards."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd

SEASONALITY_BASIS = Literal["sit_dates", "first_seen"]
INTERVAL = Literal["month", "week"]

PET_COUNT_COLUMNS = (
    "dogs_count",
    "cats_count",
    "fish_count",
    "birds_count",
    "rabbits_guinea_pigs_count",
    "chickens_ducks_geese_count",
    "farm_animals_count",
    "horses_count",
    "reptiles_count",
    "other_pets_count",
)

DURATION_BUCKETS = (
    "0-7 days",
    "8-14 days",
    "15-30 days",
    "31-60 days",
    "61+ days",
)


@dataclass(frozen=True)
class DashboardFilters:
    """Filter values selected in the dashboard sidebar."""

    start_date: date
    end_date: date
    regions: tuple[str, ...]
    subregions: tuple[str, ...]
    cities: tuple[str, ...]
    pet_labels: tuple[str, ...]
    duration_buckets: tuple[str, ...]
    statuses: tuple[str, ...]


def load_listing_facts(database_path: Path) -> pd.DataFrame:
    """Load listing rows from a DuckDB analytics snapshot with derived columns."""
    if not database_path.exists():
        raise FileNotFoundError(f"Analytics database does not exist: {database_path}")

    with duckdb.connect(str(database_path), read_only=True) as connection:
        listings = connection.sql("select * from listings").df()

    return prepare_listing_facts(listings)


def prepare_listing_facts(listings: pd.DataFrame) -> pd.DataFrame:
    """Return listing facts with dashboard-friendly derived columns."""
    facts = listings.copy()
    facts["start_date"] = pd.to_datetime(facts["start_date"], errors="coerce")
    facts["end_date"] = pd.to_datetime(facts["end_date"], errors="coerce")
    facts["first_seen_at"] = pd.to_datetime(facts["first_seen_at"], errors="coerce")

    derived_duration = (facts["end_date"] - facts["start_date"]).dt.days + 1
    facts["duration_days"] = facts["duration_days"].fillna(derived_duration)
    facts["duration_bucket"] = facts["duration_days"].apply(duration_bucket)
    facts["lead_time_days"] = (
        facts["start_date"].dt.normalize() - facts["first_seen_at"].dt.normalize()
    ).dt.days
    facts["pet_label"] = facts.apply(pet_label, axis=1)
    facts["has_dogs"] = facts["dogs_count"] > 0
    facts["has_cats"] = facts["cats_count"] > 0
    facts["has_long_sit"] = facts["duration_days"] >= 31
    return facts


def duration_bucket(duration_days: int | float | None) -> str | None:
    """Bucket a sit duration into a small set of stable labels."""
    if pd.isna(duration_days):
        return None
    if duration_days <= 7:
        return "0-7 days"
    if duration_days <= 14:
        return "8-14 days"
    if duration_days <= 30:
        return "15-30 days"
    if duration_days <= 60:
        return "31-60 days"
    return "61+ days"


def pet_label(listing: pd.Series) -> str:
    """Return one display pet label for a listing."""
    if bool(listing.get("no_pets", False)):
        return "No pets"

    dogs_count = int(listing.get("dogs_count", 0) or 0)
    cats_count = int(listing.get("cats_count", 0) or 0)
    other_count = sum(int(listing.get(column, 0) or 0) for column in PET_COUNT_COLUMNS[2:])

    if dogs_count and cats_count:
        return "Dogs and cats"
    if dogs_count and other_count:
        return "Mixed pets"
    if cats_count and other_count:
        return "Mixed pets"
    if dogs_count:
        return "Dogs"
    if cats_count:
        return "Cats"
    if other_count:
        return "Other"
    return "Other"


def filter_listing_facts(facts: pd.DataFrame, filters: DashboardFilters) -> pd.DataFrame:
    """Apply dashboard filters to listing facts."""
    filtered = facts.copy()
    start_timestamp = pd.Timestamp(filters.start_date)
    end_timestamp = pd.Timestamp(filters.end_date) + pd.Timedelta(days=1)

    filtered = filtered[
        (filtered["start_date"] >= start_timestamp)
        & (filtered["start_date"] < end_timestamp)
    ]

    filtered = _filter_in(filtered, "region", filters.regions)
    filtered = _filter_in(filtered, "subregion", filters.subregions)
    filtered = _filter_in(filtered, "city", filters.cities)
    filtered = _filter_in(filtered, "pet_label", filters.pet_labels)
    filtered = _filter_in(filtered, "duration_bucket", filters.duration_buckets)
    filtered = _filter_in(filtered, "status", filters.statuses)
    return filtered


def seasonality_frame(
    facts: pd.DataFrame,
    *,
    basis: SEASONALITY_BASIS,
    interval: INTERVAL,
) -> pd.DataFrame:
    """Expand filtered listings into period-level seasonality rows."""
    rows: list[dict[str, object]] = []

    for listing in facts.itertuples(index=False):
        if basis == "first_seen":
            period_starts = _period_starts_between(
                listing.first_seen_at,
                listing.first_seen_at,
                interval=interval,
            )
        else:
            period_starts = _period_starts_between(
                listing.start_date,
                listing.end_date,
                interval=interval,
            )

        for period_start in period_starts:
            rows.append(
                {
                    "external_id": listing.external_id,
                    "period_start": period_start,
                    "year": period_start.year,
                    "month": period_start.month,
                    "week": period_start.isocalendar().week,
                    "duration_days": listing.duration_days,
                    "lead_time_days": listing.lead_time_days,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "period_start",
                "year",
                "month",
                "week",
                "listing_count",
                "avg_duration_days",
                "avg_lead_time_days",
            ]
        )

    frame = pd.DataFrame(rows)
    grouped = (
        frame.groupby(["period_start", "year", "month", "week"], as_index=False)
        .agg(
            listing_count=("external_id", "nunique"),
            avg_duration_days=("duration_days", "mean"),
            avg_lead_time_days=("lead_time_days", "mean"),
        )
        .sort_values("period_start")
    )
    return grouped


def weekly_opportunity_timeline(facts: pd.DataFrame) -> pd.DataFrame:
    """Return one row per week, including zero-listing weeks."""
    seasonal = seasonality_frame(facts, basis="sit_dates", interval="week")
    if seasonal.empty:
        return pd.DataFrame(columns=["period_start", "listing_count"])

    first_week = seasonal["period_start"].min()
    last_week = seasonal["period_start"].max()
    all_weeks = pd.DataFrame(
        {"period_start": pd.date_range(start=first_week, end=last_week, freq="W-MON")}
    )
    timeline = all_weeks.merge(
        seasonal[["period_start", "listing_count"]],
        on="period_start",
        how="left",
    )
    timeline["listing_count"] = timeline["listing_count"].fillna(0).astype(int)
    return timeline


def _filter_in(frame: pd.DataFrame, column: str, selected_values: tuple[str, ...]) -> pd.DataFrame:
    if not selected_values:
        return frame
    return frame[frame[column].isin(selected_values)]


def _period_starts_between(
    start_value: pd.Timestamp,
    end_value: pd.Timestamp,
    *,
    interval: INTERVAL,
) -> list[pd.Timestamp]:
    if pd.isna(start_value) or pd.isna(end_value):
        return []

    start = pd.Timestamp(start_value)
    end = pd.Timestamp(end_value)
    if end < start:
        return []

    if interval == "month":
        current = pd.Timestamp(year=start.year, month=start.month, day=1)
        last = pd.Timestamp(year=end.year, month=end.month, day=1)
        starts = []
        while current <= last:
            starts.append(current)
            current += pd.DateOffset(months=1)
        return starts

    current = start.normalize() - pd.Timedelta(days=start.weekday())
    last = end.normalize() - pd.Timedelta(days=end.weekday())
    starts = []
    while current <= last:
        starts.append(current)
        current += pd.Timedelta(days=7)
    return starts
