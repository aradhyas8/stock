"""Stage 2.4: Red Flag Detection - Forensic accounting and risk assessment"""

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.common.sql_utils import build_in_clause_params
from multibagger.config import Config
from multibagger.database.models import RiskFlag
from multibagger.database.schema import get_engine
from multibagger.forensics import (
    compute_altman_z_score,
    compute_beneish_m_score,
    compute_forensics_score,
    compute_sloan_accruals,
)
from multibagger.governance import compute_governance_score
from multibagger.risk import (
    compute_composite_score,
    determine_first_fail,
    generate_details_json,
)
from multibagger.sentiment import compute_sentiment_score

from .common import (
    ScreenResult,
    apply_rules_with_tracking,
    check_expected_range,
    print_stage_summary,
    save_stage_output,
)

logger = logging.getLogger(__name__)


def get_fiscal_year_for_as_of(as_of: str) -> int:
    """
    Determine which fiscal year to use based on as_of month.

    Args:
        as_of: YYYY-MM format date

    Returns:
        Fiscal year to use (prior year for determinism)

    Example:
        >>> get_fiscal_year_for_as_of("2025-11")
        2024
    """
    year, month = map(int, as_of.split('-'))
    # Use prior year's annual data
    return year - 1


def fetch_fundamentals_for_survivors(
    session: Session,
    ticker_ids: list[int],
    max_fiscal_year: int
) -> pd.DataFrame:
    """
    Fetch fundamentals for survivors (batch query).

    Args:
        session: DB session
        ticker_ids: List of survivor ticker IDs
        max_fiscal_year: Maximum fiscal year to include

    Returns:
        DataFrame with fundamentals sorted by ticker_id, fiscal_year DESC
    """
    if not ticker_ids:
        return pd.DataFrame()

    # Build SQL IN clause
    placeholders, params = build_in_clause_params(ticker_ids, param_prefix='ticker')

    # Query fundamentals
    query = text(f"""
        SELECT
            ticker_id,
            fiscal_year,
            period_end,
            revenue,
            receivables,
            gross_profit,
            current_assets,
            ppe,
            non_current_assets,
            total_assets,
            depreciation,
            sga_expense,
            long_term_debt,
            current_liabilities,
            cash,
            short_term_debt,
            retained_earnings,
            ebit,
            operating_income,
            total_liabilities
        FROM fundamentals
        WHERE ticker_id IN ({placeholders})
          AND report_type = 'A'
          AND fiscal_year <= :max_fiscal_year
        ORDER BY ticker_id, fiscal_year DESC
    """)

    params['max_fiscal_year'] = max_fiscal_year

    result = session.execute(query, params)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    logger.info(f"Fetched {len(df)} fundamental records for {len(ticker_ids)} tickers")

    return df


def fetch_market_caps(
    session: Session,
    ticker_ids: list[int]
) -> dict[int, float]:
    """
    Fetch current market caps for tickers (batch query).

    Args:
        session: DB session
        ticker_ids: List of ticker IDs

    Returns:
        Dict mapping ticker_id → market_cap
    """
    if not ticker_ids:
        return {}

    # Build SQL IN clause
    placeholders, params = build_in_clause_params(ticker_ids, param_prefix='ticker')

    query = text(f"""
        SELECT id, market_cap
        FROM tickers
        WHERE id IN ({placeholders})
    """)

    result = session.execute(query, params)
    market_caps = {row.id: float(row.market_cap) for row in result if row.market_cap}

    logger.info(f"Fetched market caps for {len(market_caps)}/{len(ticker_ids)} tickers")

    return market_caps


def compute_forensics_for_tickers(
    fundamentals_df: pd.DataFrame,
    market_caps: dict[int, float],
    config: dict
) -> list[dict]:
    """
    Compute forensic metrics for all tickers (vectorized).

    Args:
        fundamentals_df: DataFrame with fundamentals sorted by ticker_id, fiscal_year DESC
        market_caps: Dict mapping ticker_id → market_cap
        config: Configuration dict with risk.weights and risk.thresholds

    Returns:
        List of dicts with forensic results per ticker
    """
    results = []

    # Get config values
    weights = config.get('risk', {}).get('weights', {
        'forensics': 1.0,
        'governance': 0.0,
        'sentiment': 0.0
    })

    thresholds = config.get('risk', {}).get('thresholds', {
        'beneish_cutoff': -2.22,
        'altman_distress': 1.81,
        'sloan_warning': 0.10,
        'composite_score_max': 40.0
    })

    # Group fundamentals by ticker
    for ticker_id, group in fundamentals_df.groupby('ticker_id'):
        # Sort by fiscal year descending (most recent first)
        group = group.sort_values('fiscal_year', ascending=False)

        # Get latest fundamentals for Altman
        latest = group.iloc[0] if len(group) > 0 else None
        market_cap = market_caps.get(ticker_id, 0.0)

        # Compute forensic metrics
        beneish_result = compute_beneish_m_score(group)
        altman_result = compute_altman_z_score(latest, market_cap) if latest is not None else {
            'z_score': None,
            'components': {},
            'interpretation': 'Insufficient data'
        }
        accruals_result = compute_sloan_accruals(group)

        # Compute forensics score (0-100)
        forensics_score = compute_forensics_score(
            beneish_result,
            altman_result,
            accruals_result
        )

        # Stub scores for governance and sentiment (MVP)
        governance_score = 0.0
        sentiment_score = 0.0

        # Compute composite score
        composite_score = compute_composite_score(
            forensics_score,
            governance_score,
            sentiment_score,
            weights
        )

        # Check hard-stop conditions
        first_fail_reason = determine_first_fail(
            {
                'beneish_m_score': beneish_result.get('m_score'),
                'altman_z_score': altman_result.get('z_score'),
                'accruals_ratio': accruals_result.get('accruals_ratio')
            },
            thresholds
        )

        # Store result
        results.append({
            'ticker_id': ticker_id,
            'beneish_result': beneish_result,
            'altman_result': altman_result,
            'accruals_result': accruals_result,
            'forensics_score': forensics_score,
            'governance_score': governance_score,
            'sentiment_score': sentiment_score,
            'composite_score': composite_score,
            'first_fail_reason': first_fail_reason
        })

    logger.info(f"Computed forensics for {len(results)} tickers")

    return results


def screen_redflags(
    config: Config,
    as_of: str | None = None,
    output_dir: str = "snapshots"
) -> ScreenResult:
    """
    Stage 2.4: Red Flag Detection screening.

    Args:
        config: Configuration object
        as_of: YYYY-MM format date (defaults to current month)
        output_dir: Output directory for CSV files

    Returns:
        ScreenResult with survivors and screening stats
    """
    start_time = time.time()

    # Default as_of to current month
    if as_of is None:
        as_of = datetime.utcnow().strftime("%Y-%m")

    logger.info(f"Starting Red Flag Detection for {as_of}")

    # Load Stage 2.3 survivors
    business_output = Path(output_dir) / as_of / f"stage_business_{as_of}.csv"

    if not business_output.exists():
        logger.error(f"Business filter output not found: {business_output}")
        raise FileNotFoundError(
            f"Input CSV not found: {business_output}. Run 'screen business' first."
        )

    survivors_df = pd.read_csv(business_output)
    ticker_ids = survivors_df['ticker_id'].tolist()

    logger.info(f"Loaded {len(ticker_ids)} survivors from Stage 2.3")

    # Get fiscal year cutoff for determinism
    max_fiscal_year = get_fiscal_year_for_as_of(as_of)
    logger.info(f"Using fiscal year data up to {max_fiscal_year}")

    # Fetch data (batch queries)
    engine = get_engine()
    with Session(engine) as session:
        # Fetch fundamentals
        fundamentals_df = fetch_fundamentals_for_survivors(
            session,
            ticker_ids,
            max_fiscal_year
        )

        # Fetch market caps
        market_caps = fetch_market_caps(session, ticker_ids)

    # Check coverage
    tickers_with_fundamentals = fundamentals_df['ticker_id'].nunique()
    coverage = tickers_with_fundamentals / len(ticker_ids) * 100 if ticker_ids else 0

    logger.info(f"Forensics coverage: {tickers_with_fundamentals}/{len(ticker_ids)} ({coverage:.1f}%)")

    # Compute forensic metrics for all tickers
    # Convert Config object to dict for compute_forensics_for_tickers
    config_dict = config._config if hasattr(config, '_config') else (config if isinstance(config, dict) else {})
    forensic_results = compute_forensics_for_tickers(
        fundamentals_df,
        market_caps,
        config_dict
    )

    # Merge with survivor data
    results_df = pd.DataFrame(forensic_results)
    merged_df = survivors_df.merge(
        results_df,
        on='ticker_id',
        how='left'
    )

    # Apply elimination rules
    risk_config = config.get('risk', {}) if hasattr(config, 'get') else {}
    thresholds = risk_config.get('thresholds', {
        'composite_score_max': 40.0
    })

    rules = [
        ("composite_score_max", lambda df, cfg: df['composite_score'] <= thresholds.get('composite_score_max', 40.0)),
        ("first_fail_triggered", lambda df, cfg: df['first_fail_reason'].isna()),
    ]

    final_survivors, removed_by_rule = apply_rules_with_tracking(
        merged_df,
        rules,
        risk_config
    )

    # Persist to database
    as_of_date = datetime.strptime(f"{as_of}-30", "%Y-%m-%d").date()

    with Session(engine) as session:
        for _, row in merged_df.iterrows():
            # Get ticker symbol for details_json
            symbol = row.get('symbol', 'UNKNOWN')

            # Generate details JSON
            details_json = generate_details_json(
                ticker_id=row['ticker_id'],
                symbol=symbol,
                beneish_result=row.get('beneish_result', {}),
                altman_result=row.get('altman_result', {}),
                accruals_result=row.get('accruals_result', {}),
                forensics_score=row.get('forensics_score', 0.0),
                governance_score=row.get('governance_score', 0.0),
                sentiment_score=row.get('sentiment_score', 0.0),
                composite_score=row.get('composite_score', 0.0),
                first_fail_reason=row.get('first_fail_reason'),
                as_of=as_of
            )

            # UPSERT risk_flags
            risk_flag = RiskFlag(
                ticker_id=row['ticker_id'],
                as_of_date=as_of_date,
                beneish_m_score=row.get('beneish_result', {}).get('m_score'),
                altman_z_score=row.get('altman_result', {}).get('z_score'),
                accruals_ratio=row.get('accruals_result', {}).get('accruals_ratio'),
                forensics_score=row.get('forensics_score'),
                governance_score=row.get('governance_score'),
                sentiment_score=row.get('sentiment_score'),
                composite_score=row.get('composite_score'),
                first_fail_reason=row.get('first_fail_reason'),
                details_json=details_json
            )

            # Check if exists
            existing = session.query(RiskFlag).filter_by(
                ticker_id=row['ticker_id'],
                as_of_date=as_of_date
            ).first()

            if existing:
                # Update
                existing.beneish_m_score = risk_flag.beneish_m_score
                existing.altman_z_score = risk_flag.altman_z_score
                existing.accruals_ratio = risk_flag.accruals_ratio
                existing.forensics_score = risk_flag.forensics_score
                existing.governance_score = risk_flag.governance_score
                existing.sentiment_score = risk_flag.sentiment_score
                existing.composite_score = risk_flag.composite_score
                existing.first_fail_reason = risk_flag.first_fail_reason
                existing.details_json = risk_flag.details_json
            else:
                # Insert
                session.add(risk_flag)

        session.commit()

    logger.info(f"Persisted {len(merged_df)} risk assessments to database")

    # Save CSV output
    output_cols = [
        'ticker_id', 'symbol', 'name', 'exchange_code',
        'beneish_m_score', 'altman_z_score', 'accruals_ratio',
        'forensics_score', 'governance_score', 'sentiment_score',
        'composite_score', 'first_fail_reason'
    ]

    # Extract scalar values from dict columns
    csv_df = merged_df.copy()
    if 'beneish_result' in csv_df.columns:
        csv_df['beneish_m_score'] = csv_df['beneish_result'].apply(
            lambda x: x.get('m_score') if isinstance(x, dict) else None
        )
    if 'altman_result' in csv_df.columns:
        csv_df['altman_z_score'] = csv_df['altman_result'].apply(
            lambda x: x.get('z_score') if isinstance(x, dict) else None
        )
    if 'accruals_result' in csv_df.columns:
        csv_df['accruals_ratio'] = csv_df['accruals_result'].apply(
            lambda x: x.get('accruals_ratio') if isinstance(x, dict) else None
        )

    # Select only output columns that exist
    available_cols = [col for col in output_cols if col in csv_df.columns]
    output_path = save_stage_output(
        csv_df[available_cols],
        "redflags",
        as_of,
        output_dir
    )

    runtime = time.time() - start_time

    # Create result
    result = ScreenResult(
        survivors=final_survivors,
        removed_by_rule=removed_by_rule,
        total_input=len(ticker_ids),
        total_survivors=len(final_survivors),
        runtime_seconds=runtime,
        stage_name="Red Flag Detection (Stage 2.4)"
    )

    # Check expected range (optional, informational only)
    check_expected_range(
        len(final_survivors),
        expected_min=int(len(ticker_ids) * 0.5),  # Expect 50-90% survival
        expected_max=int(len(ticker_ids) * 0.9),
        stage_name="Red Flag Detection"
    )

    return result
