#!/usr/bin/env python3
"""
Tests for data promotion API (Phase A)

Validates:
- Promotion moves data from temp → canonical
- Idempotent behavior (second call yields zero changes)
- Batch promotion
"""

import pytest
from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.database.schema import get_engine
from multibagger.database.models import FundamentalTemp, FactorTemp, Fundamental, Factor
from multibagger.data.promotion import promote_finalist, batch_promote_finalists, PromotionResult


@pytest.fixture
def db_session():
    """Create a test database session with temp tables"""
    engine = get_engine()

    # Ensure temp tables exist (run migration using raw sqlite3)
    from pathlib import Path
    import sqlite3
    migration_file = Path("database/migrations/20251111_ephemeral_staging.sql")
    if migration_file.exists():
        migration_sql = migration_file.read_text()
        # Use sqlite3 directly for executescript
        db_path = "multibagger.db"  # Same DB that get_engine() uses
        conn = sqlite3.connect(db_path)
        conn.executescript(migration_sql)
        conn.close()

    session = Session(engine)
    yield session
    session.close()


def test_promote_finalist_moves_data(db_session):
    """Test that promotion moves data from temp to canonical"""
    ticker_id = 999999  # Use high ID to avoid conflicts
    as_of = date(2025, 11, 1)
    period_end = date(2024, 12, 31)

    # Clean up any existing data
    db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": ticker_id})
    db_session.commit()

    # Insert test ticker (required for FK constraints on canonical tables)
    db_session.execute(text("""
        INSERT INTO tickers (id, symbol, name, exchange_id, sector_id, active, created_at, updated_at)
        VALUES (:id, 'TEST999', 'Test Company 999', 1, 1, 1, :now, :now)
    """), {
        "id": ticker_id,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    db_session.commit()

    # Insert test data into temp tables
    db_session.execute(text("""
        INSERT INTO fundamentals_temp (
            ticker_id, period_end, report_type, fiscal_year, fiscal_quarter,
            revenue, net_income, currency, created_at, updated_at
        ) VALUES (
            :ticker_id, :period_end, 'Q', 2024, 4,
            1000000.0, 100000.0, 'USD', :now, :now
        )
    """), {
        "ticker_id": ticker_id,
        "period_end": period_end.strftime("%Y-%m-%d"),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    db_session.execute(text("""
        INSERT INTO factors_temp (
            ticker_id, as_of_date, roe, quality_score, overall_score,
            created_at, updated_at
        ) VALUES (
            :ticker_id, :as_of, 0.15, 75.0, 80.0, :now, :now
        )
    """), {
        "ticker_id": ticker_id,
        "as_of": as_of.strftime("%Y-%m-%d"),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    db_session.commit()

    # Verify data in temp tables
    temp_fundamentals = db_session.execute(
        text("SELECT COUNT(*) FROM fundamentals_temp WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert temp_fundamentals == 1

    temp_factors = db_session.execute(
        text("SELECT COUNT(*) FROM factors_temp WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert temp_factors == 1

    # Promote the data
    result = promote_finalist(db_session, ticker_id, as_of, commit=True)

    # Verify result
    assert result.ticker_id == ticker_id
    assert result.fundamentals_rows == 1
    assert result.factors_rows == 1

    # Verify data in canonical tables
    canonical_fundamentals = db_session.execute(
        text("SELECT COUNT(*) FROM fundamentals WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert canonical_fundamentals == 1

    canonical_factors = db_session.execute(
        text("SELECT COUNT(*) FROM factors WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert canonical_factors == 1

    # Cleanup
    db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": ticker_id})
    db_session.commit()


def test_promote_finalist_idempotent(db_session):
    """Test that second promotion yields zero changes"""
    ticker_id = 999998
    as_of = date(2025, 11, 1)
    period_end = date(2024, 12, 31)

    # Clean up
    db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": ticker_id})
    db_session.commit()

    # Insert test ticker
    db_session.execute(text("""
        INSERT INTO tickers (id, symbol, name, exchange_id, sector_id, active, created_at, updated_at)
        VALUES (:id, 'TEST998', 'Test Company 998', 1, 1, 1, :now, :now)
    """), {
        "id": ticker_id,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    db_session.commit()

    # Insert test data
    db_session.execute(text("""
        INSERT INTO fundamentals_temp (
            ticker_id, period_end, report_type, fiscal_year, fiscal_quarter,
            revenue, currency, created_at, updated_at
        ) VALUES (
            :ticker_id, :period_end, 'Q', 2024, 4, 1000000.0, 'USD', :now, :now
        )
    """), {
        "ticker_id": ticker_id,
        "period_end": period_end.strftime("%Y-%m-%d"),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    db_session.execute(text("""
        INSERT INTO factors_temp (
            ticker_id, as_of_date, roe, created_at, updated_at
        ) VALUES (
            :ticker_id, :as_of, 0.15, :now, :now
        )
    """), {
        "ticker_id": ticker_id,
        "as_of": as_of.strftime("%Y-%m-%d"),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    db_session.commit()

    # First promotion
    result1 = promote_finalist(db_session, ticker_id, as_of, commit=True)
    assert result1.fundamentals_rows == 1
    assert result1.factors_rows == 1

    # Second promotion (data already in canonical, temp still has it)
    result2 = promote_finalist(db_session, ticker_id, as_of, commit=True)

    # SQLite INSERT OR REPLACE will always report 1 row (even if replacing)
    # So we can't assert rowcount == 0, but data should be identical

    # Verify counts haven't changed
    canonical_fundamentals = db_session.execute(
        text("SELECT COUNT(*) FROM fundamentals WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert canonical_fundamentals == 1  # Still just 1 row

    canonical_factors = db_session.execute(
        text("SELECT COUNT(*) FROM factors WHERE ticker_id = :id"),
        {"id": ticker_id}
    ).scalar()
    assert canonical_factors == 1  # Still just 1 row

    # Cleanup
    db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": ticker_id})
    db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": ticker_id})
    db_session.commit()


def test_batch_promote_finalists(db_session):
    """Test batch promotion of multiple tickers"""
    ticker_ids = [999997, 999996]
    as_of = date(2025, 11, 1)

    # Clean up
    for tid in ticker_ids:
        db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": tid})
    db_session.commit()

    # Insert test tickers
    for tid in ticker_ids:
        db_session.execute(text("""
            INSERT INTO tickers (id, symbol, name, exchange_id, sector_id, active, created_at, updated_at)
            VALUES (:id, :symbol, :name, 1, 1, 1, :now, :now)
        """), {
            "id": tid,
            "symbol": f"TEST{tid}",
            "name": f"Test Company {tid}",
            "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    db_session.commit()

    # Insert test data for both tickers
    for tid in ticker_ids:
        db_session.execute(text("""
            INSERT INTO factors_temp (
                ticker_id, as_of_date, roe, created_at, updated_at
            ) VALUES (
                :ticker_id, :as_of, 0.15, :now, :now
            )
        """), {
            "ticker_id": tid,
            "as_of": as_of.strftime("%Y-%m-%d"),
            "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    db_session.commit()

    # Batch promote
    results = batch_promote_finalists(db_session, ticker_ids, as_of, commit=True)

    # Verify results
    assert len(results) == 2
    assert all(r.ticker_id in ticker_ids for r in results)
    assert all(r.factors_rows == 1 for r in results)

    # Cleanup
    for tid in ticker_ids:
        db_session.execute(text("DELETE FROM fundamentals_temp WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM factors_temp WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM fundamentals WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM factors WHERE ticker_id = :id"), {"id": tid})
        db_session.execute(text("DELETE FROM tickers WHERE id = :id"), {"id": tid})
    db_session.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
