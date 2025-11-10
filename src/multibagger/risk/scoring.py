"""Composite risk scoring and first-fail logic"""

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def compute_composite_score(
    forensics_score: float,
    governance_score: float,
    sentiment_score: float,
    weights: dict
) -> float:
    """
    Compute weighted composite risk score.

    Args:
        forensics_score: Forensics risk score (0-100)
        governance_score: Governance risk score (0-100)
        sentiment_score: Sentiment risk score (0-100)
        weights: Dict with keys 'forensics', 'governance', 'sentiment'

    Returns:
        Composite score from 0 (low risk) to 100 (high risk)

    Example:
        >>> compute_composite_score(20.0, 0.0, 0.0, {'forensics': 1.0, 'governance': 0.0, 'sentiment': 0.0})
        20.0
    """
    # Weighted average
    composite = (
        forensics_score * weights.get('forensics', 0.5) +
        governance_score * weights.get('governance', 0.3) +
        sentiment_score * weights.get('sentiment', 0.2)
    )

    # Bound to 0-100
    return min(100.0, max(0.0, composite))


def determine_first_fail(
    metrics: dict,
    thresholds: dict
) -> str | None:
    """
    Check hard-stop conditions in priority order.

    Priority:
    1. Beneish M-Score > cutoff → "beneish_m_score_high"
    2. Altman Z-Score < distress threshold → "altman_z_score_distress"
    3. Sloan Accruals > warning threshold → "sloan_accruals_high"

    Args:
        metrics: Dict with 'beneish_m_score', 'altman_z_score', 'accruals_ratio'
        thresholds: Dict with 'beneish_cutoff', 'altman_distress', 'sloan_warning'

    Returns:
        First matching failure reason or None if all pass

    Example:
        >>> metrics = {'beneish_m_score': -2.0, 'altman_z_score': 1.5, 'accruals_ratio': 0.05}
        >>> thresholds = {'beneish_cutoff': -2.22, 'altman_distress': 1.81, 'sloan_warning': 0.10}
        >>> determine_first_fail(metrics, thresholds)
        'beneish_m_score_high'
    """
    # Priority 1: Beneish M-Score (earnings manipulation)
    beneish = metrics.get('beneish_m_score')
    if beneish is not None and thresholds.get('beneish_cutoff') is not None:
        if beneish > thresholds['beneish_cutoff']:
            logger.warning(
                f"Hard stop triggered: Beneish M-Score {beneish:.2f} > {thresholds['beneish_cutoff']}"
            )
            return "beneish_m_score_high"

    # Priority 2: Altman Z-Score (bankruptcy risk)
    altman = metrics.get('altman_z_score')
    if altman is not None and thresholds.get('altman_distress') is not None:
        if altman < thresholds['altman_distress']:
            logger.warning(
                f"Hard stop triggered: Altman Z-Score {altman:.2f} < {thresholds['altman_distress']}"
            )
            return "altman_z_score_distress"

    # Priority 3: Sloan Accruals (earnings quality)
    accruals = metrics.get('accruals_ratio')
    if accruals is not None and thresholds.get('sloan_warning') is not None:
        if accruals > thresholds['sloan_warning']:
            logger.warning(
                f"Hard stop triggered: Accruals ratio {accruals:.2f} > {thresholds['sloan_warning']}"
            )
            return "sloan_accruals_high"

    # No hard stop triggered
    return None


def generate_details_json(
    ticker_id: int,
    symbol: str,
    beneish_result: dict,
    altman_result: dict,
    accruals_result: dict,
    forensics_score: float,
    governance_score: float,
    sentiment_score: float,
    composite_score: float,
    first_fail_reason: str | None,
    as_of: str
) -> str:
    """
    Generate explainable details JSON with full provenance.

    Args:
        ticker_id: Ticker ID
        symbol: Ticker symbol
        beneish_result: Dict from compute_beneish_m_score()
        altman_result: Dict from compute_altman_z_score()
        accruals_result: Dict from compute_sloan_accruals()
        forensics_score: Normalized forensics score
        governance_score: Governance score (0.0 for MVP)
        sentiment_score: Sentiment score (0.0 for MVP)
        composite_score: Weighted composite score
        first_fail_reason: First-fail reason or None
        as_of: YYYY-MM date string

    Returns:
        JSON string with complete breakdown

    Example structure:
        {
            "ticker_id": 1,
            "symbol": "AAPL",
            "as_of": "2025-11",
            "forensics": {
                "beneish": {...},
                "altman": {...},
                "accruals": {...},
                "score": 15.2
            },
            "governance": {"score": 0.0, "source": "stub"},
            "sentiment": {"score": 0.0, "source": "stub"},
            "composite": {
                "score": 15.2,
                "weights": {"forensics": 1.0, "governance": 0.0, "sentiment": 0.0}
            },
            "first_fail_reason": null,
            "generated_at": "2025-11-10T12:34:56Z"
        }
    """
    details = {
        "ticker_id": ticker_id,
        "symbol": symbol,
        "as_of": as_of,
        "forensics": {
            "beneish": {
                "m_score": beneish_result.get('m_score'),
                "components": beneish_result.get('components', {}),
                "interpretation": beneish_result.get('interpretation', '')
            },
            "altman": {
                "z_score": altman_result.get('z_score'),
                "components": altman_result.get('components', {}),
                "interpretation": altman_result.get('interpretation', '')
            },
            "accruals": {
                "ratio": accruals_result.get('accruals_ratio'),
                "interpretation": accruals_result.get('interpretation', '')
            },
            "score": round(forensics_score, 2)
        },
        "governance": {
            "score": round(governance_score, 2),
            "source": "stub" if governance_score == 0.0 else "computed"
        },
        "sentiment": {
            "score": round(sentiment_score, 2),
            "source": "stub" if sentiment_score == 0.0 else "computed"
        },
        "composite": {
            "score": round(composite_score, 2),
            "weights": {
                "forensics": 1.0,  # MVP: 100% forensics
                "governance": 0.0,
                "sentiment": 0.0
            }
        },
        "first_fail_reason": first_fail_reason,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    return json.dumps(details, indent=2)
