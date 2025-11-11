"""Daily portfolio monitoring - batch-first, deterministic alert generation

Reads persisted portfolio (Phase 5.1) and local DB data to raise alerts.
No per-ticker network calls - uses only local DB/cached data.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.schema import get_engine

logger = logging.getLogger(__name__)

# Signal severity ordering (for sorting)
SIGNAL_PRIORITY = {
    'STOP_LOSS': 1,
    'THESIS_RISK': 2,
    'NEAR_TARGET': 3,
}


def load_portfolio_positions_batch(
    session: Session,
    as_of: str | None = None,
    price_date: date | None = None
) -> Tuple[pd.DataFrame, str, date]:
    """
    Load portfolio positions with latest prices in a single batch query.

    Args:
        session: DB session
        as_of: Portfolio run date (YYYY-MM), defaults to latest
        price_date: Price date, defaults to max(prices.date)

    Returns:
        Tuple of (positions_df, as_of_used, price_date_used)
    """
    # Get latest portfolio run if as_of not specified
    if as_of:
        as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d").date()
    else:
        result = session.execute(text("""
            SELECT as_of_date FROM portfolio_runs
            ORDER BY as_of_date DESC LIMIT 1
        """))
        row = result.first()
        if not row:
            raise ValueError("No portfolio runs found in database")
        as_of_date = row[0]
        as_of = as_of_date.strftime("%Y-%m")

    # Get max price date if not specified
    if price_date is None:
        result = session.execute(text("SELECT MAX(date) FROM prices"))
        price_date = result.scalar()
        if not price_date:
            raise ValueError("No prices found in database")

    # Batch query: positions + tickers + latest prices + research + risk flags
    query = text("""
        WITH latest_prices AS (
            SELECT
                ticker_id,
                adj_close,
                date,
                ROW_NUMBER() OVER (PARTITION BY ticker_id ORDER BY date DESC) as rn
            FROM prices
            WHERE date <= :price_date
        ),
        new_red_flags AS (
            SELECT
                ticker_id,
                COUNT(*) as flag_count,
                GROUP_CONCAT(first_fail_reason, ', ') as reasons
            FROM risk_flags
            WHERE as_of_date > :run_as_of
              AND as_of_date <= :price_date
              AND first_fail_reason IS NOT NULL
            GROUP BY ticker_id
        )
        SELECT
            pr.id as run_id,
            pr.as_of_date as run_date,
            pp.id as position_id,
            pp.ticker_id,
            t.symbol,
            pp.weight_pct as held_weight_pct,
            pp.entry_price,
            pp.target_price,
            pp.stop_loss_price,
            pp.conviction_score,
            pp.notes_json,
            lp.adj_close as current_price,
            lp.date as price_date,
            r.upside_pct as research_upside_pct,
            r.base_fair_value as research_target,
            nrf.flag_count as new_red_flag_count,
            nrf.reasons as new_red_flag_reasons
        FROM portfolio_runs pr
        JOIN portfolio_positions pp ON pp.run_id = pr.id
        JOIN tickers t ON t.id = pp.ticker_id
        LEFT JOIN latest_prices lp ON lp.ticker_id = pp.ticker_id AND lp.rn = 1
        LEFT JOIN research r ON r.ticker_id = pp.ticker_id AND r.as_of_date = pr.as_of_date
        LEFT JOIN new_red_flags nrf ON nrf.ticker_id = pp.ticker_id
        WHERE pr.as_of_date = :run_as_of
        ORDER BY pp.weight_pct DESC, pp.ticker_id ASC
    """)

    result = session.execute(query, {
        "run_as_of": as_of_date,
        "price_date": price_date
    })

    columns = [
        'run_id', 'run_date', 'position_id', 'ticker_id', 'symbol',
        'held_weight_pct', 'entry_price', 'target_price', 'stop_loss_price',
        'conviction_score', 'notes_json', 'current_price', 'price_date',
        'research_upside_pct', 'research_target', 'new_red_flag_count',
        'new_red_flag_reasons'
    ]

    positions_df = pd.DataFrame(result.fetchall(), columns=columns)

    logger.info(f"Loaded {len(positions_df)} positions for {as_of} with prices as of {price_date}")

    return positions_df, as_of, price_date


def compute_signals(
    positions_df: pd.DataFrame,
    config: Dict
) -> pd.DataFrame:
    """
    Compute alert signals vectorized (no loops).

    Args:
        positions_df: Positions with prices
        config: Monitor config with thresholds

    Returns:
        Alerts DataFrame with one row per signal
    """
    near_target_pct = config.get('near_target_pct', 0.90)
    stop_loss_pct = config.get('stop_loss_pct', -0.25)
    min_upside_pct = config.get('min_upside_pct', 0.05)

    alerts = []

    for _, pos in positions_df.iterrows():
        ticker_id = pos['ticker_id']
        symbol = pos['symbol']
        current_price = pos['current_price']
        entry_price = pos['entry_price']
        target_price = pos['target_price'] or pos['research_target']
        stop_loss_price = pos['stop_loss_price']
        held_weight_pct = pos['held_weight_pct']
        price_date = pos['price_date']
        new_red_flags = pos['new_red_flag_count'] or 0

        # Skip if no current price
        if pd.isna(current_price):
            logger.warning(f"No price data for {symbol} (ticker_id={ticker_id})")
            continue

        # Compute default stop loss if not set
        if pd.isna(stop_loss_price) and not pd.isna(entry_price):
            stop_loss_price = entry_price * (1 + stop_loss_pct)

        # Signal 1: STOP_LOSS
        if not pd.isna(stop_loss_price) and current_price <= stop_loss_price:
            loss_pct = (current_price / entry_price - 1) * 100 if not pd.isna(entry_price) else 0
            alerts.append({
                'run_id': pos['run_id'],
                'as_of': pos['run_date'],
                'price_date': price_date,
                'ticker_id': ticker_id,
                'symbol': symbol,
                'signal': 'STOP_LOSS',
                'current_price': float(current_price),
                'entry_price': float(entry_price) if not pd.isna(entry_price) else None,
                'target_price': float(target_price) if not pd.isna(target_price) else None,
                'stop_loss_price': float(stop_loss_price),
                'held_weight_pct': float(held_weight_pct),
                'reason': f"Price ${current_price:.2f} ≤ stop ${stop_loss_price:.2f} ({loss_pct:.1f}% loss)"
            })

        # Signal 2: NEAR_TARGET
        if not pd.isna(target_price) and current_price >= target_price * near_target_pct:
            progress_pct = (current_price / target_price) * 100
            alerts.append({
                'run_id': pos['run_id'],
                'as_of': pos['run_date'],
                'price_date': price_date,
                'ticker_id': ticker_id,
                'symbol': symbol,
                'signal': 'NEAR_TARGET',
                'current_price': float(current_price),
                'entry_price': float(entry_price) if not pd.isna(entry_price) else None,
                'target_price': float(target_price),
                'stop_loss_price': float(stop_loss_price) if not pd.isna(stop_loss_price) else None,
                'held_weight_pct': float(held_weight_pct),
                'reason': f"Price ${current_price:.2f} is {progress_pct:.1f}% of target ${target_price:.2f}"
            })

        # Signal 3: THESIS_RISK
        thesis_risk_reasons = []

        # Check for new red flags
        if new_red_flags > 0:
            reasons_str = pos['new_red_flag_reasons'] or 'unknown'
            thesis_risk_reasons.append(f"{int(new_red_flags)} new red flag(s): {reasons_str}")

        # Check current upside
        if not pd.isna(target_price) and target_price > 0:
            current_upside = (target_price / current_price - 1)
            if current_upside < min_upside_pct:
                thesis_risk_reasons.append(f"Upside {current_upside*100:.1f}% < {min_upside_pct*100:.1f}%")

        if thesis_risk_reasons:
            alerts.append({
                'run_id': pos['run_id'],
                'as_of': pos['run_date'],
                'price_date': price_date,
                'ticker_id': ticker_id,
                'symbol': symbol,
                'signal': 'THESIS_RISK',
                'current_price': float(current_price),
                'entry_price': float(entry_price) if not pd.isna(entry_price) else None,
                'target_price': float(target_price) if not pd.isna(target_price) else None,
                'stop_loss_price': float(stop_loss_price) if not pd.isna(stop_loss_price) else None,
                'held_weight_pct': float(held_weight_pct),
                'reason': '; '.join(thesis_risk_reasons)
            })

    alerts_df = pd.DataFrame(alerts)

    if not alerts_df.empty:
        # Sort by severity, weight DESC, ticker_id ASC (deterministic)
        alerts_df['signal_priority'] = alerts_df['signal'].map(SIGNAL_PRIORITY)
        alerts_df = alerts_df.sort_values(
            ['signal_priority', 'held_weight_pct', 'ticker_id'],
            ascending=[True, False, True]
        ).drop(columns=['signal_priority'])

    logger.info(f"Generated {len(alerts_df)} alerts")

    return alerts_df


def save_monitor_outputs(
    alerts_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    price_date: date,
    as_of: str,
    output_dir: str,
    config: Dict
) -> Dict[str, str]:
    """
    Save alerts CSV and metrics JSON (deterministic).

    Args:
        alerts_df: Alerts DataFrame
        positions_df: Positions DataFrame
        price_date: Price date used
        as_of: Portfolio run date
        output_dir: Output directory
        config: Monitor config

    Returns:
        Dict with output file paths
    """
    # Create output directory
    alerts_dir = Path(output_dir) / as_of / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)

    date_str = price_date.strftime("%Y-%m-%d")

    # Save alerts CSV
    alerts_csv = alerts_dir / f"portfolio_alerts_{date_str}.csv"
    if not alerts_df.empty:
        # Select and order columns for CSV
        csv_columns = [
            'as_of', 'price_date', 'ticker_id', 'symbol', 'signal',
            'current_price', 'entry_price', 'target_price', 'stop_loss_price',
            'held_weight_pct', 'reason'
        ]
        alerts_df[csv_columns].to_csv(alerts_csv, index=False)
        logger.info(f"Saved {len(alerts_df)} alerts to {alerts_csv}")
    else:
        # Save empty CSV with headers
        pd.DataFrame(columns=[
            'as_of', 'price_date', 'ticker_id', 'symbol', 'signal',
            'current_price', 'entry_price', 'target_price', 'stop_loss_price',
            'held_weight_pct', 'reason'
        ]).to_csv(alerts_csv, index=False)
        logger.info(f"No alerts - saved empty CSV to {alerts_csv}")

    # Compute metrics
    signal_counts = alerts_df['signal'].value_counts().to_dict() if not alerts_df.empty else {}

    # Tickers with multiple signals
    multi_signal_tickers = []
    if not alerts_df.empty:
        signal_counts_per_ticker = alerts_df.groupby('ticker_id')['signal'].nunique()
        multi_signal_tickers = signal_counts_per_ticker[signal_counts_per_ticker > 1].index.tolist()

    metrics = {
        'date': date_str,
        'portfolio_as_of': as_of,
        'price_date': price_date.isoformat(),
        'positions_checked': len(positions_df),
        'total_alerts': len(alerts_df),
        'signal_counts': {k: int(v) for k, v in signal_counts.items()},
        'tickers_with_multiple_signals': len(multi_signal_tickers),
        'multi_signal_ticker_ids': [int(tid) for tid in multi_signal_tickers],
        'config': {
            'near_target_pct': config.get('near_target_pct'),
            'stop_loss_pct': config.get('stop_loss_pct'),
            'min_upside_pct': config.get('min_upside_pct'),
        }
    }

    # Save metrics JSON
    metrics_json = alerts_dir / f"monitor_metrics_{date_str}.json"
    with open(metrics_json, 'w') as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Saved metrics to {metrics_json}")

    return {
        'alerts_csv': str(alerts_csv),
        'metrics_json': str(metrics_json)
    }


def run_daily_monitor(
    config: Config,
    date_str: str | None = None,
    as_of: str | None = None,
    output_dir: str = "snapshots",
    dry_run: bool = False
) -> Dict:
    """
    Run daily portfolio monitoring (batch-first, deterministic).

    Args:
        config: System config
        date_str: Price date (YYYY-MM-DD), defaults to latest
        as_of: Portfolio run (YYYY-MM), defaults to latest
        output_dir: Output directory
        dry_run: Print only, don't write files

    Returns:
        Dict with results
    """
    logger.info("Starting daily portfolio monitor")

    # Parse date
    price_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

    # Get monitor config
    monitor_config = config.get('monitoring', {}) if hasattr(config, 'get') else {}

    # Load positions batch
    engine = get_engine()
    with Session(engine) as session:
        positions_df, as_of_used, price_date_used = load_portfolio_positions_batch(
            session, as_of, price_date
        )

    if positions_df.empty:
        logger.warning("No positions found")
        return {
            'status': 'no_positions',
            'as_of': as_of_used,
            'price_date': price_date_used,
            'alerts': pd.DataFrame()
        }

    # Compute signals vectorized
    alerts_df = compute_signals(positions_df, monitor_config)

    # Save outputs (unless dry-run)
    output_paths = {}
    if not dry_run:
        output_paths = save_monitor_outputs(
            alerts_df,
            positions_df,
            price_date_used,
            as_of_used,
            output_dir,
            monitor_config
        )

    return {
        'status': 'success',
        'as_of': as_of_used,
        'price_date': price_date_used,
        'positions_checked': len(positions_df),
        'total_alerts': len(alerts_df),
        'alerts': alerts_df,
        'output_paths': output_paths
    }
