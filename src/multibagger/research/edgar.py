"""EDGAR filing fetcher - Cache-first SEC filing retrieval"""

import logging
import re
import time
from typing import Dict, Any, Optional

import requests

from multibagger.data.cache import HttpCache

logger = logging.getLogger(__name__)


class EDGARFetcher:
    """
    Fetch SEC EDGAR filings with caching and rate limiting.
    
    Uses SEC's full-text search and documented Company Facts API.
    Rate-limited to respect SEC guidelines (10 requests/second max).
    """
    
    BASE_URL = "https://www.sec.gov"
    COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
    
    def __init__(
        self,
        cache: HttpCache,
        user_agent: str = "MultiBagger Research/1.0",
        request_delay_ms: int = 200,
        cache_ttl_days: int = 90
    ):
        """
        Initialize EDGAR fetcher.
        
        Args:
            cache: HTTP cache instance
            user_agent: User agent string (required by SEC)
            request_delay_ms: Delay between requests in milliseconds
            cache_ttl_days: Cache TTL in days
        """
        self.cache = cache
        self.user_agent = user_agent
        self.request_delay_s = request_delay_ms / 1000.0
        self.cache_ttl_days = cache_ttl_days
        self.last_request_time = 0
        
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'errors': 0
        }
    
    def get_cik_from_ticker(self, ticker: str) -> Optional[str]:
        """
        Get CIK (Central Index Key) from ticker symbol.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            CIK string (10-digit, zero-padded) or None if not found
        """
        # SEC provides a ticker to CIK mapping JSON
        url = f"{self.BASE_URL}/files/company_tickers.json"
        
        # Check cache first
        cached_data, is_from_cache = self.cache.get(url, ttl_days=30)
        if is_from_cache:
            self.stats['cache_hits'] += 1
            mapping = cached_data
        else:
            # Fetch mapping
            self._rate_limit()
            
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=10
                )
                response.raise_for_status()
                mapping = response.json()
                
                # Cache the mapping
                self.cache.put(url, mapping, ttl_days=30)
                self.stats['api_calls'] += 1
                
            except Exception as e:
                logger.error(f"Failed to fetch CIK mapping: {e}")
                self.stats['errors'] += 1
                return None
        
        # Search for ticker in mapping
        ticker_upper = ticker.upper()
        for entry in mapping.values():
            if entry.get('ticker') == ticker_upper:
                cik = str(entry['cik_str']).zfill(10)
                return cik
        
        logger.warning(f"CIK not found for ticker {ticker}")
        return None
    
    def get_latest_filing(
        self,
        ticker: str,
        form_type: str = "10-K"
    ) -> Optional[Dict[str, Any]]:
        """
        Get the latest filing of specified type for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            form_type: Filing type (10-K, 10-Q, etc.)
            
        Returns:
            Dict with filing metadata or None if not found
        """
        cik = self.get_cik_from_ticker(ticker)
        if not cik:
            return None
        
        # Use SEC's submissions endpoint
        url = f"{self.BASE_URL}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=exclude&count=1&search_text="
        
        # Check cache
        cache_url = f"edgar_latest_{ticker}_{form_type}"
        cached_data, is_from_cache = self.cache.get(cache_url, ttl_days=self.cache_ttl_days)
        if is_from_cache:
            self.stats['cache_hits'] += 1
            return cached_data
        
        # For MVP, return minimal metadata structure
        # In production, would parse the submissions.json endpoint
        filing_metadata = {
            'ticker': ticker,
            'cik': cik,
            'form_type': form_type,
            'status': 'not_implemented',
            'message': 'Full EDGAR parsing not implemented in MVP'
        }
        
        # Cache the result
        self.cache.put(cache_url, filing_metadata, ttl_days=self.cache_ttl_days)
        
        return filing_metadata
    
    def extract_business_section(self, filing_metadata: Dict[str, Any]) -> Optional[str]:
        """
        Extract Business section text from filing.
        
        Args:
            filing_metadata: Filing metadata from get_latest_filing()
            
        Returns:
            Business section text or None if unavailable
        """
        # MVP: Return placeholder
        # Production would fetch and parse the actual 10-K HTML/XML
        if filing_metadata.get('status') == 'not_implemented':
            logger.info("Business section extraction not implemented in MVP")
            return None
        
        return None
    
    def extract_risk_factors(self, filing_metadata: Dict[str, Any]) -> Optional[str]:
        """
        Extract Risk Factors section text from filing.
        
        Args:
            filing_metadata: Filing metadata from get_latest_filing()
            
        Returns:
            Risk Factors section text or None if unavailable
        """
        # MVP: Return placeholder
        if filing_metadata.get('status') == 'not_implemented':
            logger.info("Risk factors extraction not implemented in MVP")
            return None
        
        return None
    
    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        if self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.request_delay_s:
                sleep_time = self.request_delay_s - elapsed
                time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def get_stats(self) -> Dict[str, int]:
        """Get fetcher statistics"""
        return self.stats.copy()
