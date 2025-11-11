"""Data fetcher with unified interface across sources"""

import logging
from datetime import date, datetime

from multibagger.common.http import create_http_session
from multibagger.common.utils import chunk_list

from .cache import HttpCache
from .config import DataConfig
from .models import FetchResult, FundamentalSnapshot, InstrumentMeta, PriceBar

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Unified data fetcher with cache-first architecture.

    Lookup order: In-memory → SQLite → Network
    """

    def __init__(self, config: DataConfig | None = None):
        self.config = config or DataConfig.create_default()
        self.cache = HttpCache()
        self.session = create_http_session()

        # Track statistics
        self._cache_hits = 0
        self._network_calls = 0

    def get_prices(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        force_refresh: bool = False,
    ) -> FetchResult:
        """
        Fetch price data for multiple tickers.

        Args:
            tickers: List of ticker symbols
            start_date: Start date
            end_date: End date
            force_refresh: Skip cache

        Returns:
            FetchResult with price bars
        """
        start_time = datetime.utcnow()
        records = []
        errors = []

        # Batch fetch for efficiency
        for chunk in chunk_list(tickers, self.config.batch_size):
            for ticker in chunk:
                try:
                    prices = self._fetch_prices_single(
                        ticker, start_date, end_date, force_refresh
                    )
                    records.extend(prices)
                except Exception as e:
                    errors.append(f"{ticker}: {str(e)}")
                    logger.error(f"Failed to fetch prices for {ticker}: {e}")

        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return FetchResult(
            records=records,
            cache_hits=self._cache_hits,
            network_calls=self._network_calls,
            execution_time_ms=execution_time,
            errors=errors,
            source="yahoo",
            fetched_at=datetime.utcnow(),
        )

    def _fetch_prices_single(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        force_refresh: bool,
    ) -> list[PriceBar]:
        """Fetch prices for a single ticker (placeholder)"""
        # This is a placeholder - real implementation would use yfinance
        cache_key = f"prices_{ticker}_{start_date}_{end_date}"

        if not force_refresh:
            cached, from_cache = self.cache.get(
                cache_key, ttl_days=self.config.cache.ttl_prices
            )
            if from_cache:
                self._cache_hits += 1
                return cached

        # Network fetch would go here
        self._network_calls += 1

        # Placeholder return
        return []

    def get_fundamentals(
        self,
        tickers: list[str],
        period: str = "annual",
        force_refresh: bool = False,
    ) -> FetchResult:
        """
        Fetch fundamental data.

        Args:
            tickers: List of ticker symbols
            period: 'annual' or 'quarterly'
            force_refresh: Skip cache

        Returns:
            FetchResult with fundamentals
        """
        start_time = datetime.utcnow()
        records = []
        errors = []

        for ticker in tickers:
            try:
                fundamentals = self._fetch_fundamentals_single(ticker, period, force_refresh)
                records.extend(fundamentals)
            except Exception as e:
                errors.append(f"{ticker}: {str(e)}")

        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return FetchResult(
            records=records,
            cache_hits=self._cache_hits,
            network_calls=self._network_calls,
            execution_time_ms=execution_time,
            errors=errors,
            source="yahoo",
            fetched_at=datetime.utcnow(),
        )

    def _fetch_fundamentals_single(
        self,
        ticker: str,
        period: str,
        force_refresh: bool,
    ) -> list[FundamentalSnapshot]:
        """Fetch fundamentals for a single ticker (placeholder)"""
        cache_key = f"fundamentals_{ticker}_{period}"

        if not force_refresh:
            cached, from_cache = self.cache.get(
                cache_key, ttl_days=self.config.cache.ttl_fundamentals
            )
            if from_cache:
                self._cache_hits += 1
                return cached

        self._network_calls += 1
        return []

    def warm_cache(self, as_of: datetime) -> dict:
        """
        Warm cache with commonly used data.

        Args:
            as_of: Date to warm cache for

        Returns:
            Statistics dictionary
        """
        summary = {
            "instruments_fetched": 0,
            "prices_fetched": 0,
            "fundamentals_fetched": 0,
            "filings_fetched": 0,
            "cache_hits": self._cache_hits,
            "network_calls": self._network_calls,
            "execution_time_ms": 0,
        }

        # Placeholder implementation
        logger.info(f"Cache warming for {as_of} - placeholder")

        return summary

    def get_cache_stats(self) -> "CacheStats":  # noqa: F821
        """Get cache statistics"""
        return self.cache.get_stats()

    def prune_cache(self, older_than_days: int) -> int:
        """Prune old cache entries"""
        return self.cache.prune(older_than_days)
