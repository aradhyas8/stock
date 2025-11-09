"""Data adapters for fetching universe data from official exchange sources"""

import csv
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd
import requests

from multibagger.config import Config
from multibagger.data.cache import HttpCache

logger = logging.getLogger(__name__)


@dataclass
class UniverseEntry:
    """Raw universe entry from exchange data"""

    symbol: str
    name: str
    exchange_code: str
    market_cap: float | None = None
    sector: str | None = None
    industry: str | None = None
    is_active: bool = True
    is_etf: bool = False
    is_adr: bool = False
    is_common_equity: bool = True
    raw_data: dict | None = None


class UniverseAdapter(ABC):
    """Abstract base class for universe data adapters"""

    def __init__(self, config: Config, cache: HttpCache):
        self.config = config
        self.cache = cache
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.data.get("sources", {})
                .get("yahoo", {})
                .get("user_agent", "MultiBagger/1.0")
            }
        )

    @abstractmethod
    def fetch_universe(self) -> list[UniverseEntry]:
        """Fetch universe data from source"""
        pass

    @abstractmethod
    def get_exchange_codes(self) -> list[str]:
        """Return list of exchange codes this adapter handles"""
        pass

    def _make_request(self, url: str, ttl_days: int = 1) -> str | None:
        """Make HTTP request with caching"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None


class USUniverseAdapter(UniverseAdapter):
    """Adapter for US market data (NYSE, NASDAQ, S&P 500)"""

    def get_exchange_codes(self) -> list[str]:
        return ["NYSE", "NASDAQ"]

    def fetch_universe(self) -> list[UniverseEntry]:
        """Fetch US universe from NASDAQ/NYSE directories and S&P 500"""
        entries = []

        # Fetch NASDAQ listed securities
        nasdaq_entries = self._fetch_nasdaq_listed()
        entries.extend(nasdaq_entries)

        # Fetch NYSE listed securities
        nyse_entries = self._fetch_nyse_listed()
        entries.extend(nyse_entries)

        # Add S&P 500 (subset of above, but ensures coverage)
        sp500_entries = self._fetch_sp500()
        entries.extend(sp500_entries)

        # Remove duplicates by symbol
        seen_symbols = set()
        unique_entries = []
        for entry in entries:
            if entry.symbol not in seen_symbols:
                seen_symbols.add(entry.symbol)
                unique_entries.append(entry)

        logger.info(f"US Universe: {len(unique_entries)} unique symbols")
        return unique_entries

    def _fetch_nasdaq_listed(self) -> list[UniverseEntry]:
        """Fetch NASDAQ listed securities"""
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        data = self._make_request(url)
        if not data:
            return []

        entries = []
        lines = data.strip().split("\n")
        headers = lines[0].lower().split("|")

        for line in lines[1:]:
            if not line.strip() or line.startswith("File Creation"):
                continue

            parts = line.split("|")
            if len(parts) < len(headers):
                continue

            row = dict(zip(headers, parts, strict=False))
            symbol = row.get("symbol", "").strip()

            if not symbol or symbol in ["File", "Creation", "Time"]:
                continue

            # Determine security type
            financial_status = row.get("financial status", "").strip()
            is_etf = row.get("etf", "N").strip().upper() == "Y"

            # Skip test symbols and non-trading securities
            if financial_status in ["D", "E", "Q", "G", "H", "J", "K"]:
                continue

            entry = UniverseEntry(
                symbol=symbol,
                name=row.get("security name", "").strip(),
                exchange_code="NASDAQ",
                is_etf=is_etf,
                is_active=financial_status not in ["D", "E"],
                raw_data=row,
            )
            entries.append(entry)

        logger.info(f"NASDAQ: {len(entries)} securities")
        return entries

    def _fetch_nyse_listed(self) -> list[UniverseEntry]:
        """Fetch NYSE listed securities"""
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
        data = self._make_request(url)
        if not data:
            return []

        entries = []
        lines = data.strip().split("\n")
        headers = lines[0].lower().split("|")

        for line in lines[1:]:
            if not line.strip() or line.startswith("File Creation"):
                continue

            parts = line.split("|")
            if len(parts) < len(headers):
                continue

            row = dict(zip(headers, parts, strict=False))
            symbol = row.get("act symbol", "").strip()
            exchange = row.get("exchange", "").strip()

            if not symbol or exchange not in [
                "N",
                "P",
                "Z",
            ]:  # NYSE, NYSE Arca, NYSE MKT
                continue

            # Map exchange codes
            exchange_map = {"N": "NYSE", "P": "NYSE", "Z": "NYSE"}
            exchange_code = exchange_map.get(exchange, "NYSE")

            # Determine security type
            security_type = row.get("security name", "").strip()
            is_etf = "ETF" in security_type.upper() or "ETN" in security_type.upper()

            entry = UniverseEntry(
                symbol=symbol,
                name=security_type,
                exchange_code=exchange_code,
                is_etf=is_etf,
                raw_data=row,
            )
            entries.append(entry)

        logger.info(f"NYSE: {len(entries)} securities")
        return entries

    def _fetch_sp500(self) -> list[UniverseEntry]:
        """Fetch S&P 500 constituents"""
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        try:
            tables = pd.read_html(url)
            sp500_df = tables[0]  # First table contains the list

            entries = []
            for _, row in sp500_df.iterrows():
                symbol = str(row.get("Symbol", "")).strip()
                if not symbol:
                    continue

                entry = UniverseEntry(
                    symbol=symbol,
                    name=str(row.get("Security", "")).strip(),
                    exchange_code="NYSE",  # Most S&P 500 are NYSE, will be corrected by other sources
                    sector=str(row.get("GICS Sector", "")).strip(),
                    industry=str(row.get("GICS Sub-Industry", "")).strip(),
                    raw_data=row.to_dict(),
                )
                entries.append(entry)

            logger.info(f"S&P 500: {len(entries)} securities")
            return entries

        except Exception as e:
            logger.error(f"Failed to fetch S&P 500: {e}")
            return []


class IndiaUniverseAdapter(UniverseAdapter):
    """Adapter for Indian market data (NSE)"""

    def get_exchange_codes(self) -> list[str]:
        return ["NSE"]

    def fetch_universe(self) -> list[UniverseEntry]:
        """Fetch NSE universe from EQUITY_L.csv"""
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        data = self._make_request(url)
        if not data:
            return []

        entries = []
        lines = data.strip().split("\n")

        # Skip header
        for line in lines[1:]:
            if not line.strip():
                continue

            # Parse CSV line (NSE uses | as delimiter sometimes)
            if "|" in line:
                parts = line.split("|")
            else:
                parts = next(csv.reader([line]))

            if len(parts) < 6:
                continue

            symbol = parts[0].strip()
            name = parts[1].strip()
            series = parts[2].strip()
            date_of_listing = parts[3].strip()
            paid_up_value = parts[4].strip()
            market_lot = parts[5].strip()

            if not symbol or series != "EQ":  # Only equity series
                continue

            entry = UniverseEntry(
                symbol=symbol,
                name=name,
                exchange_code="NSE",
                is_active=True,
                raw_data={
                    "series": series,
                    "date_of_listing": date_of_listing,
                    "paid_up_value": paid_up_value,
                    "market_lot": market_lot,
                },
            )
            entries.append(entry)

        logger.info(f"NSE: {len(entries)} securities")
        return entries
