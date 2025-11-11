"""Business profile extraction from filings and local data"""

import logging
from typing import Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.database.schema import get_engine
from .edgar import EDGARFetcher

logger = logging.getLogger(__name__)


def extract_business_profile(
    ticker_id: int,
    ticker_symbol: str,
    as_of: str,
    edgar_fetcher: Optional[EDGARFetcher] = None
) -> Dict[str, Any]:
    """
    Extract business profile combining filings and local data.
    
    Args:
        ticker_id: Ticker ID from database
        ticker_symbol: Stock ticker symbol
        as_of: YYYY-MM format date
        edgar_fetcher: Optional EDGAR fetcher instance
        
    Returns:
        Dict with business profile fields:
        - business_model: Revenue model description
        - moat: Competitive advantage type
        - growth_drivers: Key growth catalysts
        - top_risks: Top risks
        - sources_json: Provenance data
    """
    profile = {
        'business_model': 'unknown',
        'moat': 'unknown',
        'growth_drivers': 'Insufficient data for analysis',
        'top_risks': 'Insufficient data for analysis',
        'sources': []
    }
    
    # Try to fetch company metadata from local DB
    engine = get_engine()
    with Session(engine) as session:
        result = session.execute(
            text("""
                SELECT t.symbol, t.name, s.name as sector, t.exchange_id
                FROM tickers t
                LEFT JOIN sectors s ON t.sector_id = s.id
                WHERE t.id = :ticker_id
            """),
            {'ticker_id': ticker_id}
        ).first()
        
        if result:
            profile['sources'].append({
                'type': 'local_db',
                'table': 'tickers',
                'fields': ['symbol', 'name', 'sector']
            })
            
            # Basic inference from sector
            sector = result.sector if result.sector else 'Unknown'
            profile['business_model'] = f"{sector} business"
            
            # Sector-based moat heuristics (very simplistic for MVP)
            moat_by_sector = {
                'Technology': 'network_effects',
                'Healthcare': 'ip_brand',
                'Financial Services': 'scale',
                'Consumer': 'brand',
                'Industrial': 'cost_advantage'
            }
            profile['moat'] = moat_by_sector.get(sector, 'unknown')
    
    # Try EDGAR filing if available
    if edgar_fetcher:
        try:
            filing = edgar_fetcher.get_latest_filing(ticker_symbol, form_type="10-K")
            
            if filing and filing.get('status') != 'not_implemented':
                # Extract business section
                business_text = edgar_fetcher.extract_business_section(filing)
                if business_text:
                    profile['business_model'] = _parse_business_model(business_text)
                    profile['moat'] = _infer_moat(business_text)
                    profile['growth_drivers'] = _extract_growth_drivers(business_text)
                
                # Extract risk factors
                risk_text = edgar_fetcher.extract_risk_factors(filing)
                if risk_text:
                    profile['top_risks'] = _extract_top_risks(risk_text)
                
                profile['sources'].append({
                    'type': 'edgar_filing',
                    'cik': filing.get('cik'),
                    'form_type': filing.get('form_type'),
                    'ticker': ticker_symbol
                })
        except Exception as e:
            logger.warning(f"Failed to fetch EDGAR data for {ticker_symbol}: {e}")
    
    return profile


def _parse_business_model(text: str) -> str:
    """
    Parse business model from Business section text.
    
    MVP: Returns placeholder. Production would use NLP/LLM parsing.
    """
    # Placeholder for MVP
    return "Business model description unavailable (full parsing not implemented)"


def _infer_moat(text: str) -> str:
    """
    Infer moat type from Business section.
    
    MVP: Simple keyword matching. Production would use LLM classification.
    """
    text_lower = text.lower()
    
    # Simple keyword heuristics
    if any(kw in text_lower for kw in ['network effect', 'platform', 'marketplace']):
        return 'network_effects'
    elif any(kw in text_lower for kw in ['patent', 'proprietary', 'brand', 'trademark']):
        return 'ip_brand'
    elif any(kw in text_lower for kw in ['scale', 'economies of scale', 'largest']):
        return 'scale'
    elif any(kw in text_lower for kw in ['switching cost', 'sticky', 'lock-in']):
        return 'switching_costs'
    elif any(kw in text_lower for kw in ['low cost', 'efficient', 'cost advantage']):
        return 'cost_advantage'
    
    return 'unknown'


def _extract_growth_drivers(text: str) -> str:
    """
    Extract growth drivers from Business section.
    
    MVP: Placeholder. Production would use NLP extraction.
    """
    return "Growth drivers analysis unavailable (full parsing not implemented)"


def _extract_top_risks(text: str) -> str:
    """
    Extract top 5 risks from Risk Factors section.
    
    MVP: Placeholder. Production would parse and rank risks.
    """
    return "Risk factors analysis unavailable (full parsing not implemented)"
