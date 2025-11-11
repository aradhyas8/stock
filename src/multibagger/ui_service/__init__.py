"""UI Service Layer - Thin facade for Streamlit app"""

from .service import (
    get_latest_snapshot,
    get_health_summary,
    list_stage_artifacts,
    run_monthly,
    run_daily,
    get_research_table,
    reconcile_portfolio,
    portfolio_show,
    monitor_daily,
    analytics_compute,
    ops_health,
    ops_rotate,
)

__all__ = [
    "get_latest_snapshot",
    "get_health_summary",
    "list_stage_artifacts",
    "run_monthly",
    "run_daily",
    "get_research_table",
    "reconcile_portfolio",
    "portfolio_show",
    "monitor_daily",
    "analytics_compute",
    "ops_health",
    "ops_rotate",
]
