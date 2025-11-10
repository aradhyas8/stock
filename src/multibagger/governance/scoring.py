"""Governance risk scoring (MVP: Stub implementation)

This module provides stub implementations for governance scoring.
In the full implementation, this will:
- Fetch SEC EDGAR Form 4 data for US companies
- Fetch MCA data for India companies
- Calculate insider selling metrics
- Detect promoter pledge levels
"""

import logging

logger = logging.getLogger(__name__)


def compute_governance_score(ticker_id: int, as_of: str, config: dict = None) -> float:
    """
    Compute governance risk score (0-100).

    MVP Implementation: Returns 0.0 (stub)

    In full implementation, will:
    - Route by exchange (US → EDGAR, India → MCA)
    - Fetch insider transactions (90-day lookback)
    - Calculate net insider selling %
    - Check promoter pledge levels
    - Normalize to 0-100 risk score

    Args:
        ticker_id: Ticker ID from database
        as_of: YYYY-MM format date
        config: Optional configuration dict

    Returns:
        Risk score from 0 (low risk) to 100 (high risk)
        MVP: Always returns 0.0
    """
    logger.debug(f"Governance scoring (stub) for ticker_id={ticker_id}, as_of={as_of}")
    return 0.0


def fetch_insider_data(ticker_id: int, as_of: str, config: dict) -> dict:
    """
    Fetch insider trading data (stub).

    Returns:
        Empty dict (stub implementation)
    """
    logger.debug(f"Insider data fetch (stub) for ticker_id={ticker_id}")
    return {}
