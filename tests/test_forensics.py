"""Tests for forensic accounting metrics and risk scoring"""

import pandas as pd
import pytest

from multibagger.forensics import (
    compute_altman_z_score,
    compute_beneish_m_score,
    compute_forensics_score,
    compute_sloan_accruals,
)
from multibagger.risk import compute_composite_score, determine_first_fail


class TestBeneishMScore:
    """Test Beneish M-Score calculation"""

    def test_insufficient_data(self):
        """Test handling of insufficient data (< 2 years)"""
        fundamentals = pd.DataFrame([{
            'fiscal_year': 2024,
            'revenue': 1000,
            'receivables': 100,
            'gross_profit': 300,
            'current_assets': 500,
            'ppe': 200,
            'non_current_assets': 300,
            'total_assets': 800,
            'depreciation': 20,
            'sga_expense': 100,
            'long_term_debt': 200
        }])

        result = compute_beneish_m_score(fundamentals)

        assert result['m_score'] is None
        assert 'Insufficient data' in result['interpretation']

    def test_manipulation_detection(self):
        """Test detection of high M-Score (manipulation risk)"""
        # Create synthetic data with manipulation signals
        fundamentals = pd.DataFrame([
            {
                'fiscal_year': 2024,
                'revenue': 2000,  # 100% growth (SGI = 2.0)
                'receivables': 500,  # 150% growth (DSRI = 1.5)
                'gross_profit': 600,  # 30% margin vs 40% prior (GMI = 1.33)
                'current_assets': 1000,
                'ppe': 200,
                'non_current_assets': 300,
                'total_assets': 1300,
                'depreciation': 20,
                'sga_expense': 150,
                'long_term_debt': 300
            },
            {
                'fiscal_year': 2023,
                'revenue': 1000,
                'receivables': 200,
                'gross_profit': 400,  # 40% margin
                'current_assets': 600,
                'ppe': 180,
                'non_current_assets': 270,
                'total_assets': 870,
                'depreciation': 18,
                'sga_expense': 100,
                'long_term_debt': 200
            }
        ])

        result = compute_beneish_m_score(fundamentals)

        assert result['m_score'] is not None
        assert 'components' in result
        assert 'interpretation' in result
        # High growth + rising receivables often triggers manipulation signal
        assert result['components']['SGI'] > 1.0  # Revenue growth
        assert result['components']['DSRI'] > 1.0  # Rising receivables


class TestAltmanZScore:
    """Test Altman Z-Score calculation"""

    def test_insufficient_data(self):
        """Test handling of missing required fields"""
        fundamentals = pd.Series({
            'fiscal_year': 2024,
            'total_assets': None
        })

        result = compute_altman_z_score(fundamentals, market_cap=1000000)

        assert result['z_score'] is None
        assert 'Insufficient data' in result['interpretation']

    def test_distress_zone(self):
        """Test detection of distress zone (Z < 1.81)"""
        fundamentals = pd.Series({
            'fiscal_year': 2024,
            'current_assets': 100,
            'current_liabilities': 150,  # Negative working capital
            'total_assets': 500,
            'retained_earnings': -50,  # Negative RE
            'ebit': 10,  # Low profitability
            'total_liabilities': 400,
            'revenue': 200
        })
        market_cap = 50000  # Low market cap relative to liabilities

        result = compute_altman_z_score(fundamentals, market_cap)

        assert result['z_score'] is not None
        assert result['z_score'] < 1.81  # Distress zone
        assert 'distress' in result['interpretation'].lower()

    def test_safe_zone(self):
        """Test detection of safe zone (Z > 2.99)"""
        fundamentals = pd.Series({
            'fiscal_year': 2024,
            'current_assets': 600,
            'current_liabilities': 200,  # Strong working capital
            'total_assets': 1000,
            'retained_earnings': 400,  # High retained earnings
            'ebit': 200,  # Strong profitability
            'total_liabilities': 300,
            'revenue': 1500
        })
        market_cap = 2000000  # High market cap

        result = compute_altman_z_score(fundamentals, market_cap)

        assert result['z_score'] is not None
        assert result['z_score'] > 2.99  # Safe zone
        assert 'safe' in result['interpretation'].lower()


class TestSloanAccruals:
    """Test Sloan Accruals calculation"""

    def test_insufficient_data(self):
        """Test handling of insufficient data (< 2 years)"""
        fundamentals = pd.DataFrame([{
            'fiscal_year': 2024,
            'current_assets': 500,
            'cash': 100,
            'current_liabilities': 200,
            'short_term_debt': 50,
            'depreciation': 20,
            'total_assets': 1000
        }])

        result = compute_sloan_accruals(fundamentals)

        assert result['accruals_ratio'] is None
        assert 'Insufficient data' in result['interpretation']

    def test_high_accruals_warning(self):
        """Test detection of high accruals (earnings quality concern)"""
        fundamentals = pd.DataFrame([
            {
                'fiscal_year': 2024,
                'current_assets': 800,  # Large increase
                'cash': 100,
                'current_liabilities': 300,  # Large increase
                'short_term_debt': 50,
                'depreciation': 20,
                'total_assets': 1200
            },
            {
                'fiscal_year': 2023,
                'current_assets': 400,
                'cash': 100,
                'current_liabilities': 150,
                'short_term_debt': 40,
                'depreciation': 18,
                'total_assets': 900
            }
        ])

        result = compute_sloan_accruals(fundamentals)

        assert result['accruals_ratio'] is not None
        # Large increase in current assets/liabilities signals high accruals
        assert result['accruals_ratio'] > 0.05


class TestForensicsScore:
    """Test normalized forensics score computation"""

    def test_low_risk_scenario(self):
        """Test low-risk stock produces low forensics score"""
        beneish = {'m_score': -3.0, 'interpretation': 'Low risk'}  # Below cutoff
        altman = {'z_score': 3.5, 'interpretation': 'Safe'}  # Above safe zone
        accruals = {'accruals_ratio': 0.02, 'interpretation': 'Low'}  # Low accruals

        score = compute_forensics_score(beneish, altman, accruals)

        assert 0 <= score <= 100
        assert score < 30  # Low risk should have low score

    def test_high_risk_scenario(self):
        """Test high-risk stock produces high forensics score"""
        beneish = {'m_score': -1.5, 'interpretation': 'High risk'}  # Above cutoff
        altman = {'z_score': 1.2, 'interpretation': 'Distress'}  # Distress zone
        accruals = {'accruals_ratio': 0.15, 'interpretation': 'High'}  # High accruals

        score = compute_forensics_score(beneish, altman, accruals)

        assert 0 <= score <= 100
        assert score > 60  # High risk should have high score

    def test_missing_data_handling(self):
        """Test handling of None values in metrics"""
        beneish = {'m_score': None, 'interpretation': 'Insufficient data'}
        altman = {'z_score': None, 'interpretation': 'Insufficient data'}
        accruals = {'accruals_ratio': None, 'interpretation': 'Insufficient data'}

        score = compute_forensics_score(beneish, altman, accruals)

        # Should return maximum risk score when no data available
        assert score == 100.0


class TestCompositeScore:
    """Test composite risk score calculation"""

    def test_mvp_weights_forensics_only(self):
        """Test MVP configuration (100% forensics)"""
        weights = {'forensics': 1.0, 'governance': 0.0, 'sentiment': 0.0}

        score = compute_composite_score(
            forensics_score=25.0,
            governance_score=50.0,  # Should be ignored
            sentiment_score=75.0,   # Should be ignored
            weights=weights
        )

        assert score == 25.0  # Should equal forensics_score exactly

    def test_balanced_weights(self):
        """Test balanced weighting"""
        weights = {'forensics': 0.5, 'governance': 0.3, 'sentiment': 0.2}

        score = compute_composite_score(
            forensics_score=20.0,
            governance_score=30.0,
            sentiment_score=40.0,
            weights=weights
        )

        expected = 20.0 * 0.5 + 30.0 * 0.3 + 40.0 * 0.2
        assert score == expected

    def test_score_bounds(self):
        """Test score is bounded to 0-100 range"""
        weights = {'forensics': 2.0, 'governance': 0.0, 'sentiment': 0.0}

        score = compute_composite_score(
            forensics_score=100.0,
            governance_score=0.0,
            sentiment_score=0.0,
            weights=weights
        )

        assert score == 100.0  # Should be capped at 100


class TestFirstFail:
    """Test first-fail priority ordering"""

    def test_no_failures(self):
        """Test stock passes all checks"""
        metrics = {
            'beneish_m_score': -3.0,  # Pass
            'altman_z_score': 3.0,    # Pass
            'accruals_ratio': 0.05    # Pass
        }
        thresholds = {
            'beneish_cutoff': -2.22,
            'altman_distress': 1.81,
            'sloan_warning': 0.10
        }

        result = determine_first_fail(metrics, thresholds)

        assert result is None  # No failures

    def test_beneish_priority_1(self):
        """Test Beneish has highest priority"""
        metrics = {
            'beneish_m_score': -2.0,  # FAIL (above -2.22)
            'altman_z_score': 1.5,    # FAIL (below 1.81)
            'accruals_ratio': 0.15    # FAIL (above 0.10)
        }
        thresholds = {
            'beneish_cutoff': -2.22,
            'altman_distress': 1.81,
            'sloan_warning': 0.10
        }

        result = determine_first_fail(metrics, thresholds)

        assert result == "beneish_m_score_high"  # Beneish wins despite all failing

    def test_altman_priority_2(self):
        """Test Altman has second priority when Beneish passes"""
        metrics = {
            'beneish_m_score': -3.0,  # Pass
            'altman_z_score': 1.5,    # FAIL (below 1.81)
            'accruals_ratio': 0.15    # FAIL (above 0.10)
        }
        thresholds = {
            'beneish_cutoff': -2.22,
            'altman_distress': 1.81,
            'sloan_warning': 0.10
        }

        result = determine_first_fail(metrics, thresholds)

        assert result == "altman_z_score_distress"  # Altman wins

    def test_sloan_priority_3(self):
        """Test Sloan has third priority when Beneish and Altman pass"""
        metrics = {
            'beneish_m_score': -3.0,  # Pass
            'altman_z_score': 3.0,    # Pass
            'accruals_ratio': 0.15    # FAIL (above 0.10)
        }
        thresholds = {
            'beneish_cutoff': -2.22,
            'altman_distress': 1.81,
            'sloan_warning': 0.10
        }

        result = determine_first_fail(metrics, thresholds)

        assert result == "sloan_accruals_high"  # Sloan triggered

    def test_missing_metrics(self):
        """Test handling of None/missing metrics"""
        metrics = {
            'beneish_m_score': None,  # Missing
            'altman_z_score': None,   # Missing
            'accruals_ratio': 0.15    # FAIL
        }
        thresholds = {
            'beneish_cutoff': -2.22,
            'altman_distress': 1.81,
            'sloan_warning': 0.10
        }

        result = determine_first_fail(metrics, thresholds)

        # Should trigger Sloan since Beneish/Altman are None
        assert result == "sloan_accruals_high"
