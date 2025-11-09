"""Database migration system for Multi-Bagger Research System

Simple, file-based migration system suitable for SQLite with timestamped
migration files and idempotent application.
"""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import SchemaVersion
from .schema import get_engine, get_session

logger = logging.getLogger(__name__)


class Migration:
    """Represents a single database migration"""

    def __init__(self, version: str, description: str, up_sql: str, down_sql: str = ""):
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql

    def apply(self, engine: Engine) -> None:
        """Apply migration to database"""
        with engine.connect() as conn:
            # Execute SQL statements
            for statement in self.up_sql.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()

    def rollback(self, engine: Engine) -> None:
        """Rollback migration (dev only)"""
        if not self.down_sql:
            raise ValueError(f"Migration {self.version} has no rollback SQL")

        with engine.connect() as conn:
            for statement in self.down_sql.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()


class MigrationManager:
    """Manages database migrations"""

    def __init__(self, migrations_dir: str = "database/migrations"):
        self.migrations_dir = Path(migrations_dir)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

    def get_current_version(self, engine: Engine) -> str | None:
        """Get current schema version from database"""
        try:
            session = get_session(engine)
            try:
                latest = (
                    session.query(SchemaVersion)
                    .order_by(SchemaVersion.applied_at.desc())
                    .first()
                )
                return latest.version if latest else None
            finally:
                session.close()
        except Exception:
            # Table doesn't exist yet
            return None

    def get_applied_versions(self, engine: Engine) -> list[str]:
        """Get list of applied migration versions"""
        try:
            session = get_session(engine)
            try:
                versions = session.query(SchemaVersion.version).all()
                return [v[0] for v in versions]
            finally:
                session.close()
        except Exception:
            return []

    def load_migrations(self) -> dict[str, Migration]:
        """Load all migration files"""
        migrations = {}

        # Look for migration files in format: YYYYMMDD_HHMMSS_description.sql
        for migration_file in sorted(self.migrations_dir.glob("*.sql")):
            try:
                version = migration_file.stem
                content = migration_file.read_text()

                # Parse migration file
                # Format: -- Description: Migration description
                #         -- Up:
                #         CREATE TABLE ...;
                #         -- Down:
                #         DROP TABLE ...;

                lines = content.strip().split("\n")
                description = ""
                up_sql = ""
                down_sql = ""
                current_section = None

                for line in lines:
                    line = line.strip()
                    if line.startswith("-- Description:"):
                        description = line.replace("-- Description:", "").strip()
                    elif line.startswith("-- Up:"):
                        current_section = "up"
                    elif line.startswith("-- Down:"):
                        current_section = "down"
                    elif line.startswith("--") or not line:
                        continue
                    elif current_section == "up":
                        up_sql += line + "\n"
                    elif current_section == "down":
                        down_sql += line + "\n"

                migrations[version] = Migration(
                    version, description, up_sql.strip(), down_sql.strip()
                )

            except Exception as e:
                logger.warning(f"Failed to load migration {migration_file}: {e}")

        return migrations

    def get_pending_migrations(self, engine: Engine) -> list[Migration]:
        """Get migrations that haven't been applied yet"""
        applied_versions = set(self.get_applied_versions(engine))
        all_migrations = self.load_migrations()

        pending = []
        for version in sorted(all_migrations.keys()):
            if version not in applied_versions:
                pending.append(all_migrations[version])

        return pending

    def apply_migration(self, engine: Engine, migration: Migration) -> None:
        """Apply a single migration"""
        logger.info(f"Applying migration {migration.version}: {migration.description}")

        # Apply the migration
        migration.apply(engine)

        # Record it as applied
        session = get_session(engine)
        try:
            version_record = SchemaVersion(
                version=migration.version,
                description=migration.description,
                applied_at=datetime.utcnow(),
            )
            session.add(version_record)
            session.commit()
            logger.info(f"Migration {migration.version} applied successfully")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def run_migrations(self, engine: Engine, target_version: str | None = None) -> int:
        """Run all pending migrations up to target version"""
        # Ensure schema_versions table exists
        self._ensure_schema_versions_table(engine)

        pending = self.get_pending_migrations(engine)

        if target_version:
            # Filter to only migrations up to target
            pending = [m for m in pending if m.version <= target_version]

        applied_count = 0
        for migration in pending:
            try:
                self.apply_migration(engine, migration)
                applied_count += 1
            except Exception as e:
                logger.error(f"Failed to apply migration {migration.version}: {e}")
                raise

        if applied_count == 0:
            logger.info("No pending migrations to apply")
        else:
            logger.info(f"Applied {applied_count} migrations successfully")

        return applied_count

    def _ensure_schema_versions_table(self, engine: Engine) -> None:
        """Ensure the schema_versions table exists"""
        create_sql = """
        CREATE TABLE IF NOT EXISTS schema_versions (
            version VARCHAR(50) PRIMARY KEY,
            applied_at DATETIME NOT NULL,
            description VARCHAR(255)
        )
        """

        with engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()

    def create_migration(
        self, description: str, up_sql: str, down_sql: str = ""
    ) -> str:
        """Create a new migration file"""
        # Generate timestamped version
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_description = "".join(
            c if c.isalnum() else "_" for c in description.lower()
        )
        version = f"{timestamp}_{safe_description}"

        # Create migration file content
        content = f"""-- Description: {description}
-- Up:
{up_sql}

-- Down:
{down_sql}
"""

        # Write to file
        migration_file = self.migrations_dir / f"{version}.sql"
        migration_file.write_text(content)

        logger.info(f"Created migration: {migration_file}")
        return version


def run_migrations(
    db_path: str | None = None, target_version: str | None = None
) -> int:
    """Convenience function to run migrations"""
    engine = get_engine(db_path)
    manager = MigrationManager()
    return manager.run_migrations(engine, target_version)


def create_initial_migration() -> None:
    """Create the initial migration with all tables"""
    manager = MigrationManager()

    up_sql = """
-- Create exchanges table
CREATE TABLE exchanges (
    id INTEGER PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(3) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create sectors table
CREATE TABLE sectors (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INTEGER REFERENCES sectors(id),
    level INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create tickers table
CREATE TABLE tickers (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    name VARCHAR(200) NOT NULL,
    sector_id INTEGER REFERENCES sectors(id),
    market_cap DECIMAL(15,2),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    isin VARCHAR(12),
    cusip VARCHAR(9),
    active BOOLEAN NOT NULL DEFAULT 1,
    delisted_date DATE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create prices table
CREATE TABLE prices (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4) NOT NULL,
    adj_close DECIMAL(12,4) NOT NULL,
    volume INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create fundamentals table
CREATE TABLE fundamentals (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    period_end DATE NOT NULL,
    report_type VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER,
    revenue DECIMAL(15,2),
    gross_profit DECIMAL(15,2),
    operating_income DECIMAL(15,2),
    ebit DECIMAL(15,2),
    ebitda DECIMAL(15,2),
    net_income DECIMAL(15,2),
    total_assets DECIMAL(15,2),
    current_assets DECIMAL(15,2),
    non_current_assets DECIMAL(15,2),
    total_liabilities DECIMAL(15,2),
    current_liabilities DECIMAL(15,2),
    long_term_debt DECIMAL(15,2),
    shareholders_equity DECIMAL(15,2),
    operating_cash_flow DECIMAL(15,2),
    investing_cash_flow DECIMAL(15,2),
    financing_cash_flow DECIMAL(15,2),
    free_cash_flow DECIMAL(15,2),
    shares_outstanding DECIMAL(12,2),
    book_value_per_share DECIMAL(8,4),
    earnings_per_share DECIMAL(8,4),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    filed_date DATE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create factors table
CREATE TABLE factors (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    as_of_date DATE NOT NULL,
    roe DECIMAL(8,4),
    roa DECIMAL(8,4),
    roce DECIMAL(8,4),
    roic DECIMAL(8,4),
    gross_margin DECIMAL(8,4),
    operating_margin DECIMAL(8,4),
    net_margin DECIMAL(8,4),
    revenue_growth_1y DECIMAL(8,4),
    revenue_growth_3y DECIMAL(8,4),
    revenue_growth_5y DECIMAL(8,4),
    earnings_growth_1y DECIMAL(8,4),
    earnings_growth_3y DECIMAL(8,4),
    earnings_growth_5y DECIMAL(8,4),
    debt_to_equity DECIMAL(8,4),
    current_ratio DECIMAL(8,4),
    interest_coverage DECIMAL(8,4),
    piotroski_score INTEGER,
    altman_z_score DECIMAL(8,4),
    pe_ratio DECIMAL(8,4),
    pb_ratio DECIMAL(8,4),
    ps_ratio DECIMAL(8,4),
    peg_ratio DECIMAL(8,4),
    ev_ebitda DECIMAL(8,4),
    fcf_yield DECIMAL(8,4),
    beta DECIMAL(8,4),
    volatility_1y DECIMAL(8,4),
    max_drawdown_1y DECIMAL(8,4),
    beneish_m_score DECIMAL(8,4),
    days_sales_outstanding DECIMAL(8,4),
    asset_quality_index DECIMAL(8,4),
    quality_score DECIMAL(8,4),
    growth_score DECIMAL(8,4),
    value_score DECIMAL(8,4),
    momentum_score DECIMAL(8,4),
    overall_score DECIMAL(8,4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create http_cache table
CREATE TABLE http_cache (
    id INTEGER PRIMARY KEY,
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    url TEXT NOT NULL,
    response_data TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    content_type VARCHAR(100),
    ttl_days INTEGER NOT NULL DEFAULT 1,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create runs table
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL UNIQUE,
    month_year VARCHAR(7) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    input_count INTEGER,
    output_count INTEGER,
    duration_seconds INTEGER,
    parameters TEXT,
    error_message TEXT
);

-- Create decisions table
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    stage VARCHAR(50) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    reason VARCHAR(500),
    score DECIMAL(8,4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE UNIQUE INDEX ix_ticker_symbol_exchange ON tickers(symbol, exchange_id);
CREATE INDEX ix_ticker_active ON tickers(active);
CREATE INDEX ix_ticker_market_cap ON tickers(market_cap);
CREATE UNIQUE INDEX ix_price_ticker_date ON prices(ticker_id, date);
CREATE INDEX ix_price_date ON prices(date);
CREATE UNIQUE INDEX ix_fundamental_ticker_period ON fundamentals(ticker_id, period_end);
CREATE INDEX ix_fundamental_period ON fundamentals(period_end);
CREATE INDEX ix_fundamental_fiscal_year ON fundamentals(fiscal_year);
CREATE UNIQUE INDEX ix_factor_ticker_date ON factors(ticker_id, as_of_date);
CREATE INDEX ix_factor_date ON factors(as_of_date);
CREATE INDEX ix_factor_overall_score ON factors(overall_score);
CREATE INDEX ix_factor_quality_score ON factors(quality_score);
CREATE INDEX ix_cache_key ON http_cache(cache_key);
CREATE INDEX ix_cache_expires ON http_cache(expires_at);
CREATE INDEX ix_run_month_year ON runs(month_year);
CREATE INDEX ix_run_started_at ON runs(started_at);
CREATE INDEX ix_run_status ON runs(status);
CREATE INDEX ix_decision_run_ticker ON decisions(run_id, ticker_id);
CREATE INDEX ix_decision_stage ON decisions(stage);
CREATE INDEX ix_decision_decision ON decisions(decision);
"""

    down_sql = """
DROP TABLE IF EXISTS decisions;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS http_cache;
DROP TABLE IF EXISTS factors;
DROP TABLE IF EXISTS fundamentals;
DROP TABLE IF EXISTS prices;
DROP TABLE IF EXISTS tickers;
DROP TABLE IF EXISTS sectors;
DROP TABLE IF EXISTS exchanges;
"""

    manager.create_migration("initial_schema", up_sql, down_sql)
    logger.info("Created initial migration file")
