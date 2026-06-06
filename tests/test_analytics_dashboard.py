"""Tests for dashboard-only helpers."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_DASHBOARD_PATH = Path(__file__).parent.parent / "analytics" / "dashboard.py"
_DASHBOARD_SPEC = spec_from_file_location("analytics_dashboard", _DASHBOARD_PATH)
assert _DASHBOARD_SPEC is not None
assert _DASHBOARD_SPEC.loader is not None
_DASHBOARD = module_from_spec(_DASHBOARD_SPEC)
_DASHBOARD_SPEC.loader.exec_module(_DASHBOARD)
_format_days = _DASHBOARD._format_days


def test_format_days_handles_numeric_value() -> None:
    assert _format_days(12.4) == "12 days"


def test_format_days_handles_missing_value() -> None:
    assert _format_days(float("nan")) == "-"
