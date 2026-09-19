"""Reusable deterministic fixtures for dashboard and workflow acceptance."""

from .dashboard_s02 import (
    SyntheticDashboardFixture,
    build_s02_dashboard_fixture,
    set_s02_live_running,
)

__all__ = ["SyntheticDashboardFixture", "build_s02_dashboard_fixture", "set_s02_live_running"]
