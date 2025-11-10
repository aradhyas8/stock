"""Stage 2.2: Quality Filter - Financial quality metrics"""

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def fetch_factors_for_tickers(
    session: Session, ticker_ids: list[int], as_of_date: datetime
) -> pd.DataFrame:
    """
    Fetch factors for given tickers.

    Args:
        session: DB session
        ticker_ids: List of ticker IDs to fetch
        as_of_date: Only get factors computed as of this date

    Returns:
        DataFrame with factors
    """
    if not ticker_ids:
        return pd.DataFrame()

    # Create placeholders for IN clause
    placeholders = ','.join([f':id{i}' for i in range(len(ticker_ids))])

    query = text(f"""
        SELECT
            f.ticker_id,
            t.symbol,
            f.as_of_date,
            f.roce,
            f.revenue_growth_5y,
            f.gross_margin,
            f.debt_to_equity,
            f.fcf_yield
        FROM factors f
        INNER JOIN tickers t ON f.ticker_id = t.id
        WHERE f.ticker_id IN ({placeholders})
          AND f.as_of_date <= :as_of_date
        ORDER BY f.ticker_id, f.as_of_date DESC
    """)

    # Build params dict with individual ID parameters
    params = {f'id{i}': tid for i, tid in enumerate(ticker_ids)}
    params['as_of_date'] = as_of_date

    result = session.execute(query, params)

    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    # Take most recent factor per ticker
    if not df.empty:
        df = df.drop_duplicates(subset=["ticker_id"], keep="first")

    logger.info(f"Fetched factors for {len(df)}/{len(ticker_ids)} tickers")

    return df


# Rule functions


def rule_min_roce(df: pd.DataFrame, config: dict) -> pd.Series:
    """ROCE must meet minimum"""
    min_val = config.get("min_roce", 15.0)
    return df["roce"].fillna(0) >= min_val


def rule_min_revenue_growth(df: pd.DataFrame, config: dict) -> pd.Series:
    """Revenue growth (5y CAGR) must meet minimum"""
    min_val = config.get("min_revenue_cagr_5y", 10.0)
    return df["revenue_growth_5y"].fillna(0) >= min_val


def rule_min_gross_margin(df: pd.DataFrame, config: dict) -> pd.Series:
    """Gross margin must meet minimum"""
    min_val = config.get("min_gross_margin", 20.0)
    return df["gross_margin"].fillna(0) >= min_val


def rule_max_debt_to_equity(df: pd.DataFrame, config: dict) -> pd.Series:
    """Debt-to-equity must be below maximum"""
    max_val = config.get("max_debt_to_equity", 1.0)
    # Treat NaN as zero debt (pass)
    return df["debt_to_equity"].fillna(0) <= max_val


def rule_min_fcf_margin(df: pd.DataFrame, config: dict) -> pd.Series:
    """FCF yield must meet minimum (optional check)"""
    min_val = config.get("min_fcf_margin", 0.0)  # Default 0 = no filter

    if min_val <= 0:
        return pd.Series([True] * len(df), index=df.index)

    return df["fcf_yield"].fillna(0) >= min_val


def screen_quality(
    config: Config,
    input_csv: str | Path | None = None,
    as_of: str | None = None,
    output_dir: str = "snapshots",
) -> ScreenResult:
    """
    Execute Stage 2.2: Quality Filter.

    Filters on financial quality metrics from factors table.

    Args:
        config: System configuration
        input_csv: Path to stage1 CSV (if None, uses default snapshot path)
        as_of: YYYY-MM date string
        output_dir: Output directory for CSV

    Returns:
        ScreenResult with survivors and statistics
    """
    start_time = time.time()

    # Parse as_of date
    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m")

    as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d")

    logger.info(f"Starting Quality Filter for as_of={as_of}")

    # Load input from previous stage
    if input_csv is None:
        input_csv = Path(f"{output_dir}/{as_of}/stage_fast_{as_of}.csv")

    if not Path(input_csv).exists():
        raise FileNotFoundError(
            f"Input CSV not found: {input_csv}. Run 'screen fast' first."
        )

    input_df = pd.read_csv(input_csv)
    total_input = len(input_df)

    logger.info(f"Loaded {total_input} candidates from {input_csv}")

    # Get screening config
    screen_config = config.get("screen", {}).get("quality", {})

    # Fetch factors for input tickers
    engine = get_engine()
    with Session(engine) as session:
        factors_df = fetch_factors_for_tickers(
            session, input_df["ticker_id"].tolist(), as_of_date
        )

    # Merge with input
    if factors_df.empty:
        logger.warning(
            "No factors found! Cannot proceed with quality screening. "
            "Run factor computation first."
        )
        # Return empty result
        return ScreenResult(
            survivors=pd.DataFrame(),
            removed_by_rule={"no_factors_data": total_input},
            total_input=total_input,
            total_survivors=0,
            runtime_seconds=time.time() - start_time,
            stage_name="Quality Filter (Stage 2.2)",
        )

    # Merge input with factors
    df = input_df.merge(factors_df, on="ticker_id", how="left", suffixes=("", "_factor"))

    # Track missing factors
    missing_factors = df["roce"].isna().sum()
    if missing_factors > 0:
        logger.warning(f"{missing_factors} tickers missing factor data")

    # Define rules in order
    rules = [
        ("min_roce", rule_min_roce),
        ("min_revenue_growth", rule_min_revenue_growth),
        ("min_gross_margin", rule_min_gross_margin),
        ("max_debt_to_equity", rule_max_debt_to_equity),
        ("min_fcf_margin", rule_min_fcf_margin),
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
        stage_name="Quality Filter (Stage 2.2)",
    )

    # Print summary
    print_stage_summary(result)

    # Check expected range (target ~2% of original)
    # Assume input is ~10% of original 5000 = 500
    # So target 2% = 10 survivors = ~2% of 500
    expected_min = max(int(total_input * 0.15), 10)  # At least 10
    expected_max = int(total_input * 0.25)
    check_expected_range(len(survivors), expected_min, expected_max, "Quality Filter")

    # Save output
    snapshot_dir = f"{output_dir}/{as_of}"
    csv_path = save_stage_output(survivors, "quality", as_of, snapshot_dir)

    logger.info(f"Quality Filter complete: {len(survivors)} survivors in {runtime:.2f}s")
    logger.info(f"Output: {csv_path}")

    return result
