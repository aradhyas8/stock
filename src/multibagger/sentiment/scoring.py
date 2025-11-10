"""Sentiment risk scoring (MVP: Stub implementation)

This module provides stub implementations for sentiment scoring.
In the full implementation, this will:
- Query NewsAPI for ticker mentions
- Scan headlines for adverse keywords
- Calculate severity scores
- Detect recent adverse events
"""

import logging

logger = logging.getLogger(__name__)


def compute_sentiment_score(ticker_id: int, symbol: str, as_of: str, config: dict = None) -> float:
    """
    Compute sentiment risk score (0-100).

    MVP Implementation: Returns 0.0 (stub)

    In full implementation, will:
    - Query NewsAPI for ticker mentions (30-day lookback)
    - Scan headlines for adverse keywords (fraud, bankruptcy, lawsuit, etc.)
    - Weight by keyword severity
    - Normalize to 0-100 risk score

    Args:
        ticker_id: Ticker ID from database
        symbol: Ticker symbol (e.g., "AAPL")
        as_of: YYYY-MM format date
        config: Optional configuration dict

    Returns:
        Risk score from 0 (low risk) to 100 (high risk)
        MVP: Always returns 0.0
    """
    logger.debug(f"Sentiment scoring (stub) for {symbol}, as_of={as_of}")
    return 0.0


def fetch_news_data(symbol: str, as_of: str, config: dict) -> dict:
    """
    Fetch news data (stub).

    Returns:
        Empty dict (stub implementation)
    """
    logger.debug(f"News fetch (stub) for {symbol}")
    return {}
