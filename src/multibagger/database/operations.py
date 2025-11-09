"""Database operations and utilities for Multi-Bagger Research System"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from .migrations import MigrationManager, create_initial_migration
from .models import Exchange, Run, Sector
from .schema import get_engine, get_session

logger = logging.getLogger(__name__)


class DatabaseManager:
    """High-level database operations"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self.engine = get_engine(db_path)
        self.migration_manager = MigrationManager()

    def initialize(self) -> dict[str, any]:
        """Initialize database with schema and initial data"""
        result = {
            "database_created": False,
            "migrations_applied": 0,
            "initial_data_loaded": False,
            "schema_version": None,
            "database_path": str(self.engine.url.database),
        }

        try:
            # Check if database exists
            db_exists = Path(self.engine.url.database).exists()
            if not db_exists:
                result["database_created"] = True
                logger.info("Creating new database")

            # Create initial migration if none exist
            if not list(self.migration_manager.migrations_dir.glob("*.sql")):
                create_initial_migration()
                logger.info("Created initial migration file")

            # Run migrations
            applied_count = self.migration_manager.run_migrations(self.engine)
            result["migrations_applied"] = applied_count

            # Load initial reference data if new database
            if applied_count > 0:
                self._load_initial_data()
                result["initial_data_loaded"] = True

            # Get current schema version
            result["schema_version"] = self.migration_manager.get_current_version(
                self.engine
            )

            logger.info(f"Database initialization complete: {result}")
            return result

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def verify_schema(self) -> dict[str, any]:
        """Verify database schema integrity"""
        result = {
            "tables_exist": True,
            "indexes_exist": True,
            "constraints_valid": True,
            "test_operations": True,
            "issues": [],
        }

        try:
            session = get_session(self.engine)

            # Test basic table operations
            expected_tables = [
                "schema_versions",
                "exchanges",
                "sectors",
                "tickers",
                "prices",
                "fundamentals",
                "factors",
                "http_cache",
                "runs",
                "decisions",
            ]

            for table in expected_tables:
                try:
                    session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                except Exception as e:
                    result["tables_exist"] = False
                    result["issues"].append(f"Table {table} not accessible: {e}")

            # Test write operations
            try:
                # Create a test run record
                test_run = Run(
                    run_id="test_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
                    month_year=datetime.now().strftime("%Y-%m"),
                    stage="verification",
                    status="completed",
                )
                session.add(test_run)
                session.commit()

                # Clean up test record
                session.delete(test_run)
                session.commit()

            except Exception as e:
                result["test_operations"] = False
                result["issues"].append(f"Write test failed: {e}")

            session.close()

            # Check indexes exist
            inspector_result = self._check_indexes()
            if inspector_result["missing_indexes"]:
                result["indexes_exist"] = False
                result["issues"].extend(
                    [
                        f"Missing index: {idx}"
                        for idx in inspector_result["missing_indexes"]
                    ]
                )

            logger.info(f"Schema verification result: {result}")
            return result

        except Exception as e:
            result["tables_exist"] = False
            result["issues"].append(f"Verification failed: {e}")
            logger.error(f"Schema verification error: {e}")
            return result

    def create_snapshot(self, snapshot_dir: str | None = None) -> dict[str, any]:
        """Create a monthly snapshot of the database"""
        if not snapshot_dir:
            timestamp = datetime.now().strftime("%Y-%m")
            snapshot_dir = f"snapshots/{timestamp}"

        snapshot_path = Path(snapshot_dir)
        snapshot_path.mkdir(parents=True, exist_ok=True)

        result = {
            "snapshot_created": False,
            "snapshot_path": str(snapshot_path.absolute()),
            "database_copied": False,
            "run_recorded": False,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Copy database file
            db_source = Path(self.engine.url.database)
            db_target = snapshot_path / "multibagger.db"

            if db_source.exists():
                shutil.copy2(db_source, db_target)
                result["database_copied"] = True
                logger.info(f"Database copied to {db_target}")

            # Record snapshot in runs table
            session = get_session(self.engine)
            try:
                snapshot_run = Run(
                    run_id=f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    month_year=datetime.now().strftime("%Y-%m"),
                    stage="snapshot",
                    status="completed",
                    parameters=json.dumps({"snapshot_path": str(snapshot_path)}),
                )
                session.add(snapshot_run)
                session.commit()
                result["run_recorded"] = True

            finally:
                session.close()

            result["snapshot_created"] = True
            logger.info(f"Snapshot created: {result}")
            return result

        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            raise

    def get_schema_info(self) -> dict[str, any]:
        """Get detailed schema information"""
        info = {
            "database_path": str(self.engine.url.database),
            "database_exists": Path(self.engine.url.database).exists(),
            "schema_version": None,
            "table_counts": {},
            "indexes": [],
            "applied_migrations": [],
        }

        try:
            # Get schema version
            info["schema_version"] = self.migration_manager.get_current_version(
                self.engine
            )

            # Get applied migrations
            info["applied_migrations"] = self.migration_manager.get_applied_versions(
                self.engine
            )

            # Get table counts
            session = get_session(self.engine)
            try:
                table_names = [
                    "exchanges",
                    "sectors",
                    "tickers",
                    "prices",
                    "fundamentals",
                    "factors",
                    "http_cache",
                    "runs",
                    "decisions",
                ]

                for table in table_names:
                    try:
                        result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar()
                        info["table_counts"][table] = count
                    except Exception:
                        info["table_counts"][table] = "ERROR"

            finally:
                session.close()

            # Get index information
            info["indexes"] = self._get_index_list()

            return info

        except Exception as e:
            logger.error(f"Failed to get schema info: {e}")
            info["error"] = str(e)
            return info

    def _load_initial_data(self) -> None:
        """Load initial reference data"""
        session = get_session(self.engine)
        try:
            # Load exchanges
            exchanges_data = [
                {
                    "code": "NYSE",
                    "name": "New York Stock Exchange",
                    "country": "USA",
                    "timezone": "America/New_York",
                },
                {
                    "code": "NASDAQ",
                    "name": "NASDAQ",
                    "country": "USA",
                    "timezone": "America/New_York",
                },
                {
                    "code": "NSE",
                    "name": "National Stock Exchange of India",
                    "country": "IND",
                    "timezone": "Asia/Kolkata",
                },
                {
                    "code": "BSE",
                    "name": "Bombay Stock Exchange",
                    "country": "IND",
                    "timezone": "Asia/Kolkata",
                },
            ]

            for exchange_data in exchanges_data:
                if (
                    not session.query(Exchange)
                    .filter_by(code=exchange_data["code"])
                    .first()
                ):
                    exchange = Exchange(**exchange_data)
                    session.add(exchange)

            # Load sectors
            sectors_data = [
                {"name": "Technology", "level": 1},
                {"name": "Healthcare", "level": 1},
                {"name": "Financial Services", "level": 1},
                {"name": "Consumer Goods", "level": 1},
                {"name": "Energy", "level": 1},
                {"name": "Materials", "level": 1},
                {"name": "Industrials", "level": 1},
                {"name": "Utilities", "level": 1},
                {"name": "Real Estate", "level": 1},
                {"name": "Communication Services", "level": 1},
            ]

            for sector_data in sectors_data:
                if (
                    not session.query(Sector)
                    .filter_by(name=sector_data["name"])
                    .first()
                ):
                    sector = Sector(**sector_data)
                    session.add(sector)

            session.commit()
            logger.info("Initial reference data loaded")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to load initial data: {e}")
            raise
        finally:
            session.close()

    def _check_indexes(self) -> dict[str, list[str]]:
        """Check if required indexes exist"""
        required_indexes = [
            "ix_ticker_symbol_exchange",
            "ix_ticker_active",
            "ix_price_ticker_date",
            "ix_fundamental_ticker_period",
            "ix_factor_ticker_date",
            "ix_factor_overall_score",
            "ix_cache_key",
            "ix_run_month_year",
            "ix_decision_run_ticker",
        ]

        existing_indexes = self._get_index_list()
        missing_indexes = [
            idx for idx in required_indexes if idx not in existing_indexes
        ]

        return {
            "existing_indexes": existing_indexes,
            "missing_indexes": missing_indexes,
            "required_indexes": required_indexes,
        }

    def _get_index_list(self) -> list[str]:
        """Get list of existing indexes"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
                    )
                )
                return [row[0] for row in result]
        except Exception:
            return []


def initialize_database(db_path: str | None = None) -> dict[str, any]:
    """Convenience function to initialize database"""
    manager = DatabaseManager(db_path)
    return manager.initialize()


def verify_database(db_path: str | None = None) -> dict[str, any]:
    """Convenience function to verify database"""
    manager = DatabaseManager(db_path)
    return manager.verify_schema()


def create_database_snapshot(
    snapshot_dir: str | None = None, db_path: str | None = None
) -> dict[str, any]:
    """Convenience function to create database snapshot"""
    manager = DatabaseManager(db_path)
    return manager.create_snapshot(snapshot_dir)


def get_database_info(db_path: str | None = None) -> dict[str, any]:
    """Convenience function to get database information"""
    manager = DatabaseManager(db_path)
    return manager.get_schema_info()
