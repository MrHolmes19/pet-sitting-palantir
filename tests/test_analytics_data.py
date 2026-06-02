"""Tests for analytics dashboard data transforms."""

from datetime import date

import pandas as pd

from pet_sitting_palantir.analytics.data import (
    DashboardFilters,
    duration_bucket,
    filter_listing_facts,
    pet_label,
    prepare_listing_facts,
    seasonality_frame,
    weekly_opportunity_timeline,
)


def test_duration_bucket() -> None:
    assert duration_bucket(7) == "0-7 days"
    assert duration_bucket(8) == "8-14 days"
    assert duration_bucket(30) == "15-30 days"
    assert duration_bucket(31) == "31-60 days"
    assert duration_bucket(61) == "61+ days"


def test_pet_label() -> None:
    assert pet_label(pd.Series({"dogs_count": 1, "cats_count": 0, "no_pets": False})) == "Dogs"
    assert pet_label(pd.Series({"dogs_count": 0, "cats_count": 2, "no_pets": False})) == "Cats"
    assert (
        pet_label(pd.Series({"dogs_count": 1, "cats_count": 1, "no_pets": False}))
        == "Dogs and cats"
    )
    assert pet_label(pd.Series({"dogs_count": 0, "cats_count": 0, "no_pets": True})) == "No pets"


def test_prepare_listing_facts_adds_dashboard_columns() -> None:
    facts = prepare_listing_facts(_sample_listings())

    assert facts["duration_bucket"].tolist() == ["8-14 days", "15-30 days"]
    assert facts["lead_time_days"].tolist() == [31, 24]
    assert facts["pet_label"].tolist() == ["Dogs", "Cats"]


def test_filter_listing_facts_applies_sidebar_filters() -> None:
    facts = prepare_listing_facts(_sample_listings())
    filters = DashboardFilters(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        regions=("Auckland",),
        subregions=(),
        cities=(),
        pet_labels=("Dogs",),
        duration_buckets=("8-14 days",),
        statuses=("active",),
    )

    filtered = filter_listing_facts(facts, filters)

    assert filtered["external_id"].tolist() == ["one"]


def test_empty_filter_values_include_all_values() -> None:
    facts = prepare_listing_facts(_sample_listings())
    filters = DashboardFilters(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        regions=(),
        subregions=(),
        cities=(),
        pet_labels=(),
        duration_buckets=(),
        statuses=(),
    )

    filtered = filter_listing_facts(facts, filters)

    assert filtered["external_id"].tolist() == ["one", "two"]


def test_seasonality_frame_expands_sit_dates_by_week() -> None:
    facts = prepare_listing_facts(_sample_listings().head(1))

    seasonal = seasonality_frame(facts, basis="sit_dates", interval="week")

    assert seasonal["listing_count"].sum() == 2
    assert seasonal["week"].tolist() == [2, 3]


def test_weekly_opportunity_timeline_includes_zero_listing_weeks() -> None:
    listings = _sample_listings()
    listings.loc[1, "start_date"] = "2026-01-26"
    listings.loc[1, "end_date"] = "2026-01-26"
    facts = prepare_listing_facts(listings)

    timeline = weekly_opportunity_timeline(facts)

    assert timeline["period_start"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-05",
        "2026-01-12",
        "2026-01-19",
        "2026-01-26",
    ]
    assert timeline["listing_count"].tolist() == [1, 1, 0, 1]


def _sample_listings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "external_id": "one",
                "region": "Auckland",
                "subregion": "Auckland - Central",
                "city": "Auckland CBD",
                "start_date": "2026-01-05",
                "end_date": "2026-01-18",
                "duration_days": 14,
                "dogs_count": 1,
                "cats_count": 0,
                "fish_count": 0,
                "birds_count": 0,
                "rabbits_guinea_pigs_count": 0,
                "chickens_ducks_geese_count": 0,
                "farm_animals_count": 0,
                "horses_count": 0,
                "reptiles_count": 0,
                "other_pets_count": 0,
                "no_pets": False,
                "first_seen_at": "2025-12-05 10:00:00",
                "first_seen_context": "observed",
                "status": "active",
            },
            {
                "external_id": "two",
                "region": "Wellington",
                "subregion": "Wellington",
                "city": "Island Bay",
                "start_date": "2026-02-01",
                "end_date": "2026-02-20",
                "duration_days": 20,
                "dogs_count": 0,
                "cats_count": 1,
                "fish_count": 0,
                "birds_count": 0,
                "rabbits_guinea_pigs_count": 0,
                "chickens_ducks_geese_count": 0,
                "farm_animals_count": 0,
                "horses_count": 0,
                "reptiles_count": 0,
                "other_pets_count": 0,
                "no_pets": False,
                "first_seen_at": "2026-01-08 10:00:00",
                "first_seen_context": "observed",
                "status": "active",
            },
        ]
    )
