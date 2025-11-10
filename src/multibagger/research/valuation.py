"""DCF valuation engine with scenario analysis"""

import logging
from typing import Dict, Any, List, Optional
import json

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.database.schema import get_engine

logger = logging.getLogger(__name__)


def compute_dcf_valuation(
    ticker_id: int,
    current_price: float,
    as_of: str,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute DCF valuation with Bear/Base/Bull scenarios.
    
    Args:
        ticker_id: Ticker ID from database
        current_price: Current stock price
        as_of: YYYY-MM format date
        config: Configuration dict with DCF parameters
        
    Returns:
        Dict with valuation results:
        - base_fair_value, bear_fair_value, bull_fair_value
        - upside_pct (base case vs current price)
        - valuation_json (full model details)
        - assumptions_json (all assumptions)
        - status: 'success' or 'insufficient_data'
    """
    dcf_config = config.get('research', {}).get('dcf', {})
    
    # Get DCF parameters
    discount_rate = dcf_config.get('discount_rate_pct', 10.0) / 100.0
    terminal_g = dcf_config.get('terminal_g_pct', 2.5) / 100.0
    projection_years = dcf_config.get('projection_years', 5)
    growth_spread = dcf_config.get('growth_spread_pct', 4.0) / 100.0
    margin_spread = dcf_config.get('margin_spread_pct', 2.0) / 100.0
    tax_rate = dcf_config.get('tax_rate_pct', 25.0) / 100.0
    
    # Fetch historical fundamentals
    engine = get_engine()
    with Session(engine) as session:
        # Get fiscal year cutoff
        year, month = map(int, as_of.split('-'))
        max_fiscal_year = year - 1
        
        result = session.execute(
            text("""
                SELECT 
                    fiscal_year,
                    revenue,
                    gross_profit,
                    operating_income,
                    net_income,
                    depreciation,
                    operating_cash_flow,
                    free_cash_flow,
                    total_assets,
                    current_assets,
                    current_liabilities,
                    ppe,
                    receivables,
                    cash
                FROM fundamentals
                WHERE ticker_id = :tid AND fiscal_year <= :max_fy
                ORDER BY fiscal_year DESC
                LIMIT 5
            """),
            {'tid': ticker_id, 'max_fy': max_fiscal_year}
        ).fetchall()
        
        if len(result) < 3:
            logger.warning(f"Insufficient data for DCF: only {len(result)} years")
            return {
                'status': 'insufficient_data',
                'base_fair_value': None,
                'bear_fair_value': None,
                'bull_fair_value': None,
                'upside_pct': None,
                'valuation_json': json.dumps({'error': 'insufficient_historical_data'}),
                'assumptions_json': json.dumps({'min_years_required': 3, 'available': len(result)})
            }
        
        # Convert to DataFrame for easier calculations
        df = pd.DataFrame(result, columns=[
            'fiscal_year', 'revenue', 'gross_profit', 'operating_income',
            'net_income', 'depreciation', 'operating_cash_flow', 'free_cash_flow',
            'total_assets', 'current_assets', 'current_liabilities',
            'ppe', 'receivables', 'cash'
        ])
        df = df.sort_values('fiscal_year')
    
    # Calculate historical metrics
    revenue_cagr = _calculate_cagr(df['revenue'].iloc[0], df['revenue'].iloc[-1], len(df) - 1)
    avg_margin = (df['operating_income'] / df['revenue']).mean() if df['revenue'].sum() > 0 else 0.10
    
    # Check for sufficient FCF history
    positive_fcf_years = (df['free_cash_flow'] > 0).sum() if 'free_cash_flow' in df.columns else 0
    min_fcf_years = config.get('research', {}).get('guardrails', {}).get('min_fcf_years', 3)
    
    if positive_fcf_years < min_fcf_years:
        logger.warning(f"Insufficient positive FCF years: {positive_fcf_years}/{min_fcf_years}")
        return {
            'status': 'insufficient_fcf',
            'base_fair_value': None,
            'bear_fair_value': None,
            'bull_fair_value': None,
            'upside_pct': None,
            'valuation_json': json.dumps({'error': 'insufficient_positive_fcf_years'}),
            'assumptions_json': json.dumps({'positive_fcf_years': int(positive_fcf_years), 'required': min_fcf_years})
        }
    
    # Build scenarios
    scenarios = {
        'base': {'growth': revenue_cagr, 'margin': avg_margin},
        'bull': {'growth': revenue_cagr + growth_spread, 'margin': avg_margin + margin_spread},
        'bear': {'growth': max(revenue_cagr - growth_spread, 0.01), 'margin': max(avg_margin - margin_spread, 0.05)}
    }
    
    # Calculate DCF for each scenario
    dcf_results = {}
    for scenario_name, params in scenarios.items():
        dcf = _project_dcf(
            base_revenue=df['revenue'].iloc[-1],
            growth_rate=params['growth'],
            operating_margin=params['margin'],
            tax_rate=tax_rate,
            discount_rate=discount_rate,
            terminal_g=terminal_g,
            years=projection_years
        )
        dcf_results[scenario_name] = dcf
    
    # Calculate upside
    base_fair_value = dcf_results['base']['fair_value_per_share']
    upside_pct = ((base_fair_value - current_price) / current_price * 100) if current_price > 0 else None
    
    # Prepare JSON payloads
    valuation_json = json.dumps({
        'scenarios': dcf_results,
        'historical_cagr': float(revenue_cagr),
        'avg_margin': float(avg_margin),
        'positive_fcf_years': int(positive_fcf_years)
    })
    
    assumptions_json = json.dumps({
        'discount_rate': discount_rate,
        'terminal_g': terminal_g,
        'tax_rate': tax_rate,
        'projection_years': projection_years,
        'growth_spread': growth_spread,
        'margin_spread': margin_spread,
        'base_revenue': float(df['revenue'].iloc[-1]),
        'fiscal_years_used': df['fiscal_year'].tolist()
    })
    
    return {
        'status': 'success',
        'base_fair_value': float(dcf_results['base']['fair_value_per_share']),
        'bear_fair_value': float(dcf_results['bear']['fair_value_per_share']),
        'bull_fair_value': float(dcf_results['bull']['fair_value_per_share']),
        'upside_pct': float(upside_pct) if upside_pct is not None else None,
        'valuation_json': valuation_json,
        'assumptions_json': assumptions_json
    }


def compute_comparables(
    ticker_id: int,
    sector_id: Optional[int],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute peer comparables analysis.
    
    Args:
        ticker_id: Ticker ID
        sector_id: Sector ID for peer selection
        config: Configuration dict
        
    Returns:
        Dict with comparables analysis:
        - peers: List of peer ticker symbols
        - median_pe, median_ev_ebit, median_ev_fcf
        - comps_json: Full comparable details
    """
    max_peers = config.get('research', {}).get('limits', {}).get('max_peers_for_comps', 10)
    
    if not sector_id:
        return {
            'peers': [],
            'median_pe': None,
            'median_ev_ebit': None,
            'median_ev_fcf': None,
            'comps_json': json.dumps({'error': 'no_sector_for_peer_selection'})
        }
    
    engine = get_engine()
    with Session(engine) as session:
        # Get peers in same sector
        result = session.execute(
            text("""
                SELECT t.id, t.symbol, t.market_cap,
                       f.roce, f.revenue_growth_5y, f.gross_margin
                FROM tickers t
                INNER JOIN factors f ON t.id = f.ticker_id
                WHERE t.sector_id = :sector_id
                  AND t.id != :ticker_id
                  AND t.active = 1
                  AND t.market_cap > 0
                ORDER BY t.market_cap DESC
                LIMIT :max_peers
            """),
            {'sector_id': sector_id, 'ticker_id': ticker_id, 'max_peers': max_peers}
        ).fetchall()
        
        if len(result) == 0:
            return {
                'peers': [],
                'median_pe': None,
                'median_ev_ebit': None,
                'median_ev_fcf': None,
                'comps_json': json.dumps({'error': 'no_peers_found'})
            }
        
        peers = [{'ticker_id': r[0], 'symbol': r[1], 'market_cap': float(r[2])} for r in result]
        
        # For MVP, return basic peer list
        # Production would calculate actual multiples
        comps_json = json.dumps({
            'peers': peers,
            'count': len(peers),
            'note': 'Full multiples calculation not implemented in MVP'
        })
        
        return {
            'peers': [p['symbol'] for p in peers],
            'median_pe': None,
            'median_ev_ebit': None,
            'median_ev_fcf': None,
            'comps_json': comps_json
        }


def _calculate_cagr(start_value: float, end_value: float, years: int) -> float:
    """Calculate Compound Annual Growth Rate"""
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return 0.0
    return (end_value / start_value) ** (1 / years) - 1


def _project_dcf(
    base_revenue: float,
    growth_rate: float,
    operating_margin: float,
    tax_rate: float,
    discount_rate: float,
    terminal_g: float,
    years: int
) -> Dict[str, Any]:
    """
    Project DCF model and calculate fair value.
    
    Returns dict with projections and fair value calculation.
    """
    projections = []
    pv_fcfs = []
    
    for year in range(1, years + 1):
        # Project revenue
        revenue = base_revenue * ((1 + growth_rate) ** year)
        
        # Project operating income
        operating_income = revenue * operating_margin
        
        # Project NOPAT (Net Operating Profit After Tax)
        nopat = operating_income * (1 - tax_rate)
        
        # Simplified FCF (would add D&A, CapEx, NWC changes in production)
        fcf = nopat * 0.85  # Assume 15% reinvestment
        
        # Discount to present value
        discount_factor = (1 + discount_rate) ** year
        pv_fcf = fcf / discount_factor
        
        projections.append({
            'year': year,
            'revenue': float(revenue),
            'operating_income': float(operating_income),
            'nopat': float(nopat),
            'fcf': float(fcf),
            'discount_factor': float(discount_factor),
            'pv_fcf': float(pv_fcf)
        })
        pv_fcfs.append(pv_fcf)
    
    # Terminal value (Gordon Growth)
    terminal_fcf = projections[-1]['fcf'] * (1 + terminal_g)
    terminal_value = terminal_fcf / (discount_rate - terminal_g)
    pv_terminal_value = terminal_value / ((1 + discount_rate) ** years)
    
    # Enterprise value
    enterprise_value = sum(pv_fcfs) + pv_terminal_value
    
    # Assume shares outstanding = market cap / current price (simplified)
    # For MVP, return per-share value assuming 1B shares
    shares_outstanding = 1_000_000_000
    fair_value_per_share = enterprise_value / shares_outstanding
    
    return {
        'projections': projections,
        'terminal_value': float(terminal_value),
        'pv_terminal_value': float(pv_terminal_value),
        'enterprise_value': float(enterprise_value),
        'fair_value_per_share': float(fair_value_per_share),
        'pv_fcf_sum': float(sum(pv_fcfs))
    }
