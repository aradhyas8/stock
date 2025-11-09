"""Main universe builder that orchestrates the entire universe building process"""

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.data.cache import HttpCache
from multibagger.database.models import Exchange, Sector, Ticker
from multibagger.database.schema import get_engine, get_session

from .adapters import IndiaUniverseAdapter, UniverseEntry, USUniverseAdapter
from .eligibility import EligibilityChecker
from .normalizer import SymbolNormalizer

logger = logging.getLogger(__name__)


class UniverseBuilder:
    """Builds and maintains the stock universe"""

    def __init__(self, config: Config, cache: HttpCache):
        self.config = config
        self.cache = cache
        self.normalizer = SymbolNormalizer()
        self.eligibility_checker = EligibilityChecker(config)
        self.engine = get_engine()

        # Initialize adapters based on enabled markets
        self.adapters = self._init_adapters()

    def _init_adapters(self) -> list:
        """Initialize data adapters for enabled markets"""
        adapters = []

        if "US" in self.config.markets:
            adapters.append(USUniverseAdapter(self.config, self.cache))

        if "INDIA" in self.config.markets:
            adapters.append(IndiaUniverseAdapter(self.config, self.cache))

        return adapters

    def build_universe(self, force_refresh: bool = False) -> dict[str, any]:
        """Build complete stock universe from all sources"""
        logger.info("Starting universe build process")

        all_entries = []
        stats = {
            "sources": {},
            "total_raw_entries": 0,
            "normalized_entries": 0,
            "eligible_entries": 0,
            "final_universe_size": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Fetch data from all adapters
        for adapter in self.adapters:
            source_name = adapter.__class__.__name__
            logger.info(f"Fetching data from {source_name}")

            try:
                entries = adapter.fetch_universe()
                stats["sources"][source_name] = len(entries)
                stats["total_raw_entries"] += len(entries)
                all_entries.extend(entries)
                logger.info(f"{source_name}: {len(entries)} entries")
            except Exception as e:
                logger.error(f"Failed to fetch from {source_name}: {e}")
                stats["sources"][source_name] = 0

        # Normalize symbols
        logger.info("Normalizing symbols")
        normalized_entries = []
        for entry in all_entries:
            normalized = self.normalizer.normalize_universe_entry(entry)
            if normalized.symbol:  # Skip empty symbols
                normalized_entries.append(normalized)

        stats["normalized_entries"] = len(normalized_entries)

        # Remove duplicates
        deduplicated_entries = self._deduplicate_entries(normalized_entries)
        logger.info(
            f"Deduplication: {len(normalized_entries)} -> {len(deduplicated_entries)}"
        )

        # Apply eligibility filters
        eligible_entries = self.eligibility_checker.filter_eligible(
            deduplicated_entries
        )
        stats["eligible_entries"] = len(eligible_entries)

        # Persist to database
        final_count = self._persist_universe(eligible_entries)
        stats["final_universe_size"] = final_count

        logger.info(f"Universe build complete: {final_count} securities")
        return stats

    def _deduplicate_entries(self, entries: list[UniverseEntry]) -> list[UniverseEntry]:
        """Remove duplicate entries by (symbol, exchange)"""
        seen_keys = set()
        unique_entries = []

        for entry in entries:
            key = (entry.symbol, entry.exchange_code)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_entries.append(entry)

        return unique_entries

    def _persist_universe(self, entries: list[UniverseEntry]) -> int:
        """Persist universe to database with upsert operations"""
        with get_session(self.engine) as session:
            # Ensure exchanges exist
            self._ensure_exchanges(session, entries)

            # Ensure sectors exist (if provided)
            self._ensure_sectors(session, entries)

            # Upsert tickers
            count = self._upsert_tickers(session, entries)

            # Commit all changes
            session.commit()

            return count

    def _ensure_exchanges(self, session: Session, entries: list[UniverseEntry]):
        """Ensure all required exchanges exist in database"""
        exchange_codes = {entry.exchange_code for entry in entries}

        # Exchange metadata
        exchange_data = {
            "NYSE": {
                "name": "New York Stock Exchange",
                "country": "USA",
                "timezone": "America/New_York",
            },
            "NASDAQ": {
                "name": "NASDAQ Stock Market",
                "country": "USA",
                "timezone": "America/New_York",
            },
            "NSE": {
                "name": "National Stock Exchange of India",
                "country": "IND",
                "timezone": "Asia/Kolkata",
            },
        }

        for code in exchange_codes:
            existing = session.query(Exchange).filter_by(code=code).first()
            if not existing:
                data = exchange_data.get(
                    code,
                    {"name": f"{code} Exchange", "country": "UNK", "timezone": "UTC"},
                )

                exchange = Exchange(
                    code=code,
                    name=data["name"],
                    country=data["country"],
                    timezone=data["timezone"],
                )
                session.add(exchange)
                logger.debug(f"Created exchange: {code}")

    def _ensure_sectors(self, session: Session, entries: list[UniverseEntry]):
        """Ensure all required sectors exist in database"""
        sectors_seen = set()

        for entry in entries:
            if entry.sector:
                sectors_seen.add(entry.sector)
            if entry.industry:
                sectors_seen.add(entry.industry)

        for sector_name in sectors_seen:
            existing = session.query(Sector).filter_by(name=sector_name).first()
            if not existing:
                sector = Sector(
                    name=sector_name,
                    level=(
                        1
                        if not any(entry.industry == sector_name for entry in entries)
                        else 2
                    ),
                )
                session.add(sector)
                logger.debug(f"Created sector: {sector_name}")

    def _upsert_tickers(self, session: Session, entries: list[UniverseEntry]) -> int:
        """Upsert ticker records"""
        count = 0

        for entry in entries:
            # Get exchange
            exchange = (
                session.query(Exchange).filter_by(code=entry.exchange_code).first()
            )
            if not exchange:
                logger.error(f"Exchange not found: {entry.exchange_code}")
                continue

            # Get sector if provided
            sector = None
            if entry.sector:
                sector = session.query(Sector).filter_by(name=entry.sector).first()

            # Check if ticker exists
            existing = (
                session.query(Ticker)
                .filter_by(symbol=entry.symbol, exchange_id=exchange.id)
                .first()
            )

            if existing:
                # Update existing
                existing.name = entry.name
                if sector:
                    existing.sector_id = sector.id
                if entry.market_cap:
                    existing.market_cap = entry.market_cap
                existing.active = entry.is_active
                existing.updated_at = datetime.utcnow()
            else:
                # Create new
                ticker = Ticker(
                    symbol=entry.symbol,
                    exchange_id=exchange.id,
                    name=entry.name,
                    sector_id=sector.id if sector else None,
                    market_cap=entry.market_cap,
                    active=entry.is_active,
                )
                session.add(ticker)

            count += 1

        return count

    def save_snapshot(self, snapshot_dir: str, stats: dict) -> Path:
        """Save universe snapshot to files"""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        snapshot_path = Path(snapshot_dir) / f"universe_{timestamp}"
        snapshot_path.mkdir(parents=True, exist_ok=True)

        # Get current universe from database
        universe_data = self._get_universe_data()

        # Save JSON
        json_file = snapshot_path / "universe.json"
        with open(json_file, "w") as f:
            json.dump(
                {
                    "metadata": {"timestamp": timestamp, "stats": stats},
                    "universe": universe_data,
                },
                f,
                indent=2,
                default=str,
            )

        # Save CSV
        csv_file = snapshot_path / "universe.csv"
        if universe_data:
            import csv

            with open(csv_file, "w", newline="") as f:
                if universe_data:
                    writer = csv.DictWriter(f, fieldnames=universe_data[0].keys())
                    writer.writeheader()
                    writer.writerows(universe_data)

        # Save stats separately
        stats_file = snapshot_path / "build_stats.json"
        with open(stats_file, "w") as f:
            json.dump(stats, f, indent=2, default=str)

        logger.info(f"Snapshot saved to: {snapshot_path}")
        return snapshot_path

    def _get_universe_data(self) -> list[dict]:
        """Get current universe data from database"""
        with get_session(self.engine) as session:
            tickers = session.query(Ticker).filter_by(active=True).all()

            universe = []
            for ticker in tickers:
                universe.append(
                    {
                        "symbol": ticker.symbol,
                        "name": ticker.name,
                        "exchange": ticker.exchange.code,
                        "sector": ticker.sector.name if ticker.sector else None,
                        "market_cap": ticker.market_cap,
                        "currency": ticker.currency,
                        "isin": ticker.isin,
                        "active": ticker.active,
                        "created_at": ticker.created_at,
                        "updated_at": ticker.updated_at,
                    }
                )

            return universe

    def verify_universe(self) -> dict[str, any]:
        """Verify universe integrity and statistics"""
        with get_session(self.engine) as session:
            # Basic counts
            total_tickers = session.query(Ticker).count()
            active_tickers = session.query(Ticker).filter_by(active=True).count()
            exchanges = session.query(Exchange).count()
            sectors = session.query(Sector).count()

            # Exchange breakdown
            exchange_counts = {}
            for exchange in session.query(Exchange).all():
                count = session.query(Ticker).filter_by(exchange_id=exchange.id).count()
                exchange_counts[exchange.code] = count

            # Symbol validation
            invalid_symbols = []
            for ticker in session.query(Ticker).filter_by(active=True):
                if not self.normalizer._is_valid_symbol(ticker.symbol):
                    invalid_symbols.append(ticker.symbol)

            return {
                "total_tickers": total_tickers,
                "active_tickers": active_tickers,
                "exchanges": exchanges,
                "sectors": sectors,
                "exchange_breakdown": exchange_counts,
                "invalid_symbols": invalid_symbols,
                "is_valid": len(invalid_symbols) == 0,
            }

    def get_universe_info(self) -> dict[str, any]:
        """Get summary information about the universe"""
        verification = self.verify_universe()

        return {
            "verification": verification,
            "config": {
                "markets": self.config.markets,
                "min_market_cap": self.config.universe.get("min_market_cap"),
                "min_price": self.config.universe.get("min_price"),
                "exclude_otc": self.config.universe.get("exclude_otc"),
                "exclude_adrs": self.config.universe.get("exclude_adrs"),
            },
            "last_updated": datetime.utcnow().isoformat(),
        }
