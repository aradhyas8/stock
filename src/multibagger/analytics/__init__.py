"""Analytics module - performance calculations and reporting"""

from .compute import compute_analytics
from .report import generate_reports, print_analytics_summary

__all__ = [
    "compute_analytics",
    "generate_reports",
    "print_analytics_summary",
]
