"""Portfolio sizing and weight calculation with conviction-based approach"""

import logging
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def compute_conviction_weights(
    candidates_df: pd.DataFrame,
    config: Dict[str, float]
) -> pd.DataFrame:
    """
    Compute model weights based on conviction (upside potential).

    Args:
        candidates_df: DataFrame with 'ticker_id', 'symbol', 'upside_pct', 'market_cap'
        config: Dict with max_weight_pct, min_weight_pct

    Returns:
        DataFrame with added 'model_weight' column
    """
    if candidates_df.empty:
        return candidates_df

    max_weight = config.get('max_weight_pct', 20.0)
    min_weight = config.get('min_weight_pct', 3.0)

    # Sort by upside DESC, market_cap DESC for determinism
    candidates_df = candidates_df.sort_values(
        ['upside_pct', 'market_cap'],
        ascending=[False, False]
    ).copy()

    # Raw weight = proportional to upside
    total_upside = candidates_df['upside_pct'].sum()

    if total_upside <= 0:
        logger.warning("Total upside <= 0; using equal weights")
        candidates_df['raw_weight'] = 100.0 / len(candidates_df)
    else:
        candidates_df['raw_weight'] = (candidates_df['upside_pct'] / total_upside) * 100.0

    # Apply max cap
    candidates_df['model_weight'] = candidates_df['raw_weight'].clip(upper=max_weight)

    # Drop positions below minimum
    before_count = len(candidates_df)
    candidates_df = candidates_df[candidates_df['model_weight'] >= min_weight].copy()
    after_count = len(candidates_df)

    if after_count < before_count:
        logger.info(f"Dropped {before_count - after_count} positions below min_weight={min_weight}%")

    # Renormalize to sum ≤ 100%
    current_total = candidates_df['model_weight'].sum()

    if current_total > 100.0:
        # Scale down proportionally
        candidates_df['model_weight'] = (candidates_df['model_weight'] / current_total) * 100.0
        logger.info(f"Scaled weights down from {current_total:.1f}% to 100.0%")

    # Round to 2 decimals for determinism
    candidates_df['model_weight'] = candidates_df['model_weight'].round(2)

    final_total = candidates_df['model_weight'].sum()
    cash_pct = 100.0 - final_total

    logger.info(f"Computed weights for {len(candidates_df)} positions: total={final_total:.2f}%, cash={cash_pct:.2f}%")

    return candidates_df


def compute_held_weights(
    holdings_df: pd.DataFrame,
    prices_dict: Dict[int, float]
) -> pd.DataFrame:
    """
    Compute held weights from quantities and prices.

    Args:
        holdings_df: DataFrame with 'ticker_id', 'quantity'
        prices_dict: Dict of {ticker_id: price}

    Returns:
        DataFrame with added 'held_weight', 'current_value' columns
    """
    if holdings_df.empty:
        return holdings_df

    # If weight_pct already provided, use it
    if 'weight_pct' in holdings_df.columns and holdings_df['weight_pct'].notna().any():
        # Use provided weights
        holdings_df['held_weight'] = holdings_df['weight_pct'].fillna(0)
        logger.info("Using provided weight_pct values")
        return holdings_df

    # Otherwise compute from quantities
    if 'quantity' not in holdings_df.columns or holdings_df['quantity'].isna().all():
        raise ValueError("Cannot compute weights: no quantities or weight_pct provided")

    # Add prices
    holdings_df['current_price'] = holdings_df['ticker_id'].map(prices_dict)

    # Compute values
    holdings_df['current_value'] = holdings_df['quantity'] * holdings_df['current_price']

    # Handle missing prices
    missing_prices = holdings_df['current_price'].isna().sum()
    if missing_prices > 0:
        logger.warning(f"{missing_prices} holdings missing prices; will exclude from weight calculation")
        holdings_df = holdings_df[holdings_df['current_price'].notna()].copy()

    # Compute portfolio value
    portfolio_value = holdings_df['current_value'].sum()

    if portfolio_value <= 0:
        logger.error("Portfolio value is zero; cannot compute weights")
        holdings_df['held_weight'] = 0
        return holdings_df

    # Compute weights
    holdings_df['held_weight'] = (holdings_df['current_value'] / portfolio_value) * 100.0
    holdings_df['held_weight'] = holdings_df['held_weight'].round(2)

    logger.info(f"Computed held weights from quantities (portfolio value: ${portfolio_value:,.2f})")

    return holdings_df


def apply_sizing_caps(
    weights_df: pd.DataFrame,
    config: Dict[str, float]
) -> pd.DataFrame:
    """
    Apply max_positions, max_weight, min_weight caps.

    Args:
        weights_df: DataFrame with 'model_weight'
        config: Sizing config

    Returns:
        Filtered and capped DataFrame
    """
    max_positions = config.get('max_positions', 15)
    max_weight = config.get('max_weight_pct', 20.0)
    min_weight = config.get('min_weight_pct', 3.0)

    # Sort by weight DESC for determinism
    weights_df = weights_df.sort_values('model_weight', ascending=False).copy()

    # Apply max positions
    if len(weights_df) > max_positions:
        logger.info(f"Limiting to {max_positions} positions (had {len(weights_df)})")
        weights_df = weights_df.head(max_positions)

    # Apply weight caps
    weights_df['model_weight'] = weights_df['model_weight'].clip(lower=min_weight, upper=max_weight)

    # Renormalize
    total = weights_df['model_weight'].sum()
    if total > 100.0:
        weights_df['model_weight'] = (weights_df['model_weight'] / total) * 100.0

    weights_df['model_weight'] = weights_df['model_weight'].round(2)

    return weights_df
