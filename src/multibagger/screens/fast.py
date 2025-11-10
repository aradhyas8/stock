"""Stage 2.1: Quick Screener - Fast filters for liquidity, size, price"""

import logging
import time
from datetime import datetime

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


def fetch_universe_with_metrics(
    session: Session, as_of_date: datetime, window_days: int = 30
) -> pd.DataFrame:
    """
    Fetch universe with computed metrics using SQL.

    Single SQL query with window function for avg_volume_30d.
    """

    query = text("""
        WITH price_window AS (
            SELECT
                p.ticker_id,
                p.adj_close,
                p.volume,
                p.date,
                ROW_NUMBER() OVER (PARTITION BY p.ticker_id ORDER BY p.date DESC) as rn
            FROM prices p
            WHERE p.date <= :as_of_date
        ),
        last_prices AS (
            SELECT
                ticker_id,
                MAX(CASE WHEN rn = 1 THEN adj_close END) as last_close,
                MAX(CASE WHEN rn = 1 THEN date END) as last_date,
                AVG(CASE WHEN rn <= :window_days THEN volume END) as avg_volume_30d,
                COUNT(*) as price_data_points
            FROM price_window
            WHERE rn <= :window_days
            GROUP BY ticker_id
        )
        SELECT
            t.id as ticker_id,
            t.symbol,
            t.name,
            t.active,
            t.market_cap,
            e.code as exchange_code,
            e.country,
            s.name as sector,
            lp.last_close,
            lp.last_date,
            lp.avg_volume_30d,
            lp.price_data_points
        FROM tickers t
        INNER JOIN exchanges e ON t.exchange_id = e.id
        LEFT JOIN sectors s ON t.sector_id = s.id
        LEFT JOIN last_prices lp ON t.id = lp.ticker_id
        WHERE t.active = 1
    """)

    result = session.execute(
        query, {"as_of_date": as_of_date, "window_days": window_days}
    )

    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    logger.info(f"Fetched {len(df)} active tickers with price metrics")
    return df


# Rule functions (return boolean mask for survivors)


def rule_is_active(df: pd.DataFrame, config: dict) -> pd.Series:
    """Must be active ticker"""
    return df["active"] == 1


def rule_allowed_exchange(df: pd.DataFrame, config: dict) -> pd.Series:
    """Exchange must be in allowed list"""
    allowed = config.get("allowed_exchanges", ["NYSE", "NASDAQ", "NSE"])
    return df["exchange_code"].isin(allowed)


def rule_min_price(df: pd.DataFrame, config: dict) -> pd.Series:
    """Price must meet minimum threshold (currency-specific)"""
    min_price_usd = config.get("min_price_usd", 5.0)
    min_price_inr = config.get("min_price_inr", 100.0)

    # Apply currency-specific minimums
    mask_usd = (df["country"] == "USA") & (df["last_close"] >= min_price_usd)
    mask_inr = (df["country"] == "IND") & (df["last_close"] >= min_price_inr)

    return mask_usd | mask_inr


def rule_min_adv(df: pd.DataFrame, config: dict) -> pd.Series:
    """Average daily volume must meet minimum"""
    min_adv = config.get("min_adv", 100000)
    return df["avg_volume_30d"].fillna(0) >= min_adv


def rule_min_market_cap(df: pd.DataFrame, config: dict) -> pd.Series:
    """Market cap must meet minimum"""
    min_cap = config.get("min_market_cap", 100000000)
    return df["market_cap"].fillna(0) >= min_cap


def rule_exclude_etf(df: pd.DataFrame, config: dict) -> pd.Series:
    """Exclude ETFs if configured"""
    if not config.get("exclude_etf", True):
        return pd.Series([True] * len(df), index=df.index)

    # Infer ETF from symbol (simple heuristic)
    is_etf = df["symbol"].str.contains("ETF|FUND", case=False, na=False)
    return ~is_etf


def rule_exclude_adr(df: pd.DataFrame, config: dict) -> pd.Series:
    """Exclude ADRs if configured"""
    if not config.get("exclude_adr", True):
        return pd.Series([True] * len(df), index=df.index)

    # Infer ADR from symbol suffix (simple heuristic)
    is_adr = df["symbol"].str.endswith((".ADR", " ADR"), na=False)
    return ~is_adr


def rule_exclude_otc(df: pd.DataFrame, config: dict) -> pd.Series:
    """Exclude OTC stocks if configured"""
    if not config.get("exclude_otc", True):
        return pd.Series([True] * len(df), index=df.index)

    is_otc = df["exchange_code"].isin(["OTC", "PINK", "OTCBB"])
    return ~is_otc


def rule_has_price_data(df: pd.DataFrame, config: dict) -> pd.Series:
    """Must have recent price data"""
    return df["last_close"].notna()


def screen_fast(
    config: Config,
    as_of: str | None = None,
    output_dir: str = "snapshots",
) -> ScreenResult:
    """
    Execute Stage 2.1: Quick Screener.

    Filters universe on liquidity, size, price using batch SQL.

    Args:
        config: System configuration
        as_of: YYYY-MM date string (defaults to current month)
        output_dir: Output directory for CSV

    Returns:
        ScreenResult with survivors and statistics
    """
    start_time = time.time()

    # Parse as_of date
    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m")

    as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d")

    logger.info(f"Starting Quick Screener for as_of={as_of}")

    # Get screening config
    screen_config = config.get("screen", {}).get("fast", {})

    # Fetch universe with metrics
    engine = get_engine()
    with Session(engine) as session:
        df = fetch_universe_with_metrics(session, as_of_date)

    total_input = len(df)

    # Define rules in order
    rules = [
        ("has_price_data", rule_has_price_data),
        ("is_active", rule_is_active),
        ("allowed_exchange", rule_allowed_exchange),
        ("min_price", rule_min_price),
        ("min_adv", rule_min_adv),
        ("min_market_cap", rule_min_market_cap),
        ("exclude_etf", rule_exclude_etf),
        ("exclude_adr", rule_exclude_adr),
        ("exclude_otc", rule_exclude_otc),
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
        stage_name="Quick Screener (Stage 2.1)",
    )

    # Print summary
    print_stage_summary(result)

    # Check expected range (target ~10%)
    expected_min = int(total_input * 0.08)  # 8%
    expected_max = int(total_input * 0.12)  # 12%
    check_expected_range(len(survivors), expected_min, expected_max, "Quick Screener")

    # Save output
    snapshot_dir = f"{output_dir}/{as_of}"
    csv_path = save_stage_output(survivors, "fast", as_of, snapshot_dir)

    logger.info(f"Quick Screener complete: {len(survivors)} survivors in {runtime:.2f}s")
    logger.info(f"Output: {csv_path}")

    return result
