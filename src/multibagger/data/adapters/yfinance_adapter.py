"""yfinance adapter for fetching prices and fundamentals"""

import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from multibagger.common.utils import chunk_list

logger = logging.getLogger(__name__)


class YFinanceAdapter:
    """
    Adapter for Yahoo Finance data via yfinance library.

    Provides batch fetching for prices and fundamentals.
    """

    def __init__(self, batch_size: int = 50, delay_seconds: float = 1.0):
        self.batch_size = batch_size
        self.delay_seconds = delay_seconds

        # Lazy import yfinance
        try:
            import yfinance as yf
            self.yf = yf
        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            raise

    def fetch_prices_batch(
        self,
        symbols: list[str],
        period: str = "90d",
        progress_callback=None,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch prices for multiple tickers in batches.

        Args:
            symbols: List of ticker symbols
            period: Time period (e.g., '90d', '1y')
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Dict mapping symbol → DataFrame with columns [Date, Open, High, Low, Close, Volume]
        """
        results = {}
        chunks = chunk_list(symbols, self.batch_size)
        total_chunks = len(chunks)

        logger.info(f"Fetching prices for {len(symbols)} symbols in {total_chunks} batches")

        for i, chunk in enumerate(chunks):
            try:
                # Download batch
                logger.debug(f"Batch {i+1}/{total_chunks}: {len(chunk)} symbols")

                data = self.yf.download(
                    chunk,
                    period=period,
                    group_by='ticker',
                    auto_adjust=False,
                    progress=False,
                    threads=False,  # Disable threading for compatibility
                )

                # Parse results
                if len(chunk) == 1:
                    # Single ticker - data is DataFrame
                    symbol = chunk[0]
                    if not data.empty:
                        results[symbol] = data
                else:
                    # Multiple tickers - data is MultiIndex DataFrame
                    for symbol in chunk:
                        try:
                            if symbol in data.columns.levels[0]:
                                ticker_data = data[symbol]
                                if not ticker_data.empty and not ticker_data['Close'].isna().all():
                                    results[symbol] = ticker_data
                                else:
                                    logger.warning(f"No valid data for {symbol}")
                        except (KeyError, IndexError, AttributeError) as e:
                            logger.warning(f"Failed to parse {symbol}: {e}")

                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_chunks)

                # Polite delay between batches
                if i < total_chunks - 1:
                    time.sleep(self.delay_seconds)

            except Exception as e:
                logger.error(f"Batch {i+1} failed: {e}")
                continue

        logger.info(f"Successfully fetched prices for {len(results)}/{len(symbols)} symbols")
        return results

    def fetch_fundamentals(
        self,
        symbol: str,
        years: int = 5,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch fundamentals for a single ticker.

        Args:
            symbol: Ticker symbol
            years: Number of years of history

        Returns:
            Dict with keys: financials, balance_sheet, cashflow
        """
        try:
            ticker = self.yf.Ticker(symbol)

            # Fetch annual statements
            result = {
                'financials': ticker.financials,  # Income statement
                'balance_sheet': ticker.balance_sheet,
                'cashflow': ticker.cashflow,
            }

            # Limit to N years
            for key in result:
                if result[key] is not None and not result[key].empty:
                    result[key] = result[key].iloc[:, :years]

            return result

        except Exception as e:
            logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
            return {'financials': pd.DataFrame(), 'balance_sheet': pd.DataFrame(), 'cashflow': pd.DataFrame()}

    def fetch_info(self, symbol: str) -> dict:
        """
        Fetch ticker info (market cap, sector, etc.)

        Args:
            symbol: Ticker symbol

        Returns:
            Info dict
        """
        try:
            ticker = self.yf.Ticker(symbol)
            return ticker.info
        except Exception as e:
            logger.error(f"Failed to fetch info for {symbol}: {e}")
            return {}
