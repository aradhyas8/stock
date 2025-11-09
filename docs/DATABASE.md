# Database Architecture & Operations

This document explains the SQLite database design, migration system, and operational procedures for the Multi-Bagger Research System.

## Database Location & Naming

### Default Location
```
data/multibagger.db          # Current working database
```

### Monthly Snapshots
```
snapshots/YYYY-MM/
├── multibagger.db          # Frozen monthly snapshot
├── reports/                # Generated research reports
└── logs/                   # Pipeline execution logs
```

### Snapshot Strategy
- **Current DB**: `data/multibagger.db` - actively updated during pipeline runs
- **Monthly Snapshots**: Frozen copies in `snapshots/YYYY-MM/` for reproducibility
- **Rollforward**: Current DB is the "live" version, snapshots preserve historical state

## Schema Design

### Core Tables

#### Reference Data
- **`exchanges`**: Stock exchanges (NYSE, NASDAQ, NSE, BSE)
- **`sectors`**: Industry classifications with hierarchical structure
- **`tickers`**: Stock reference data with exchange and sector links

#### Market Data
- **`prices`**: Daily OHLCV price data with split/dividend adjustments
- **`fundamentals`**: Quarterly/annual financial statements
- **`factors`**: Precomputed screening metrics (ROE, growth, quality scores)

#### Operational
- **`http_cache`**: API response caching with TTL management
- **`runs`**: Pipeline execution tracking with stage-level statistics
- **`decisions`**: Individual stock pass/fail decisions with reasoning

#### Migration Management
- **`schema_versions`**: Applied migration tracking with timestamps

### Key Indexes

Fast screening requires strategic indexing:

```sql
-- Core screening indexes
CREATE INDEX ix_ticker_active ON tickers(active);
CREATE INDEX ix_factor_overall_score ON factors(overall_score);
CREATE INDEX ix_factor_quality_score ON factors(quality_score);

-- Time-series access
CREATE INDEX ix_price_ticker_date ON prices(ticker_id, date);
CREATE INDEX ix_fundamental_ticker_period ON fundamentals(ticker_id, period_end);

-- Pipeline tracking
CREATE INDEX ix_run_month_year ON runs(month_year);
CREATE INDEX ix_decision_run_ticker ON decisions(run_id, ticker_id);
```

## Migration System

### Migration Files
Stored in `database/migrations/` with naming convention:
```
YYYYMMDD_HHMMSS_description.sql
```

### Migration Format
```sql
-- Description: Add new factor columns
-- Up:
ALTER TABLE factors ADD COLUMN new_metric DECIMAL(8,4);
CREATE INDEX ix_factor_new_metric ON factors(new_metric);

-- Down:
DROP INDEX ix_factor_new_metric;
ALTER TABLE factors DROP COLUMN new_metric;
```

### Migration Commands
```bash
# Apply all pending migrations
multibagger db-init

# Check current schema version
multibagger db-info

# Verify schema integrity
multibagger db-verify
```

## Data Integrity Rules

### Constraints
- **Uniqueness**: (ticker, exchange), (ticker, date), (ticker, period_end)
- **Foreign Keys**: Enforced via SQLite PRAGMA foreign_keys=ON
- **NOT NULL**: Critical fields like ticker symbols, dates, prices
- **Soft Deletes**: Use `active` flags instead of hard deletes for reference data

### Validation Expectations
- Prices must be positive or null
- Currencies follow ISO 3-letter codes (USD, INR)
- Dates in proper format with timezone handling
- Factor scores normalized to reasonable ranges

### Data Quality
```sql
-- Example validation queries
SELECT ticker_id FROM prices WHERE close_price <= 0;
SELECT ticker_id FROM factors WHERE roe > 200 OR roe < -100;
SELECT COUNT(*) FROM fundamentals WHERE currency NOT IN ('USD', 'INR', 'EUR', 'GBP');
```

## Operational Commands

### Initialize New Database
```bash
multibagger db-init
```
Creates database, applies migrations, loads initial reference data.

### Verify Schema
```bash
multibagger db-verify
```
Checks table structure, indexes, constraints, and runs test operations.

### Get Database Info
```bash
multibagger db-info
```
Shows schema version, table counts, index status, migration history.

### Create Monthly Snapshot
```bash
multibagger db-snapshot
```
Copies current database to timestamped snapshot directory.

### Custom Database Path
```bash
multibagger db-init --db-path /custom/path/research.db
```

## SQLite Optimizations

### Pragmas Applied
```sql
PRAGMA journal_mode=WAL;        -- Better concurrency
PRAGMA foreign_keys=ON;         -- Referential integrity
PRAGMA synchronous=NORMAL;      -- Fast reads
PRAGMA cache_size=10000;        -- 10MB cache
PRAGMA temp_store=MEMORY;       -- Memory temp tables
```

### Performance Considerations
- **Read-Heavy Workload**: Optimized for screening queries over 5,000+ stocks
- **Batch Writes**: Use transactions for bulk inserts/updates
- **Precomputed Factors**: Avoid complex calculations during screening
- **Selective Indexes**: Only index columns used in WHERE/ORDER BY clauses

## Backup & Recovery

### Monthly Snapshots
Automatic during pipeline runs:
```bash
multibagger monthly  # Creates snapshot automatically
```

Manual snapshots:
```bash
multibagger db-snapshot --snapshot-dir custom/location
```

### Restore from Snapshot
```bash
# Copy snapshot back to current location
cp snapshots/2025-11/multibagger.db data/multibagger.db

# Verify restore
multibagger db-verify
```

### Cross-Platform Compatibility
SQLite files are binary compatible across Windows/macOS/Linux with identical behavior.

## Troubleshooting

### Common Issues

**Database Locked**
```bash
# Check for stale WAL files
ls -la data/multibagger.db*

# Force checkpoint
sqlite3 data/multibagger.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

**Missing Indexes**
```bash
multibagger db-verify  # Shows missing indexes
multibagger db-init    # Recreates missing indexes
```

**Schema Version Mismatch**
```bash
multibagger db-info    # Check current version
multibagger db-init    # Apply pending migrations
```

**Data Corruption**
```bash
# Check integrity
sqlite3 data/multibagger.db "PRAGMA integrity_check;"

# Restore from snapshot if needed
cp snapshots/2025-11/multibagger.db data/multibagger.db
```

### Development vs Production

**Development (Local)**
- Drop and recreate database allowed
- Migration rollback supported
- Schema changes frequent

**Production (Snapshots)**
- Forward-only migrations
- Snapshot before major changes  
- Conservative schema evolution

## Schema Evolution Guidelines

### Adding Columns
```sql
-- Safe: Add nullable column with default
ALTER TABLE factors ADD COLUMN new_score DECIMAL(8,4) DEFAULT 0.0;
```

### Adding Indexes
```sql
-- Safe: Always safe to add indexes
CREATE INDEX ix_new_column ON table_name(new_column);
```

### Removing Columns
```sql
-- Risky: SQLite doesn't support DROP COLUMN directly
-- Requires table recreation with data migration
```

### Changing Data Types
```sql
-- Risky: Requires careful data migration
-- Plan multi-step migration with validation
```

This database architecture provides a solid foundation for the multi-bagger research pipeline with reproducible monthly snapshots and fast screening capabilities.
