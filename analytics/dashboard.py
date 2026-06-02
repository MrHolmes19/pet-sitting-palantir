"""Streamlit dashboard for local pet-sitting analytics snapshots."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pet_sitting_palantir.analytics.data import (
    DURATION_BUCKETS,
    DashboardFilters,
    filter_listing_facts,
    load_listing_facts,
    seasonality_frame,
    weekly_opportunity_timeline,
)

DEFAULT_DATABASE_PATH = Path(".analytics/demo.duckdb")
HEATMAP_COLOR_SCALE = "RdYlBu_r"
WEEKLY_TIMELINE_CELL_WIDTH = 34
WEEKLY_TIMELINE_MIN_WIDTH = 900
DISPLAY_COLUMNS = [
    "external_id",
    "region",
    "subregion",
    "city",
    "start_date",
    "end_date",
    "duration_days",
    "pet_label",
    "dogs_count",
    "cats_count",
    "first_seen_at",
    "lead_time_days",
    "status",
    "url",
]


def main() -> None:
    """Render the Streamlit dashboard."""
    st.set_page_config(page_title="Pet Sitting Analytics", layout="wide")
    st.title("Pet Sitting Analytics")

    database_path = Path(st.sidebar.text_input("DuckDB path", str(DEFAULT_DATABASE_PATH)))
    if st.sidebar.button("Reload data"):
        st.cache_data.clear()

    try:
        facts = _load_data(str(database_path))
    except FileNotFoundError:
        st.error(f"Analytics database not found: {database_path}")
        st.code(
            "uv --cache-dir .uv-cache run python -m pet_sitting_palantir.analytics "
            "generate-demo"
        )
        return

    filters = _sidebar_filters(facts)
    filtered = filter_listing_facts(facts, filters)

    if filtered.empty:
        st.warning("No listings match the current filters.")
        return

    (
        overview_tab,
        seasonality_tab,
        lead_time_tab,
        location_tab,
        auckland_tab,
        explorer_tab,
    ) = st.tabs(
        [
            "Overview",
            "Seasonality",
            "Lead time",
            "Location",
            "Auckland Central",
            "Data explorer",
        ]
    )

    with overview_tab:
        _overview(filtered)

    with seasonality_tab:
        _seasonality(filtered)

    with lead_time_tab:
        _lead_time(filtered)

    with location_tab:
        _location(filtered)

    with auckland_tab:
        auckland_filters = DashboardFilters(
            start_date=filters.start_date,
            end_date=filters.end_date,
            regions=("Auckland",),
            subregions=("Auckland - Central",),
            cities=(),
            pet_labels=filters.pet_labels,
            duration_buckets=filters.duration_buckets,
            statuses=filters.statuses,
        )
        _auckland_central(filter_listing_facts(facts, auckland_filters))

    with explorer_tab:
        _data_explorer(filtered)


@st.cache_data(show_spinner=False)
def _load_data(database_path: str) -> pd.DataFrame:
    return load_listing_facts(Path(database_path))


def _sidebar_filters(facts: pd.DataFrame) -> DashboardFilters:
    st.sidebar.header("Filters")
    minimum_date = facts["start_date"].min().date()
    maximum_date = facts["start_date"].max().date()
    selected_range = st.sidebar.date_input(
        "Sit date range",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
    )
    if len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date, end_date = minimum_date, maximum_date

    regions = _multiselect_all("Region", facts["region"])
    subregion_frame = facts if not regions else facts[facts["region"].isin(regions)]
    subregions = _multiselect_all("Subregion", subregion_frame["subregion"])
    city_frame = (
        subregion_frame
        if not subregions
        else subregion_frame[subregion_frame["subregion"].isin(subregions)]
    )
    cities = _multiselect_all("City", city_frame["city"])
    pet_labels = _multiselect_all("Pet type", facts["pet_label"])
    duration_buckets = tuple(
        st.sidebar.multiselect(
            "Sit length",
            options=list(DURATION_BUCKETS),
            default=(),
            help="Leave empty to include all sit lengths.",
        )
    )
    statuses = _multiselect_all("Status", facts["status"])

    return DashboardFilters(
        start_date=start_date,
        end_date=end_date,
        regions=regions,
        subregions=subregions,
        cities=cities,
        pet_labels=pet_labels,
        duration_buckets=duration_buckets,
        statuses=statuses,
    )


def _overview(frame: pd.DataFrame) -> None:
    lead_times = _valid_lead_times(frame)
    metrics = st.columns(5)
    metrics[0].metric("Listings", f"{len(frame):,}")
    metrics[1].metric("Average length", _format_days(frame["duration_days"].mean()))
    metrics[2].metric("Median length", _format_days(frame["duration_days"].median()))
    metrics[3].metric("Average lead", _format_days(lead_times.mean()))
    metrics[4].metric("Median lead", _format_days(lead_times.median()))

    left, right = st.columns(2)
    with left:
        region_counts = _count_by(frame, "region", limit=12)
        st.plotly_chart(
            px.bar(
                region_counts,
                x="listings",
                y="region",
                orientation="h",
                title="Listings by region",
            ).update_layout(yaxis={"categoryorder": "total ascending"}),
            width="stretch",
        )
    with right:
        pet_counts = _count_by(frame, "pet_label", limit=10)
        st.plotly_chart(
            px.pie(
                pet_counts,
                names="pet_label",
                values="listings",
                title="Pet mix",
                hole=0.35,
            ),
            width="stretch",
        )


def _seasonality(frame: pd.DataFrame) -> None:
    controls = st.columns(2)
    interval_label = controls[0].selectbox("Interval", ["Month", "Week"])
    metric_label = controls[1].selectbox(
        "Metric",
        ["Listing count", "Average duration", "Average lead time"],
    )

    interval = "month" if interval_label == "Month" else "week"
    metric_column = {
        "Listing count": "listing_count",
        "Average duration": "avg_duration_days",
        "Average lead time": "avg_lead_time_days",
    }[metric_label]
    metric_title = {
        "Listing count": "Listings",
        "Average duration": "Average duration days",
        "Average lead time": "Average lead time days",
    }[metric_label]

    seasonal = seasonality_frame(frame, basis="sit_dates", interval=interval)
    if seasonal.empty:
        st.warning("No seasonality data available for the current filters.")
        return

    x_column = "month" if interval == "month" else "week"
    heatmap = seasonal.pivot_table(
        index="year",
        columns=x_column,
        values=metric_column,
        aggfunc="sum" if metric_column == "listing_count" else "mean",
        fill_value=0,
    )
    st.plotly_chart(
        px.imshow(
            heatmap,
            aspect="auto",
            color_continuous_scale=HEATMAP_COLOR_SCALE,
            labels={"x": interval_label, "y": "Year", "color": metric_title},
            text_auto=True,
            title=f"{metric_label} by {interval_label.lower()}",
        ),
        width="stretch",
    )

    st.plotly_chart(
        px.bar(
            seasonal,
            x="period_start",
            y=metric_column,
            title=f"{metric_label} over time",
            labels={"period_start": "Period", metric_column: metric_title},
        ),
        width="stretch",
    )


def _lead_time(frame: pd.DataFrame) -> None:
    include_baseline = st.checkbox("Include baseline rows", value=False)
    lead_frame = frame[frame["lead_time_days"].notna() & (frame["lead_time_days"] >= 0)].copy()
    if not include_baseline:
        lead_frame = lead_frame[lead_frame["first_seen_context"] != "baseline"]

    if lead_frame.empty:
        st.warning("No lead-time data available for the current filters.")
        return

    lead_times = lead_frame["lead_time_days"]
    metrics = st.columns(4)
    metrics[0].metric("Average", _format_days(lead_times.mean()))
    metrics[1].metric("Median", _format_days(lead_times.median()))
    metrics[2].metric("P25", _format_days(lead_times.quantile(0.25)))
    metrics[3].metric("P75", _format_days(lead_times.quantile(0.75)))

    st.plotly_chart(
        px.histogram(
            lead_frame,
            x="lead_time_days",
            nbins=35,
            marginal="box",
            title="Lead-time distribution",
            labels={"lead_time_days": "Days before sit start"},
        ),
        width="stretch",
    )

    st.plotly_chart(
        px.box(
            lead_frame,
            x="duration_bucket",
            y="lead_time_days",
            category_orders={"duration_bucket": list(DURATION_BUCKETS)},
            title="Lead time by sit length",
            labels={"duration_bucket": "Sit length", "lead_time_days": "Lead time days"},
        ),
        width="stretch",
    )


def _location(frame: pd.DataFrame) -> None:
    level_label = st.segmented_control(
        "Location level",
        options=["Region", "Subregion", "City"],
        default="Region",
    )
    location_frame = _location_focus_frame(frame, level_label)
    if location_frame.empty:
        st.warning("No listings match the selected location focus.")
        return

    limit = st.slider("Rows", min_value=5, max_value=30, value=15, step=5)
    column = level_label.lower()
    counts = _count_by(location_frame, column, limit=limit)

    st.plotly_chart(
        px.bar(
            counts,
            x="listings",
            y=column,
            orientation="h",
            title=f"Listings by {level_label.lower()}",
        ).update_layout(yaxis={"categoryorder": "total ascending"}),
        width="stretch",
    )

    stacked = (
        location_frame.groupby([column, "pet_label"], as_index=False)
        .agg(listings=("external_id", "nunique"))
        .sort_values("listings", ascending=False)
    )
    top_locations = counts[column].tolist()
    stacked = stacked[stacked[column].isin(top_locations)]
    st.plotly_chart(
        px.bar(
            stacked,
            x=column,
            y="listings",
            color="pet_label",
            title=f"Pet mix by {level_label.lower()}",
            labels={column: level_label, "pet_label": "Pet type"},
        ),
        width="stretch",
    )


def _auckland_central(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.warning("No Auckland Central listings match the current non-location filters.")
        return

    metrics = st.columns(4)
    lead_times = _valid_lead_times(frame)
    metrics[0].metric("Listings", f"{len(frame):,}")
    metrics[1].metric("Long sits", f"{int(frame['has_long_sit'].sum()):,}")
    metrics[2].metric("Average length", _format_days(frame["duration_days"].mean()))
    metrics[3].metric("Median lead", _format_days(lead_times.median()))

    _auckland_weekly_opportunities(frame)

    listing_trend = seasonality_frame(frame, basis="sit_dates", interval="month")
    st.plotly_chart(
        px.line(
            listing_trend,
            x="period_start",
            y="listing_count",
            markers=True,
            title="Listings over time",
            labels={"period_start": "Month", "listing_count": "Listings"},
        ),
        width="stretch",
    )


def _data_explorer(frame: pd.DataFrame) -> None:
    display_frame = frame[DISPLAY_COLUMNS].sort_values("start_date").copy()
    st.dataframe(display_frame, width="stretch", hide_index=True)
    st.download_button(
        "Download CSV",
        data=display_frame.to_csv(index=False),
        file_name="pet_sitting_filtered_listings.csv",
        mime="text/csv",
    )


def _auckland_weekly_opportunities(frame: pd.DataFrame) -> None:
    timeline = weekly_opportunity_timeline(frame)
    if timeline.empty:
        st.warning("No weekly Auckland Central timeline is available.")
        return

    timeline = _select_timeline_year(timeline)
    week_count = len(timeline)
    chart_width = max(WEEKLY_TIMELINE_MIN_WIDTH, week_count * WEEKLY_TIMELINE_CELL_WIDTH)
    week_labels = timeline["period_start"].dt.strftime("%d/%m").tolist()
    hover_labels = timeline["period_start"].dt.strftime("%d %b %Y").tolist()
    counts = timeline["listing_count"].tolist()

    st.subheader("Auckland Central weekly opportunities")
    st.caption("Week starting")
    _heatmap_legend(min(counts), max(counts))

    figure = go.Figure(
        data=go.Heatmap(
            z=[counts],
            x=list(range(week_count)),
            y=["Listings"],
            text=[counts],
            customdata=[hover_labels],
            colorscale=HEATMAP_COLOR_SCALE,
            xgap=2,
            ygap=2,
            showscale=False,
            hovertemplate="Week starting %{customdata}<br>Listings: %{z}<extra></extra>",
        )
    )
    figure.update_layout(
        width=chart_width,
        height=185,
        margin={"l": 20, "r": 20, "t": 12, "b": 72},
        xaxis={
            "tickmode": "array",
            "tickvals": list(range(week_count)),
            "ticktext": week_labels,
            "tickangle": -45,
            "title": "",
            "showgrid": True,
            "gridwidth": 1,
            "gridcolor": "rgba(90, 110, 130, 0.28)",
        },
        yaxis={"showticklabels": False, "title": ""},
    )

    for boundary_index in _month_boundary_indices(timeline):
        figure.add_shape(
            type="line",
            x0=boundary_index - 0.5,
            x1=boundary_index - 0.5,
            y0=-0.5,
            y1=0.5,
            xref="x",
            yref="y",
            line={"color": "rgba(20, 30, 45, 0.85)", "width": 3},
        )

    _scrollable_plotly_chart(figure, height=225)


def _select_timeline_year(timeline: pd.DataFrame) -> pd.DataFrame:
    years = sorted(timeline["period_start"].dt.year.unique().tolist())
    if len(years) <= 1:
        return timeline

    selected_year = st.selectbox("Weekly year", years, index=len(years) - 1)
    return timeline[timeline["period_start"].dt.year == selected_year]


def _heatmap_legend(minimum_count: int, maximum_count: int) -> None:
    st.markdown(
        f"""
        <div style="
          display:flex;
          align-items:center;
          gap:10px;
          max-width:520px;
          margin: 0 0 8px 0;
        ">
          <span style="font-size:0.85rem; color:#425466;">Quiet: {minimum_count}</span>
          <div style="
            height: 12px;
            flex: 1;
            border-radius: 3px;
            background: linear-gradient(90deg, #4575b4 0%, #ffffbf 50%, #d73027 100%);
            border: 1px solid rgba(40, 50, 65, 0.22);
          "></div>
          <span style="font-size:0.85rem; color:#425466;">Busy: {maximum_count}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _month_boundary_indices(timeline: pd.DataFrame) -> list[int]:
    months = timeline["period_start"].dt.month.tolist()
    return [index for index in range(1, len(months)) if months[index] != months[index - 1]]


def _scrollable_plotly_chart(figure: go.Figure, *, height: int) -> None:
    html = figure.to_html(full_html=False, include_plotlyjs=True)
    st.iframe(
        f"""
        <div style="width: 100%; overflow-x: auto; padding-bottom: 8px;">
          {html}
        </div>
        """,
        height=height,
    )


def _multiselect_all(label: str, values: pd.Series) -> tuple[str, ...]:
    options = sorted(value for value in values.dropna().unique().tolist())
    return tuple(
        st.sidebar.multiselect(
            label,
            options=options,
            default=(),
            help="Leave empty to include all.",
        )
    )


def _location_focus_frame(frame: pd.DataFrame, level_label: str) -> pd.DataFrame:
    focused = frame
    if level_label in {"Subregion", "City"}:
        region_options = ["All"] + sorted(frame["region"].dropna().unique().tolist())
        selected_region = st.selectbox("Focus region", region_options)
        if selected_region != "All":
            focused = focused[focused["region"] == selected_region]

    if level_label == "City":
        subregion_options = ["All"] + sorted(focused["subregion"].dropna().unique().tolist())
        selected_subregion = st.selectbox("Focus subregion", subregion_options)
        if selected_subregion != "All":
            focused = focused[focused["subregion"] == selected_subregion]

    return focused


def _count_by(frame: pd.DataFrame, column: str, *, limit: int) -> pd.DataFrame:
    return (
        frame.groupby(column, as_index=False)
        .agg(listings=("external_id", "nunique"))
        .sort_values("listings", ascending=False)
        .head(limit)
    )


def _valid_lead_times(frame: pd.DataFrame) -> pd.Series:
    return frame.loc[
        frame["lead_time_days"].notna() & (frame["lead_time_days"] >= 0),
        "lead_time_days",
    ]


def _format_days(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:.0f} days"


if __name__ == "__main__":
    main()
