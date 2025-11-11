"""Tests for daily portfolio monitoring"""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.models import PortfolioRun, PortfolioPosition
from multibagger.database.schema import get_engine
from multibagger.monitor.daily import (
    load_portfolio_positions_batch,
    compute_signals,
    run_daily_monitor,
)


@pytest.fixture
def test_engine():
    """Create test database engine."""
    engine = get_engine()
    return engine


@pytest.fixture
def test_config():
    """Create test config."""
    return {
        'monitoring': {
            'near_target_pct': 0.90,
            'stop_loss_pct': -0.25,
            'min_upside_pct': 0.05,
        }
    }


@pytest.fixture
def setup_test_data(test_engine):
    """Setup test data with 3 positions triggering different alerts."""
    with Session(test_engine) as session:
        # Create test tickers
        test_tickers = [
            (2000, "STOP", "Stop Loss Test", 1),  # Will hit stop loss
            (2001, "TARGET", "Near Target Test", 1),  # Near target
            (2002, "CLEAN", "Clean Position Test", 1),  # No alerts
        ]

        for ticker_id, symbol, name, exchange_id in test_tickers:
            session.execute(text("""
                INSERT OR IGNORE INTO tickers (id, symbol, name, exchange_id, market_cap, currency, active)
                VALUES (:id, :symbol, :name, :exchange_id, 1000000000, 'USD', 1)
            """), {"id": ticker_id, "symbol": symbol, "name": name, "exchange_id": exchange_id})

        # Create test portfolio run
        as_of_date = date(2025, 12, 1)
        session.execute(text("""
            DELETE FROM portfolio_positions WHERE run_id IN (SELECT id FROM portfolio_runs WHERE as_of_date = :as_of)
        """), {"as_of": as_of_date})
        session.execute(text("""
            DELETE FROM portfolio_runs WHERE as_of_date = :as_of
        """), {"as_of": as_of_date})

        run = PortfolioRun(
            as_of_date=as_of_date,
            metrics_json='{"turnover_pct": 0}'
        )
        session.add(run)
        session.flush()
        run_id = run.id

        # Create test positions
        positions = [
            # Position 1: STOP - will hit stop loss (entry $100, current $70, stop $75)
            PortfolioPosition(
                run_id=run_id,
                ticker_id=2000,
                weight_pct=30.0,
                entry_price=100.0,
                target_price=150.0,
                stop_loss_price=75.0,
                conviction_score=85.0,
                notes_json='{"symbol": "STOP"}'
            ),
            # Position 2: TARGET - near target (entry $50, current $135, target $150)
            PortfolioPosition(
                run_id=run_id,
                ticker_id=2001,
                weight_pct=40.0,
                entry_price=50.0,
                target_price=150.0,
                stop_loss_price=37.5,
                conviction_score=90.0,
                notes_json='{"symbol": "TARGET"}'
            ),
            # Position 3: CLEAN - no alerts (entry $100, current $110, target $150)
            PortfolioPosition(
                run_id=run_id,
                ticker_id=2002,
                weight_pct=30.0,
                entry_price=100.0,
                target_price=150.0,
                stop_loss_price=75.0,
                conviction_score=80.0,
                notes_json='{"symbol": "CLEAN"}'
            ),
        ]

        session.bulk_save_objects(positions)

        # Create test prices
        price_date = date(2025, 12, 15)
        prices = [
            (2000, price_date, 70.0),   # STOP: below stop loss
            (2001, price_date, 135.0),  # TARGET: near target (90% of $150)
            (2002, price_date, 110.0),  # CLEAN: normal range
        ]

        for ticker_id, pdate, price in prices:
            session.execute(text("""
                INSERT OR REPLACE INTO prices (ticker_id, date, adj_close, close_price, volume)
                VALUES (:ticker_id, :date, :price, :price, 1000000)
            """), {"ticker_id": ticker_id, "date": pdate, "price": price})

        # Create research data
        for ticker_id in [2000, 2001, 2002]:
            session.execute(text("""
                INSERT OR REPLACE INTO research (ticker_id, as_of_date, base_fair_value, upside_pct)
                VALUES (:ticker_id, :as_of, 150.0, 20.0)
            """), {"ticker_id": ticker_id, "as_of": as_of_date})

        # Create risk flags (no new flags)
        for ticker_id in [2000, 2001, 2002]:
            session.execute(text("""
                INSERT OR REPLACE INTO risk_flags (ticker_id, as_of_date, first_fail_reason, created_at)
                VALUES (:ticker_id, :as_of, NULL, :created_at)
            """), {"ticker_id": ticker_id, "as_of": as_of_date, "created_at": datetime.now()})

        session.commit()

    yield {
        'run_id': run_id,
        'as_of': '2025-12',
        'price_date': price_date
    }


def test_load_positions_batch(test_engine, setup_test_data):
    """Test batch loading of portfolio positions."""
    with Session(test_engine) as session:
        positions_df, as_of, price_date = load_portfolio_positions_batch(
            session,
            as_of=setup_test_data['as_of'],
            price_date=setup_test_data['price_date']
        )

    # Verify we got 3 positions
    assert len(positions_df) == 3
    assert as_of == setup_test_data['as_of']
    assert price_date == setup_test_data['price_date']

    # Verify symbols
    symbols = set(positions_df['symbol'].tolist())
    assert symbols == {'STOP', 'TARGET', 'CLEAN'}

    # Verify prices loaded
    assert all(positions_df['current_price'].notna())


def test_compute_signals(test_engine, setup_test_data, test_config):
    """Test signal computation (vectorized)."""
    with Session(test_engine) as session:
        positions_df, _, _ = load_portfolio_positions_batch(
            session,
            as_of=setup_test_data['as_of'],
            price_date=setup_test_data['price_date']
        )

    alerts_df = compute_signals(positions_df, test_config['monitoring'])

    # Should have 2 alerts: 1 STOP_LOSS, 1 NEAR_TARGET
    assert len(alerts_df) == 2

    # Verify signals
    signals = set(alerts_df['signal'].tolist())
    assert 'STOP_LOSS' in signals
    assert 'NEAR_TARGET' in signals

    # Verify STOP alert
    stop_alert = alerts_df[alerts_df['signal'] == 'STOP_LOSS'].iloc[0]
    assert stop_alert['symbol'] == 'STOP'
    assert stop_alert['current_price'] == 70.0
    assert stop_alert['stop_loss_price'] == 75.0

    # Verify TARGET alert
    target_alert = alerts_df[alerts_df['signal'] == 'NEAR_TARGET'].iloc[0]
    assert target_alert['symbol'] == 'TARGET'
    assert target_alert['current_price'] == 135.0
    assert target_alert['target_price'] == 150.0

    # Verify sorting (STOP_LOSS should come first)
    assert alerts_df.iloc[0]['signal'] == 'STOP_LOSS'


def test_determinism(test_engine, setup_test_data, test_config):
    """Test determinism: same inputs → identical outputs."""
    with Session(test_engine) as session:
        positions_df, _, _ = load_portfolio_positions_batch(
            session,
            as_of=setup_test_data['as_of'],
            price_date=setup_test_data['price_date']
        )

    # Run twice
    alerts1 = compute_signals(positions_df, test_config['monitoring'])
    alerts2 = compute_signals(positions_df, test_config['monitoring'])

    # Should be identical
    pd.testing.assert_frame_equal(alerts1, alerts2)


def test_run_daily_monitor_integration(test_engine, setup_test_data, test_config, tmp_path):
    """Test end-to-end monitoring run."""
    config = Config()
    config._config = test_config

    results = run_daily_monitor(
        config=config,
        date_str=setup_test_data['price_date'].isoformat(),
        as_of=setup_test_data['as_of'],
        output_dir=str(tmp_path),
        dry_run=False
    )

    # Verify results
    assert results['status'] == 'success'
    assert results['positions_checked'] == 3
    assert results['total_alerts'] == 2

    # Verify files created
    alerts_csv = Path(results['output_paths']['alerts_csv'])
    metrics_json = Path(results['output_paths']['metrics_json'])

    assert alerts_csv.exists()
    assert metrics_json.exists()

    # Verify CSV content
    alerts_df = pd.read_csv(alerts_csv)
    assert len(alerts_df) == 2

    # Verify JSON content
    with open(metrics_json, 'r') as f:
        metrics = json.load(f)

    assert metrics['positions_checked'] == 3
    assert metrics['total_alerts'] == 2
    assert 'STOP_LOSS' in metrics['signal_counts']
    assert 'NEAR_TARGET' in metrics['signal_counts']


def test_dry_run(test_engine, setup_test_data, test_config, tmp_path):
    """Test dry-run mode (no file writes)."""
    config = Config()
    config._config = test_config

    results = run_daily_monitor(
        config=config,
        date_str=setup_test_data['price_date'].isoformat(),
        as_of=setup_test_data['as_of'],
        output_dir=str(tmp_path),
        dry_run=True
    )

    # Verify results returned but no files written
    assert results['status'] == 'success'
    assert results['total_alerts'] == 2
    assert results['output_paths'] == {}

    # Verify no files created
    alerts_dir = tmp_path / setup_test_data['as_of'] / "alerts"
    if alerts_dir.exists():
        assert len(list(alerts_dir.glob("*.csv"))) == 0
        assert len(list(alerts_dir.glob("*.json"))) == 0
