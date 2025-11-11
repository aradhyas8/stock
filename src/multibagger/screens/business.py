"""Stage 2.3: Business Filter - Consistency and cash generation checks"""

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.common.sql_utils import build_in_clause_params
from multibagger.config import Config
from multibagger.database.schema import get_engine

from .common import (
    ScreenResult,
    apply_rules_with_tracking,
    check_expected_range,
    print_stage_summary,
    save_stage_output,
)

logger = logging.getLogger(__name__)


def fetch_historical_fundamentals(
    session: Session, ticker_ids: list[int], years: int = 5, config: Config | None = None
) -> pd.DataFrame:
    """
    Fetch historical fundamentals for business analysis (staging-first with canonical fallback).

    When persist_finalists_only=true, prefer fundamentals_temp, fallback to fundamentals.
    This allows screens to see both finalists (promoted) and non-finalists (staging).

    Args:
        session: DB session
        ticker_ids: List of ticker IDs
        years: Number of years of history to fetch
        config: System configuration (for storage policy)

    Returns:
        DataFrame with fundamentals
    """
    if not ticker_ids:
        return pd.DataFrame()

    # Check storage policy
    persist_finalists_only = False
    if config:
        storage = config.get("storage", {})
        persist_finalists_only = storage.get("persist_finalists_only", False)

    # Build SQL IN clause with dynamic placeholders
    placeholders, params = build_in_clause_params(ticker_ids, param_prefix='ticker')

    if persist_finalists_only:
        # Staging-first: UNION temp and canonical, prefer temp
        query = text(f"""
            WITH combined AS (
                SELECT
                    f.ticker_id,
                    t.symbol,
                    f.period_end,
                    f.fiscal_year,
                    f.revenue,
                    f.gross_profit,
                    f.net_income,
                    f.operating_cash_flow,
                    f.free_cash_flow,
                    f.total_assets,
                    f.current_assets,
                    f.total_liabilities,
                    1 as priority  -- temp has priority
                FROM fundamentals_temp f
                INNER JOIN tickers t ON f.ticker_id = t.id
                WHERE f.ticker_id IN ({placeholders})
                  AND f.report_type = 'A'
                  AND f.fiscal_year >= (strftime('%Y', 'now') - :years)

                UNION ALL

                SELECT
                    f.ticker_id,
                    t.symbol,
                    f.period_end,
                    f.fiscal_year,
                    f.revenue,
                    f.gross_profit,
                    f.net_income,
                    f.operating_cash_flow,
                    f.free_cash_flow,
                    f.total_assets,
                    f.current_assets,
                    f.total_liabilities,
                    2 as priority  -- canonical as fallback
                FROM fundamentals f
                INNER JOIN tickers t ON f.ticker_id = t.id
                WHERE f.ticker_id IN ({placeholders})
                  AND f.report_type = 'A'
                  AND f.fiscal_year >= (strftime('%Y', 'now') - :years)
            )
            SELECT
                ticker_id, symbol, period_end, fiscal_year,
                revenue, gross_profit, net_income, operating_cash_flow,
                free_cash_flow, total_assets, current_assets, total_liabilities
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY ticker_id, period_end
                        ORDER BY priority ASC
                    ) as rn
                FROM combined
            )
            WHERE rn = 1
            ORDER BY ticker_id, fiscal_year DESC
        """)
    else:
        # Legacy: read from canonical only
        query = text(f"""
            SELECT
                f.ticker_id,
                t.symbol,
                f.period_end,
                f.fiscal_year,
                f.revenue,
                f.gross_profit,
                f.net_income,
                f.operating_cash_flow,
                f.free_cash_flow,
                f.total_assets,
                f.current_assets,
                f.total_liabilities
            FROM fundamentals f
            INNER JOIN tickers t ON f.ticker_id = t.id
            WHERE f.ticker_id IN ({placeholders})
              AND f.report_type = 'A'
              AND f.fiscal_year >= (strftime('%Y', 'now') - :years)
            ORDER BY f.ticker_id, f.fiscal_year DESC
        """)

    # Add years to params
    params['years'] = years

    result = session.execute(query, params)

    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    logger.info(f"Fetched {len(df)} fundamental records for {len(ticker_ids)} tickers (policy: {'staging-first' if persist_finalists_only else 'canonical-only'})")

    return df


def compute_business_metrics(fundamentals_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute business consistency metrics using vectorized operations.

    Args:
        fundamentals_df: Historical fundamentals

    Returns:
        DataFrame with per-ticker metrics [ticker_id, positive_fcf_years, ...]
    """
    if fundamentals_df.empty:
        return pd.DataFrame()

    metrics_list = []

    for ticker_id, group in fundamentals_df.groupby("ticker_id"):
        # Sort by fiscal year
        group = group.sort_values("fiscal_year")

        # Count positive FCF years
        positive_fcf_years = (group["free_cash_flow"] > 0).sum()

        # Cumulative 5-year FCF
        cumulative_5yr_fcf = group["free_cash_flow"].sum()

        # Gross margin volatility
        group["gross_margin"] = (
            group["gross_profit"] / group["revenue"]
        ) * 100
        margin_volatility = group["gross_margin"].std()

        # Average margin
        avg_gross_margin = group["gross_margin"].mean()

        # Reinvestment rate (simplified: use operating cash flow as proxy)
        # Real calc: (capex + R&D) / gross_profit
        # For now: operating_cash_flow / gross_profit
        group["reinvestment_rate"] = (
            group["operating_cash_flow"] / group["gross_profit"]
        ) * 100
        avg_reinvestment_rate = group["reinvestment_rate"].mean()

        # Years of data available
        years_available = len(group)

        metrics_list.append(
            {
                "ticker_id": ticker_id,
                "symbol": group["symbol"].iloc[0],
                "positive_fcf_years": positive_fcf_years,
                "cumulative_5yr_fcf": cumulative_5yr_fcf,
                "margin_volatility": margin_volatility,
                "avg_gross_margin": avg_gross_margin,
                "avg_reinvestment_rate": avg_reinvestment_rate,
                "years_data": years_available,
            }
        )

    return pd.DataFrame(metrics_list)


# Rule functions


def rule_min_positive_fcf_years(df: pd.DataFrame, config: dict) -> pd.Series:
    """Must have minimum positive FCF years"""
    min_years = config.get("min_positive_fcf_years", 3)
    return df["positive_fcf_years"] >= min_years


def rule_positive_cumulative_fcf(df: pd.DataFrame, config: dict) -> pd.Series:
    """5-year cumulative FCF must be positive"""
    min_val = config.get("min_cumulative_5yr_fcf", 0)
    return df["cumulative_5yr_fcf"] >= min_val


def rule_max_margin_volatility(df: pd.DataFrame, config: dict) -> pd.Series:
    """Gross margin volatility must be below max (stable margins)"""
    max_val = config.get("max_margin_volatility", 10.0)
    # NaN means insufficient data - fail
    return df["margin_volatility"].fillna(999) <= max_val


def rule_min_years_data(df: pd.DataFrame, config: dict) -> pd.Series:
    """Must have minimum years of data"""
    min_years = config.get("min_years_data", 3)
    return df["years_data"] >= min_years


def rule_reinvestment_rate_range(df: pd.DataFrame, config: dict) -> pd.Series:
    """Reinvestment rate must be in reasonable range"""
    min_val = config.get("min_reinvestment_rate", 0.0)
    max_val = config.get("max_reinvestment_rate", 100.0)

    # Optional filter (if both are defaults, pass all)
    if min_val == 0.0 and max_val == 100.0:
        return pd.Series([True] * len(df), index=df.index)

    return (df["avg_reinvestment_rate"].fillna(0) >= min_val) & (
        df["avg_reinvestment_rate"].fillna(0) <= max_val
    )


def screen_business(
    config: Config,
    input_csv: str | Path | None = None,
    as_of: str | None = None,
    output_dir: str = "snapshots",
) -> ScreenResult:
    """
    Execute Stage 2.3: Business Filter.

    Filters on business quality and consistency metrics.

    Args:
        config: System configuration
        input_csv: Path to stage2 CSV (if None, uses default snapshot path)
        as_of: YYYY-MM date string
        output_dir: Output directory for CSV

    Returns:
        ScreenResult with survivors and statistics
    """
    start_time = time.time()

    # Parse as_of date
    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m")

    logger.info(f"Starting Business Filter for as_of={as_of}")

    # Load input from previous stage
    if input_csv is None:
        input_csv = Path(f"{output_dir}/{as_of}/stage_quality_{as_of}.csv")

    if not Path(input_csv).exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_csv}. Run 'screen quality' first."
        )

    input_df = pd.read_csv(input_csv)
    total_input = len(input_df)

    logger.info(f"Loaded {total_input} candidates from {input_csv}")

    # Get screening config
    screen_config = config.get("screen", {}).get("business", {})

    # Fetch historical fundamentals
    engine = get_engine()
    with Session(engine) as session:
        fundamentals_df = fetch_historical_fundamentals(
            session, input_df["ticker_id"].tolist(), years=5, config=config
        )

    if fundamentals_df.empty:
        logger.warning(
            "No fundamental data found! Cannot proceed with business screening."
        )
        return ScreenResult(
            survivors=pd.DataFrame(),
            removed_by_rule={"no_fundamental_data": total_input},
            total_input=total_input,
            total_survivors=0,
            runtime_seconds=time.time() - start_time,
            stage_name="Business Filter (Stage 2.3)",
        )

    # Compute business metrics (vectorized)
    metrics_df = compute_business_metrics(fundamentals_df)

    # Merge with input
    df = input_df.merge(metrics_df, on="ticker_id", how="left", suffixes=("", "_metrics"))

    # Track missing metrics
    missing_metrics = df["positive_fcf_years"].isna().sum()
    if missing_metrics > 0:
        logger.warning(f"{missing_metrics} tickers missing business metrics")

    # Define rules in order
    rules = [
        ("min_years_data", rule_min_years_data),
        ("min_positive_fcf_years", rule_min_positive_fcf_years),
        ("positive_cumulative_fcf", rule_positive_cumulative_fcf),
        ("max_margin_volatility", rule_max_margin_volatility),
        ("reinvestment_rate_range", rule_reinvestment_rate_range),
    ]

    # Apply rules with tracking
    survivors, removed_by_rule = apply_rules_with_tracking(df, rules, screen_config)

    runtime = time.time() - start_time

    # Create result
    result = ScreenResult(
        survivors=survivors,
        removed_by_rule=removed_by_rule,
        total_input=total_input,
        total_survivors=len(survivors),
        runtime_seconds=runtime,
        stage_name="Business Filter (Stage 2.3)",
    )

    # Print summary
    print_stage_summary(result)

    # Check expected range (target ~0.6% of original 5000 = ~30)
    # Input is ~100, so target ~25-35
    expected_min = max(int(total_input * 0.20), 5)  # At least 5
    expected_max = int(total_input * 0.40)
    check_expected_range(len(survivors), expected_min, expected_max, "Business Filter")

    # Save output
    snapshot_dir = f"{output_dir}/{as_of}"
    csv_path = save_stage_output(survivors, "business", as_of, snapshot_dir)

    logger.info(f"Business Filter complete: {len(survivors)} survivors in {runtime:.2f}s")
    logger.info(f"Output: {csv_path}")

    return result
