"""Generate portfolio reconciliation output artifacts"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def save_reconciliation_outputs(
    results: Dict,
    as_of: str,
    output_dir: str = "snapshots"
) -> Dict[str, str]:
    """
    Save all reconciliation artifacts to disk.

    Args:
        results: Reconciliation results dict
        as_of: YYYY-MM date
        output_dir: Base output directory

    Returns:
        Dict of {artifact_name: file_path}
    """
    # Create portfolio output directory
    portfolio_dir = Path(output_dir) / as_of / "portfolio"
    portfolio_dir.mkdir(parents=True, exist_ok=True)

    output_paths = {}

    # 1. Holdings Reconcile CSV (full detail)
    reconcile_path = portfolio_dir / f"holdings_reconcile_{as_of}.csv"
    actions_df = results['actions']

    if not actions_df.empty:
        # Select and order columns
        output_cols = [
            'ticker_id', 'symbol', 'held_weight', 'model_weight',
            'delta_weight', 'action', 'reason'
        ]

        reconcile_df = actions_df[output_cols].copy()
        reconcile_df.to_csv(reconcile_path, index=False)

        logger.info(f"Saved reconciliation details: {reconcile_path}")
        output_paths['reconcile'] = str(reconcile_path)

    # 2. Rebalance Actions CSV (trades only)
    actions_path = portfolio_dir / f"rebalance_actions_{as_of}.csv"

    trades_df = actions_df[actions_df['action'].isin(['BUY', 'SELL', 'TRIM', 'ADD'])].copy()

    if not trades_df.empty:
        trade_cols = [
            'action', 'ticker_id', 'symbol', 'held_weight', 'model_weight',
            'delta_weight', 'reason'
        ]

        trades_df[trade_cols].to_csv(actions_path, index=False)

        logger.info(f"Saved rebalance actions: {actions_path}")
        output_paths['actions'] = str(actions_path)
    else:
        logger.info("No rebalance actions needed (all HOLD)")

    # 3. Unmatched Holdings CSV
    unmatched_df = results.get('unmatched', pd.DataFrame())

    if not unmatched_df.empty:
        unmatched_path = portfolio_dir / f"unmatched_holdings_{as_of}.csv"

        unmatched_cols = ['symbol', 'exchange', 'quantity', 'reason'] if 'quantity' in unmatched_df.columns else ['symbol', 'exchange', 'weight_pct', 'reason']

        available_cols = [col for col in unmatched_cols if col in unmatched_df.columns]
        unmatched_df[available_cols].to_csv(unmatched_path, index=False)

        logger.info(f"Saved unmatched holdings: {unmatched_path}")
        output_paths['unmatched'] = str(unmatched_path)

    # 4. Portfolio Metrics JSON
    metrics_path = portfolio_dir / f"portfolio_metrics_{as_of}.json"

    metrics = {
        'as_of_date': as_of,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'holdings_count': results['holdings_count'],
        'matched_count': results['matched_count'],
        'unmatched_count': results['unmatched_count'],
        'model_positions': results['model_positions'],
        'actions': results['stats'],
        'implied_cash_pct': round(100.0 - actions_df[actions_df['action'] != 'SELL']['model_weight'].sum(), 2) if not actions_df.empty else 0,
        'turnover_pct': results['stats'].get('turnover_pct', 0),
    }

    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Saved portfolio metrics: {metrics_path}")
    output_paths['metrics'] = str(metrics_path)

    return output_paths


def print_reconciliation_summary(results: Dict, output_paths: Dict[str, str]):
    """
    Print rich console summary of reconciliation.

    Args:
        results: Reconciliation results
        output_paths: Dict of output file paths
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Summary stats
    console.print(f"\n[bold blue]Portfolio Reconciliation Summary ({results['as_of_date']})[/bold blue]\n")

    summary_table = Table(title="Overview")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Holdings Loaded", str(results['holdings_count']))
    summary_table.add_row("Successfully Matched", str(results['matched_count']))
    summary_table.add_row("Unmatched", str(results['unmatched_count']))
    summary_table.add_row("Model Positions", str(results['model_positions']))
    summary_table.add_row("Turnover", f"{results['stats']['turnover_pct']:.2f}%")

    console.print(summary_table)

    # Actions breakdown
    actions_table = Table(title="Actions Breakdown")
    actions_table.add_column("Action", style="cyan")
    actions_table.add_column("Count", style="magenta")

    stats = results['stats']
    for action in ['BUY', 'SELL', 'TRIM', 'ADD', 'HOLD']:
        count = stats.get(action, 0)
        if count > 0:
            actions_table.add_row(action, str(count))

    console.print(actions_table)

    # Top actions
    actions_df = results['actions']

    if not actions_df.empty:
        trades = actions_df[actions_df['action'].isin(['BUY', 'SELL', 'TRIM', 'ADD'])]

        if not trades.empty:
            console.print("\n[bold]Top Actions:[/bold]")

            top_actions_table = Table()
            top_actions_table.add_column("Action", style="cyan")
            top_actions_table.add_column("Symbol", style="green")
            top_actions_table.add_column("Held%", style="yellow")
            top_actions_table.add_column("Model%", style="yellow")
            top_actions_table.add_column("Δ%", style="magenta")
            top_actions_table.add_column("Reason", style="white")

            for _, row in trades.head(10).iterrows():
                top_actions_table.add_row(
                    row['action'],
                    row['symbol'],
                    f"{row['held_weight']:.1f}",
                    f"{row['model_weight']:.1f}",
                    f"{row['delta_weight']:+.1f}",
                    row['reason'][:40]  # Truncate long reasons
                )

            console.print(top_actions_table)

    # Unmatched warnings
    if results['unmatched_count'] > 0:
        console.print(f"\n[yellow]⚠️  {results['unmatched_count']} holdings could not be matched to tickers[/yellow]")
        console.print(f"   See: {output_paths.get('unmatched', 'N/A')}")

    # Output files
    console.print("\n[bold]Output Files:[/bold]")
    for name, path in output_paths.items():
        console.print(f"  • {name}: {path}")

    console.print("\n[green]✅ Portfolio reconciliation complete![/green]")
