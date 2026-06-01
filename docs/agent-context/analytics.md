# Analytics

This file owns the analytics and dashboard direction. Read it only when changing
analytics data refresh, synthetic analytics data, metric definitions, dashboard
UI, charting, or related dependencies.

Do not read this file for scraper, alerting, scheduling, or backup-only tasks
unless the task also affects analytics.

## Goal

Build a simple local analytics dashboard for KiwiHouseSitters data that can be
used before real history exists, then switched to real production snapshots once
enough data has accumulated.

The dashboard should help answer practical questions:

- Which weeks and months have more sitting opportunities?
- Which areas produce more opportunities?
- How do pet type, location, and sit length change those patterns?
- How far in advance are listings usually posted before the sit starts?
- When are long Auckland Central sits abundant or scarce?

## Non-Goals

- Do not build a custom React/frontend application for the first version.
- Do not add a hosted dashboard for the first version.
- Do not introduce Tableau, Power BI, or a separate BI platform unless the local
  dashboard proves insufficient.
- Do not add listing version/history tables for this analytics phase.
- Do not store many permanent computed metric tables early.

The first version should be local, command-driven, and easy for agents to extend.

## Recommended Stack

- DuckDB: local analytics database stored as a single file.
- Streamlit: local Python dashboard server and UI framework.
- Plotly: interactive charts rendered inside Streamlit.
- Pandas: dataframe bridge where useful for chart construction.

Production PostgreSQL/Supabase remains the source of truth. DuckDB is only a
refreshable analytics copy.

```text
Supabase/PostgreSQL
        |
        | refresh command
        v
.analytics/pet_sitting.duckdb
        |
        | Streamlit queries
        v
local browser dashboard
```

Before enough real data exists, use generated data:

```text
synthetic data generator
        |
        v
.analytics/demo.duckdb
        |
        v
same local dashboard
```

## UI Model

Streamlit owns the local web UI. It is not a separate frontend app consuming
backend REST endpoints.

The dashboard is a Python script that declares controls, queries data, builds
Plotly figures, and renders them. Running Streamlit starts a local web server,
usually at `http://localhost:8501`. When the user changes a filter, Streamlit
reruns the script and redraws the charts.

The intended UI is simple and functional:

- Sidebar filters for data source, date range, location, pet type, and sit
  length.
- Main page tabs for overview, seasonality, lead time, location, Auckland
  Central, and data explorer.
- Numeric outputs using metric cards.
- Interactive Plotly charts for heatmaps, bars, histograms, and distributions.

Avoid spending effort on custom styling unless usability requires it.

## Initial Dashboard Tabs

### Overview

Show high-level numeric summaries:

- Total listings in the filtered dataset.
- Listings in the selected date range.
- Average and median sit length.
- Average and median lead time.
- Top regions, subregions, and cities.
- Pet mix summary.

### Seasonality

Primary decision-support view for high and low seasons.

Charts:

- Month-by-year heatmap.
- Week-of-year-by-year heatmap.
- Weekly or monthly bar chart.

Filters should allow segmentation by:

- Region.
- Subregion.
- City.
- Pet type.
- Duration bucket.
- Date basis.

Supported date bases:

- Sit dates: opportunities that occur during each week or month.
- First seen date: listings first discovered during each week or month.

For the user's "hot weeks" question, default to sit dates because the decision
is about when opportunities occur. Include first-seen charts because they show
when those opportunities tend to appear.

### Lead Time

Analyze how far in advance listings appear.

Lead time is:

```text
start_date - first_seen_at date
```

Charts:

- Histogram of lead-time days.
- Distribution curve if useful.
- Box plot by duration bucket, pet type, or location.
- Scatter plot of lead time vs sit length if useful.

Show average, median, p25, and p75 for filtered data.

Exclude rows missing `start_date` or `first_seen_at`. Consider excluding
`first_seen_context = 'baseline'` from lead-time averages by default because
baseline listings may have been live before the system first observed them.

### Location

Compare market volume by place.

Charts:

- Ranked bar chart by region.
- Ranked bar chart by subregion.
- Ranked bar chart by city.
- Optional stacked bars by pet type.

Do not build a geographic map in the first version. Current data has location
names, not coordinates.

### Auckland Central

Focused view for the highest-priority market.

Default filters:

- `region = 'Auckland'`
- `subregion = 'Auckland - Central'`

Charts:

- Weekly heatmap for sitting opportunities.
- Long-sit trend over time.
- Lead-time distribution for Auckland Central.
- Pet-type breakdown.

This page should help decide when to accept scarce opportunities versus wait for
better ones.

### Data Explorer

Show filtered listing rows and allow CSV export of the current filtered data.

Useful columns:

- external id
- region
- subregion
- city
- start date
- end date
- duration days
- pet counts
- first seen at
- status
- url

## Metric Definitions

### Listing Count

Count distinct `external_id` values unless a query clearly needs internal row
ids. The current database stores one row per listing.

### Sit Length

Use `duration_days` when available. If missing and both dates exist, derive:

```text
end_date - start_date + 1
```

Duration buckets for the first version:

- 0-7 days
- 8-14 days
- 15-30 days
- 31-60 days
- 61+ days

### Sit-Week Count

For seasonality by sit dates, count a listing in every calendar week overlapped
by its date range.

This means a two-month sit contributes to multiple weeks. That is intentional
for "how many opportunities exist during this week" charts.

When the question is "how many listings started this week", use `start_date`
only and label the chart clearly.

### First-Seen Count

For posting/discovery activity, group by `first_seen_at`.

This answers "when did opportunities appear?" rather than "when do the sitting
dates happen?"

### Lead Time

Lead time is measured in days from the first system observation to the sit start:

```text
date(start_date) - date(first_seen_at)
```

Rows with negative lead time should be treated as data-quality outliers and
excluded or shown separately.

### Pet Type

Pet categories are overlapping. A listing with dogs and cats counts in both dog
and cat filters.

For a single display label, use a simple derived label such as:

- Dogs
- Cats
- Dogs and cats
- Mixed pets
- No pets
- Other

Do not make totals by pet type look mutually exclusive unless the query uses the
single display label.

## Synthetic Data

Build the dashboard against generated data first.

The generator should create enough data to make filters and charts meaningful,
for example two or three years of listings. It should intentionally include
seasonal patterns:

- More opportunities in summer and around Christmas/New Year.
- More long sits around holidays.
- Auckland Central and nearby Auckland areas denser than smaller regions.
- Cats, dogs, mixed pets, and no-pet listings.
- Longer lead times for longer sits.
- Some short-notice listings.

Generated data should match the analytics-facing columns used from `listings` so
the same dashboard can run against demo and real data.

## Commands To Add

Use `uv` for command execution.

Suggested commands:

```bash
uv run python -m pet_sitting_palantir.analytics generate-demo
uv run python -m pet_sitting_palantir.analytics refresh --source production
uv run streamlit run analytics/dashboard.py
```

Small wrapper scripts may be added later for convenience, for example:

```text
scripts/analytics-generate-demo.sh
scripts/analytics-refresh.sh
scripts/analytics-dashboard.sh
```

Production refresh must read database credentials from the existing environment
configuration pattern. Do not hardcode production database URLs in analytics
code.

## Implementation Sequence

1. Add analytics dependencies.
2. Add a synthetic data generator that writes `.analytics/demo.duckdb`.
3. Build the Streamlit dashboard against demo data.
4. Add reusable analytics query helpers.
5. Add a production refresh command that writes `.analytics/pet_sitting.duckdb`.
6. Add dashboard source selection between demo and real snapshot.
7. Add CSV export from the data explorer.
8. Refine metric definitions only after using the dashboard with real workflows.

## Testing And Verification

For docs-only analytics changes, do not run tests unless generated docs or
schemas are involved.

For analytics code changes:

- Unit-test metric bucketing and date expansion logic.
- Test synthetic data generation shape.
- Prefer targeted tests before running the full suite.
- Manually run the dashboard when UI behavior changes.

