"""Portfolio reconciliation - diff holdings vs model candidates"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.common.sql_utils import build_in_clause_params
from multibagger.config import Config
from multibagger.database.schema import get_engine

from .loader import load_holdings, validate_holdings
from .matcher import match_holdings_to_tickers
from .sizing import compute_conviction_weights, compute_held_weights

logger = logging.getLogger(__name__)


def load_model_candidates(
    as_of: str,
    output_dir: str,
    config: Dict[str, any]
) -> pd.DataFrame:
    """
    Load top candidates from Stage 4 research results.

    Args:
        as_of: YYYY-MM date
        output_dir: Snapshots directory
        config: Portfolio config with top_n_candidates

    Returns:
        DataFrame with top candidates (already filtered for failures)
    """
    research_csv = Path(output_dir) / as_of / f"stage_research_{as_of}.csv"

    if not research_csv.exists():
        raise FileNotFoundError(
            f"Research results not found: {research_csv}. "
            f"Run 'screen research --as-of {as_of}' first."
        )

    research_df = pd.read_csv(research_csv)
    logger.info(f"Loaded {len(research_df)} research results from {research_csv}")

    # Join with risk_flags to check for failures
    engine = get_engine()
    with Session(engine) as session:
        ticker_ids = research_df['ticker_id'].tolist()

        if not ticker_ids:
            logger.warning("No candidates in research results")
            return pd.DataFrame()

        placeholders, params = build_in_clause_params(ticker_ids, 'ticker')
        params['as_of'] = as_of

        query = text(f"""
            SELECT ticker_id, first_fail_reason
            FROM risk_flags
            WHERE ticker_id IN ({placeholders})
              AND as_of_date = :as_of
        """)

        result = session.execute(query, params)
        risk_flags_df = pd.DataFrame(result.fetchall(), columns=['ticker_id', 'first_fail_reason'])

    # Merge with research
    research_df = research_df.merge(risk_flags_df, on='ticker_id', how='left')

    # Exclude any with failures
    clean_df = research_df[research_df['first_fail_reason'].isna()].copy()

    excluded_count = len(research_df) - len(clean_df)
    if excluded_count > 0:
        logger.info(f"Excluded {excluded_count} candidates with red flags")

    # Sort by upside DESC, market_cap DESC
    clean_df = clean_df.sort_values(
        ['upside_pct', 'market_cap'],
        ascending=[False, False]
    )

    # Take top N
    top_n = config.get('top_n_candidates', 15)
    top_candidates = clean_df.head(top_n).copy()

    logger.info(f"Selected top {len(top_candidates)} candidates (top_n={top_n})")

    return top_candidates


def fetch_month_end_prices(
    session: Session,
    ticker_ids: List[int],
    as_of: str
) -> Dict[int, float]:
    """
    Fetch most recent prices as of month-end.

    Args:
        session: DB session
        ticker_ids: List of ticker IDs
        as_of: YYYY-MM date

    Returns:
        Dict of {ticker_id: price}
    """
    if not ticker_ids:
        return {}

    # Month-end date
    as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d")

    placeholders, params = build_in_clause_params(ticker_ids, 'ticker')
    params['as_of_date'] = as_of_date

    query = text(f"""
        WITH ranked_prices AS (
            SELECT
                ticker_id,
                adj_close,
                date,
                ROW_NUMBER() OVER (PARTITION BY ticker_id ORDER BY date DESC) as rn
            FROM prices
            WHERE ticker_id IN ({placeholders})
              AND date <= :as_of_date
        )
        SELECT ticker_id, adj_close
        FROM ranked_prices
        WHERE rn = 1
    """)

    result = session.execute(query, params)
    prices_dict = {row[0]: float(row[1]) for row in result.fetchall()}

    logger.info(f"Fetched prices for {len(prices_dict)}/{len(ticker_ids)} tickers")

    return prices_dict


def compute_reconciliation_diff(
    holdings_df: pd.DataFrame,
    model_df: pd.DataFrame,
    config: Dict[str, float]
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Compare holdings vs model and generate actions.

    Args:
        holdings_df: DataFrame with 'ticker_id', 'symbol', 'held_weight'
        model_df: DataFrame with 'ticker_id', 'symbol', 'model_weight'
        config: Dict with drift_tolerance_pct

    Returns:
        Tuple of (actions_df, stats_dict)
    """
    drift_tolerance = config.get('drift_tolerance_pct', 2.0)

    # Full outer join
    merged = pd.merge(
        holdings_df[['ticker_id', 'symbol', 'held_weight']],
        model_df[['ticker_id', 'symbol', 'model_weight']],
        on='ticker_id',
        how='outer',
        suffixes=('_held', '_model')
    )

    # Fill NaNs
    merged['held_weight'] = merged['held_weight'].fillna(0)
    merged['model_weight'] = merged['model_weight'].fillna(0)
    merged['symbol'] = merged['symbol_held'].fillna(merged['symbol_model'])

    # Compute delta
    merged['delta_weight'] = merged['model_weight'] - merged['held_weight']

    # Determine action
    def determine_action(row):
        held = row['held_weight']
        model = row['model_weight']
        delta = row['delta_weight']

        if held == 0 and model > 0:
            return 'BUY', f"New position (model weight {model:.1f}%)"
        elif held > 0 and model == 0:
            return 'SELL', f"Removed from model (held {held:.1f}%)"
        elif abs(delta) <= drift_tolerance:
            return 'HOLD', f"Within drift tolerance (±{drift_tolerance}%)"
        elif delta > 0:
            # Underweight
            return 'ADD', f"Underweight by {abs(delta):.1f}%"
        else:
            # Overweight
            return 'TRIM', f"Overweight by {abs(delta):.1f}%"

    merged[['action', 'reason']] = merged.apply(
        lambda row: pd.Series(determine_action(row)),
        axis=1
    )

    # Round for display
    merged['held_weight'] = merged['held_weight'].round(2)
    merged['model_weight'] = merged['model_weight'].round(2)
    merged['delta_weight'] = merged['delta_weight'].round(2)

    # Sort by action priority (BUY, SELL, TRIM, ADD, HOLD), then symbol
    action_priority = {'BUY': 1, 'SELL': 2, 'TRIM': 3, 'ADD': 4, 'HOLD': 5}
    merged['action_priority'] = merged['action'].map(action_priority)
    merged = merged.sort_values(['action_priority', 'symbol'])

    # Compute stats
    stats = {
        'BUY': (merged['action'] == 'BUY').sum(),
        'SELL': (merged['action'] == 'SELL').sum(),
        'TRIM': (merged['action'] == 'TRIM').sum(),
        'ADD': (merged['action'] == 'ADD').sum(),
        'HOLD': (merged['action'] == 'HOLD').sum(),
    }

    # Compute turnover (sum of absolute deltas for trades only)
    trades = merged[merged['action'].isin(['BUY', 'SELL', 'TRIM', 'ADD'])]
    turnover_pct = trades['delta_weight'].abs().sum()

    stats['turnover_pct'] = round(turnover_pct, 2)

    logger.info(f"Reconciliation: {stats}")

    return merged, stats


def reconcile_portfolio(
    config: Config,
    as_of: str,
    holdings_file: str,
    output_dir: str = "snapshots",
    top_n: int = 15
) -> Dict[str, any]:
    """
    Main reconciliation function.

    Args:
        config: System config
        as_of: YYYY-MM date
        holdings_file: Path to holdings CSV/JSON
        output_dir: Output directory
        top_n: Top N candidates from research

    Returns:
        Dict with reconciliation results
    """
    logger.info(f"Starting portfolio reconciliation for {as_of}")

    # Portfolio config
    portfolio_config = config.get('portfolio', {}) if hasattr(config, 'get') else {}
    portfolio_config['top_n_candidates'] = top_n

    # Load holdings
    holdings_df = load_holdings(holdings_file)
    holdings_summary = validate_holdings(holdings_df)

    logger.info(f"Loaded {holdings_summary['total_holdings']} holdings")

    # Load model candidates
    model_df = load_model_candidates(as_of, output_dir, portfolio_config)

    if model_df.empty:
        logger.error("No model candidates available")
        return {
            'status': 'error',
            'reason': 'No research candidates found',
            'actions': pd.DataFrame(),
            'unmatched': pd.DataFrame()
        }

    # Match holdings to tickers
    engine = get_engine()
    with Session(engine) as session:
        holdings_symbols = holdings_df[['symbol', 'exchange']].to_dict('records')
        match_results = match_holdings_to_tickers(session, holdings_symbols)

        # Add ticker_id to holdings
        holdings_df['ticker_id'] = holdings_df['symbol'].map(
            lambda s: match_results[s].get('ticker_id')
        )

        # Separate matched and unmatched
        matched_holdings = holdings_df[holdings_df['ticker_id'].notna()].copy()
        unmatched_holdings = holdings_df[holdings_df['ticker_id'].isna()].copy()

        if not unmatched_holdings.empty:
            logger.warning(f"{len(unmatched_holdings)} holdings could not be matched")
            # Add match reasons
            unmatched_holdings['reason'] = unmatched_holdings['symbol'].map(
                lambda s: match_results[s].get('reason', 'Unknown')
            )

        # Fetch prices for weight calculation
        all_ticker_ids = list(matched_holdings['ticker_id'].unique()) + list(model_df['ticker_id'].unique())
        prices_dict = fetch_month_end_prices(session, all_ticker_ids, as_of)

    # Compute held weights
    if holdings_summary['needs_pricing']:
        matched_holdings = compute_held_weights(matched_holdings, prices_dict)
    else:
        # Use provided weights
        if 'weight_pct' in matched_holdings.columns:
            matched_holdings['held_weight'] = matched_holdings['weight_pct']
        else:
            logger.error("Cannot determine held weights")
            matched_holdings['held_weight'] = 0

    # Compute model weights
    model_df = compute_conviction_weights(model_df, portfolio_config)

    # Compute diff
    actions_df, stats = compute_reconciliation_diff(
        matched_holdings,
        model_df,
        portfolio_config
    )

    # Prepare results
    results = {
        'status': 'success',
        'as_of_date': as_of,
        'holdings_count': len(holdings_df),
        'matched_count': len(matched_holdings),
        'unmatched_count': len(unmatched_holdings),
        'model_positions': len(model_df),
        'actions': actions_df,
        'unmatched': unmatched_holdings,
        'stats': stats
    }

    logger.info("Portfolio reconciliation complete")

    return results
