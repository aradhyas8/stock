"""Forensic accounting metrics for earnings manipulation detection"""

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero"""
    if denominator == 0 or pd.isna(denominator) or pd.isna(numerator):
        return default
    return numerator / denominator


def compute_beneish_m_score(fundamentals_df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute Beneish M-Score for earnings manipulation detection.

    Formula:
        M = -4.84 + 0.92×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI + 0.115×DEPI
            - 0.172×SGAI + 4.679×TATA - 0.327×LVGI

    Args:
        fundamentals_df: DataFrame with columns [ticker_id, fiscal_year, revenue,
                        receivables, gross_profit, current_assets, ppe, total_assets,
                        depreciation, sga_expense, long_term_debt, current_liabilities]
                        Sorted by fiscal_year DESC (latest first)

    Returns:
        Dict with m_score, components, and interpretation
    """
    if len(fundamentals_df) < 2:
        logger.warning("Insufficient data for Beneish M-Score (need 2+ years)")
        return {
            "m_score": None,
            "components": {},
            "interpretation": "Insufficient data"
        }

    # Sort by fiscal year descending (latest first)
    df = fundamentals_df.sort_values("fiscal_year", ascending=False).head(2)

    if len(df) < 2:
        return {
            "m_score": None,
            "components": {},
            "interpretation": "Insufficient data"
        }

    # Current year (t) and prior year (t-1)
    current = df.iloc[0]
    prior = df.iloc[1]

    try:
        # Component 1: DSRI (Days Sales in Receivables Index)
        # (Receivables_t / Revenue_t) / (Receivables_t-1 / Revenue_t-1)
        dsri = safe_divide(
            safe_divide(float(current.get('receivables', 0)), float(current.get('revenue', 1))),
            safe_divide(float(prior.get('receivables', 0)), float(prior.get('revenue', 1))),
            default=1.0
        )

        # Component 2: GMI (Gross Margin Index)
        # (Gross Profit_t-1 / Revenue_t-1) / (Gross Profit_t / Revenue_t)
        gm_prior = safe_divide(float(prior.get('gross_profit', 0)), float(prior.get('revenue', 1)))
        gm_current = safe_divide(float(current.get('gross_profit', 0)), float(current.get('revenue', 1)))
        gmi = safe_divide(gm_prior, gm_current, default=1.0)

        # Component 3: AQI (Asset Quality Index)
        # (1 - (CA_t + PPE_t)/TA_t) / (1 - (CA_t-1 + PPE_t-1)/TA_t-1)
        def asset_quality_ratio(row):
            ca = float(row.get('current_assets', 0))
            ppe = float(row.get('ppe', 0)) or float(row.get('non_current_assets', 0))
            ta = float(row.get('total_assets', 1))
            return 1 - safe_divide(ca + ppe, ta)

        aqi = safe_divide(
            asset_quality_ratio(prior),
            asset_quality_ratio(current),
            default=1.0
        )

        # Component 4: SGI (Sales Growth Index)
        # Revenue_t / Revenue_t-1
        sgi = safe_divide(
            float(current.get('revenue', 0)),
            float(prior.get('revenue', 1)),
            default=1.0
        )

        # Component 5: DEPI (Depreciation Index)
        # (Depreciation_t-1 / (Depreciation_t-1 + PPE_t-1)) / (Depreciation_t / (Depreciation_t + PPE_t))
        def depr_rate(row):
            depr = float(row.get('depreciation', 0))
            ppe = float(row.get('ppe', 0)) or float(row.get('non_current_assets', 0))
            return safe_divide(depr, depr + ppe)

        depi = safe_divide(depr_rate(prior), depr_rate(current), default=1.0)

        # Component 6: SGAI (SG&A Index)
        # (SGA_t / Revenue_t) / (SGA_t-1 / Revenue_t-1)
        sga_ratio_current = safe_divide(float(current.get('sga_expense', 0)), float(current.get('revenue', 1)))
        sga_ratio_prior = safe_divide(float(prior.get('sga_expense', 0)), float(prior.get('revenue', 1)))
        sgai = safe_divide(sga_ratio_current, sga_ratio_prior, default=1.0)

        # Component 7: TATA (Total Accruals to Total Assets)
        # (ΔWC - Depreciation) / Total Assets
        # ΔWC = ΔCA - ΔCash - ΔCL + ΔSTD
        delta_ca = float(current.get('current_assets', 0)) - float(prior.get('current_assets', 0))
        delta_cash = float(current.get('cash', 0)) - float(prior.get('cash', 0))
        delta_cl = float(current.get('current_liabilities', 0)) - float(prior.get('current_liabilities', 0))
        delta_std = float(current.get('short_term_debt', 0)) - float(prior.get('short_term_debt', 0))

        delta_wc = delta_ca - delta_cash - delta_cl + delta_std
        depreciation = float(current.get('depreciation', 0))
        avg_ta = (float(current.get('total_assets', 1)) + float(prior.get('total_assets', 1))) / 2

        tata = safe_divide(delta_wc - depreciation, avg_ta)

        # Component 8: LVGI (Leverage Index)
        # ((LTD_t + CL_t)/TA_t) / ((LTD_t-1 + CL_t-1)/TA_t-1)
        def leverage_ratio(row):
            ltd = float(row.get('long_term_debt', 0))
            cl = float(row.get('current_liabilities', 0))
            ta = float(row.get('total_assets', 1))
            return safe_divide(ltd + cl, ta)

        lvgi = safe_divide(leverage_ratio(current), leverage_ratio(prior), default=1.0)

        # Beneish M-Score Formula
        m_score = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )

        # Interpretation
        if m_score > -2.22:
            interpretation = "High probability of manipulation (RED FLAG)"
        else:
            interpretation = "Low probability of manipulation"

        return {
            "m_score": round(m_score, 4),
            "components": {
                "DSRI": round(dsri, 4),
                "GMI": round(gmi, 4),
                "AQI": round(aqi, 4),
                "SGI": round(sgi, 4),
                "DEPI": round(depi, 4),
                "SGAI": round(sgai, 4),
                "TATA": round(tata, 4),
                "LVGI": round(lvgi, 4),
            },
            "interpretation": interpretation
        }

    except Exception as e:
        logger.error(f"Error computing Beneish M-Score: {e}")
        return {
            "m_score": None,
            "components": {},
            "interpretation": f"Computation error: {e}"
        }


def compute_altman_z_score(
    fundamentals: pd.Series,
    market_cap: float
) -> dict[str, Any]:
    """
    Compute Altman Z-Score for bankruptcy prediction.

    Formula (for publicly traded manufacturing):
        Z = 1.2×(WC/TA) + 1.4×(RE/TA) + 3.3×(EBIT/TA) + 0.6×(MVE/TL) + 1.0×(Sales/TA)

    Args:
        fundamentals: Series with latest fundamental data
        market_cap: Current market capitalization

    Returns:
        Dict with z_score, components, and interpretation
    """
    try:
        ta = float(fundamentals.get('total_assets', 1))
        if ta == 0:
            return {
                "z_score": None,
                "components": {},
                "interpretation": "Insufficient data (zero total assets)"
            }

        # Component 1: Working Capital / Total Assets
        wc = float(fundamentals.get('current_assets', 0)) - float(fundamentals.get('current_liabilities', 0))
        wc_ta = safe_divide(wc, ta)

        # Component 2: Retained Earnings / Total Assets
        re = float(fundamentals.get('retained_earnings', 0))
        re_ta = safe_divide(re, ta)

        # Component 3: EBIT / Total Assets
        ebit = float(fundamentals.get('ebit', 0)) or float(fundamentals.get('operating_income', 0))
        ebit_ta = safe_divide(ebit, ta)

        # Component 4: Market Value of Equity / Total Liabilities
        tl = float(fundamentals.get('total_liabilities', 1))
        mve_tl = safe_divide(market_cap, tl)

        # Component 5: Sales / Total Assets
        sales = float(fundamentals.get('revenue', 0))
        sales_ta = safe_divide(sales, ta)

        # Altman Z-Score Formula
        z_score = (
            1.2 * wc_ta +
            1.4 * re_ta +
            3.3 * ebit_ta +
            0.6 * mve_tl +
            1.0 * sales_ta
        )

        # Interpretation
        if z_score < 1.81:
            interpretation = "High risk of bankruptcy (RED FLAG)"
        elif z_score <= 2.99:
            interpretation = "Gray zone (CAUTION)"
        else:
            interpretation = "Safe zone"

        return {
            "z_score": round(z_score, 4),
            "components": {
                "WC_TA": round(wc_ta, 4),
                "RE_TA": round(re_ta, 4),
                "EBIT_TA": round(ebit_ta, 4),
                "MVE_TL": round(mve_tl, 4),
                "Sales_TA": round(sales_ta, 4),
            },
            "interpretation": interpretation
        }

    except Exception as e:
        logger.error(f"Error computing Altman Z-Score: {e}")
        return {
            "z_score": None,
            "components": {},
            "interpretation": f"Computation error: {e}"
        }


def compute_sloan_accruals(fundamentals_df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute Sloan Accruals for earnings quality assessment.

    Formula:
        Accruals = (ΔCA - ΔCash - ΔCL + ΔSTD - Depreciation) / Average Total Assets

    Args:
        fundamentals_df: DataFrame with 2+ years of data, sorted by fiscal_year DESC

    Returns:
        Dict with accruals_ratio and interpretation
    """
    if len(fundamentals_df) < 2:
        logger.warning("Insufficient data for Sloan Accruals (need 2+ years)")
        return {
            "accruals_ratio": None,
            "interpretation": "Insufficient data"
        }

    # Sort by fiscal year descending (latest first)
    df = fundamentals_df.sort_values("fiscal_year", ascending=False).head(2)

    if len(df) < 2:
        return {
            "accruals_ratio": None,
            "interpretation": "Insufficient data"
        }

    current = df.iloc[0]
    prior = df.iloc[1]

    try:
        # Changes (current - prior)
        delta_ca = float(current.get('current_assets', 0)) - float(prior.get('current_assets', 0))
        delta_cash = float(current.get('cash', 0)) - float(prior.get('cash', 0))
        delta_cl = float(current.get('current_liabilities', 0)) - float(prior.get('current_liabilities', 0))
        delta_std = float(current.get('short_term_debt', 0)) - float(prior.get('short_term_debt', 0))

        # Depreciation
        depreciation = float(current.get('depreciation', 0))

        # Average total assets
        avg_ta = (float(current.get('total_assets', 1)) + float(prior.get('total_assets', 1))) / 2

        # Accruals
        accruals = delta_ca - delta_cash - delta_cl + delta_std - depreciation
        accruals_ratio = safe_divide(accruals, avg_ta)

        # Interpretation
        if accruals_ratio > 0.10:
            interpretation = "High positive accruals - earnings quality concern (RED FLAG)"
        elif accruals_ratio < 0:
            interpretation = "Negative accruals - conservative accounting"
        else:
            interpretation = "Moderate accruals"

        return {
            "accruals_ratio": round(accruals_ratio, 4),
            "interpretation": interpretation
        }

    except Exception as e:
        logger.error(f"Error computing Sloan Accruals: {e}")
        return {
            "accruals_ratio": None,
            "interpretation": f"Computation error: {e}"
        }


def compute_forensics_score(
    beneish: dict,
    altman: dict,
    accruals: dict
) -> float:
    """
    Normalize forensics metrics to 0-100 risk score.

    Higher score = higher risk

    Args:
        beneish: Beneish M-Score results
        altman: Altman Z-Score results
        accruals: Sloan Accruals results

    Returns:
        Risk score from 0 (low risk) to 100 (high risk)
    """
    risk_score = 0.0

    # Beneish M-Score (weight: 40%)
    m_score = beneish.get('m_score')
    if m_score is not None:
        if m_score > -2.22:
            # Above threshold: scale 0-40 based on severity
            # M-Score typically ranges from -3 to 0 for manipulators
            beneish_risk = min(40, (m_score + 2.22) * 20)
            risk_score += beneish_risk

    # Altman Z-Score (weight: 40%)
    z_score = altman.get('z_score')
    if z_score is not None:
        if z_score < 2.99:
            if z_score < 1.81:
                # High risk zone
                altman_risk = 40
            else:
                # Gray zone: scale 20-40
                altman_risk = 20 + (2.99 - z_score) / (2.99 - 1.81) * 20
            risk_score += altman_risk

    # Sloan Accruals (weight: 20%)
    accruals_ratio = accruals.get('accruals_ratio')
    if accruals_ratio is not None and accruals_ratio > 0.10:
        # Scale accruals risk (max 20 points)
        accruals_risk = min(20, accruals_ratio * 100)
        risk_score += accruals_risk

    return min(100, max(0, risk_score))
