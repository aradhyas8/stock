#!/usr/bin/env python3
"""
Data Promotion API - Phase A

Promotes finalist tickers' data from staging tables to canonical tables.
Idempotent and transactional - safe to call multiple times.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class PromotionResult:
    """Result of promoting a ticker's data from staging to canonical"""

    ticker_id: int
    as_of_date: str
    fundamentals_rows: int
    factors_rows: int

    def __str__(self) -> str:
        return (
            f"Promoted ticker_id={self.ticker_id} ({self.as_of_date}): "
            f"{self.fundamentals_rows} fundamentals, {self.factors_rows} factors"
        )


def promote_finalist(
    session: Session,
    ticker_id: int,
    as_of_date: date,
    commit: bool = True
) -> PromotionResult:
    """
    Promote a finalist's staging data to canonical tables.

    Idempotent: Safe to call multiple times. Second call yields zero changes.

    Args:
        session: SQLAlchemy session
        ticker_id: Ticker ID to promote
        as_of_date: As-of date for factors promotion
        commit: Whether to commit transaction (default: True)

    Returns:
        PromotionResult with counts of rows moved

    Process:
        1. UPSERT fundamentals_temp → fundamentals (all periods for this ticker)
        2. UPSERT factors_temp → factors (matching as_of_date)
        3. Commit transaction
        4. Return counts

    Note: Does NOT delete from temp tables (Phase B will purge).
    """
    as_of_str = as_of_date.strftime("%Y-%m-%d")

    # Step 1: Promote fundamentals (all periods for this ticker)
    # Use INSERT OR REPLACE to handle duplicates idempotently
    fundamentals_query = text("""
        INSERT OR REPLACE INTO fundamentals (
            ticker_id, period_end, report_type, fiscal_year, fiscal_quarter,
            revenue, gross_profit, operating_income, ebit, ebitda, net_income,
            total_assets, current_assets, non_current_assets,
            total_liabilities, current_liabilities, long_term_debt, shareholders_equity,
            operating_cash_flow, investing_cash_flow, financing_cash_flow, free_cash_flow,
            shares_outstanding, book_value_per_share, earnings_per_share,
            currency, filed_date, created_at, updated_at
        )
        SELECT
            ticker_id, period_end, report_type, fiscal_year, fiscal_quarter,
            revenue, gross_profit, operating_income, ebit, ebitda, net_income,
            total_assets, current_assets, non_current_assets,
            total_liabilities, current_liabilities, long_term_debt, shareholders_equity,
            operating_cash_flow, investing_cash_flow, financing_cash_flow, free_cash_flow,
            shares_outstanding, book_value_per_share, earnings_per_share,
            currency, filed_date, created_at, updated_at
        FROM fundamentals_temp
        WHERE ticker_id = :ticker_id
    """)

    result_fundamentals = session.execute(fundamentals_query, {"ticker_id": ticker_id})
    fundamentals_rows = result_fundamentals.rowcount

    # Step 2: Promote factors (matching as_of_date)
    factors_query = text("""
        INSERT OR REPLACE INTO factors (
            ticker_id, as_of_date,
            roe, roa, roce, roic, gross_margin, operating_margin, net_margin,
            revenue_growth_1y, revenue_growth_3y, revenue_growth_5y,
            earnings_growth_1y, earnings_growth_3y, earnings_growth_5y,
            debt_to_equity, current_ratio, interest_coverage, piotroski_score, altman_z_score,
            pe_ratio, pb_ratio, ps_ratio, peg_ratio, ev_ebitda, fcf_yield,
            beta, volatility_1y, max_drawdown_1y,
            beneish_m_score, days_sales_outstanding, asset_quality_index,
            quality_score, growth_score, value_score, momentum_score, overall_score,
            created_at, updated_at
        )
        SELECT
            ticker_id, as_of_date,
            roe, roa, roce, roic, gross_margin, operating_margin, net_margin,
            revenue_growth_1y, revenue_growth_3y, revenue_growth_5y,
            earnings_growth_1y, earnings_growth_3y, earnings_growth_5y,
            debt_to_equity, current_ratio, interest_coverage, piotroski_score, altman_z_score,
            pe_ratio, pb_ratio, ps_ratio, peg_ratio, ev_ebitda, fcf_yield,
            beta, volatility_1y, max_drawdown_1y,
            beneish_m_score, days_sales_outstanding, asset_quality_index,
            quality_score, growth_score, value_score, momentum_score, overall_score,
            created_at, updated_at
        FROM factors_temp
        WHERE ticker_id = :ticker_id AND as_of_date = :as_of
    """)

    result_factors = session.execute(
        factors_query,
        {"ticker_id": ticker_id, "as_of": as_of_str}
    )
    factors_rows = result_factors.rowcount

    # Step 3: Commit if requested
    if commit:
        session.commit()

    return PromotionResult(
        ticker_id=ticker_id,
        as_of_date=as_of_str,
        fundamentals_rows=fundamentals_rows,
        factors_rows=factors_rows
    )


def batch_promote_finalists(
    session: Session,
    ticker_ids: list[int],
    as_of_date: date,
    commit: bool = True
) -> list[PromotionResult]:
    """
    Promote multiple finalists in a single transaction.

    More efficient than calling promote_finalist() in a loop.

    Args:
        session: SQLAlchemy session
        ticker_ids: List of ticker IDs to promote
        as_of_date: As-of date for factors promotion
        commit: Whether to commit transaction (default: True)

    Returns:
        List of PromotionResult for each ticker
    """
    results = []

    for ticker_id in ticker_ids:
        # Call promote_finalist without committing
        result = promote_finalist(
            session=session,
            ticker_id=ticker_id,
            as_of_date=as_of_date,
            commit=False  # Don't commit per-ticker
        )
        results.append(result)

    # Single commit at end
    if commit:
        session.commit()

    return results
