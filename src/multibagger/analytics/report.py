#!/usr/bin/env python3
"""
Analytics Report Generation - Phase 7

Generate deterministic reports from analytics data:
- analytics_{YYYY-MM}.json (all metrics)
- analytics_{YYYY-MM}.csv (time series)
- analytics_report_{YYYY-MM}.md (human-readable)

All outputs are sorted/ordered for determinism.
"""

import csv
import json
from pathlib import Path
from typing import Dict

from rich.console import Console
from rich.table import Table


def generate_reports(
    analytics: Dict,
    output_dir: Path | None = None
) -> Dict[str, Path]:
    """
    Generate all report formats.

    Args:
        analytics: Analytics dict from compute_analytics()
        output_dir: Output directory (defaults to snapshots/{as_of}/analytics/)

    Returns:
        Dict mapping report type to file path
    """
    as_of = analytics['as_of']

    if output_dir is None:
        output_dir = Path("snapshots") / as_of / "analytics"

    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {}

    # 1. JSON report
    outputs['json'] = _generate_json_report(analytics, output_dir)

    # 2. CSV report (time series)
    # outputs['csv'] = _generate_csv_report(analytics, output_dir)

    # 3. Markdown report
    outputs['markdown'] = _generate_markdown_report(analytics, output_dir)

    return outputs


def _generate_json_report(analytics: Dict, output_dir: Path) -> Path:
    """Generate JSON report with all metrics"""
    as_of = analytics['as_of']
    output_file = output_dir / f"analytics_{as_of}.json"

    # Sort keys for determinism
    with open(output_file, "w") as f:
        json.dump(analytics, f, indent=2, sort_keys=True)

    return output_file


def _generate_csv_report(analytics: Dict, output_dir: Path) -> Path:
    """Generate CSV time series report"""
    as_of = analytics['as_of']
    output_file = output_dir / f"analytics_{as_of}.csv"

    # Note: This requires time series data which we don't have in the analytics dict yet
    # Placeholder implementation

    headers = [
        'date',
        'portfolio_value',
        'portfolio_return_pct',
        'benchmark_value',
        'benchmark_return_pct',
        'active_return_pct',
        'drawdown_pct',
        'positions'
    ]

    with open(output_file, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        # TODO: Write time series rows
        # For now, write placeholder

    return output_file


def _generate_markdown_report(analytics: Dict, output_dir: Path) -> Path:
    """Generate human-readable markdown report"""
    as_of = analytics['as_of']
    output_file = output_dir / f"analytics_report_{as_of}.md"

    lines = []

    # Header
    lines.append(f"# Portfolio Performance Report - {as_of}")
    lines.append("")

    # Check for errors
    if 'error' in analytics:
        lines.append(f"**Error:** {analytics['error']}")
        with open(output_file, "w") as f:
            f.write("\n".join(lines))
        return output_file

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Period:** {analytics['start_date']} to {analytics['end_date']} ({analytics['window_months']} months)")

    returns = analytics.get('returns', {})
    lines.append(f"- **Total Return:** {returns.get('total_return_pct', 'N/A')}%")
    lines.append(f"- **CAGR:** {returns.get('cagr_pct', 'N/A')}%")
    lines.append(f"- **Volatility:** {returns.get('volatility_pct', 'N/A')}%")

    risk = analytics.get('risk', {})
    lines.append(f"- **Max Drawdown:** {risk.get('max_drawdown_pct', 'N/A')}%")
    lines.append("")

    # Benchmark comparison
    bench = analytics.get('benchmark_comparison')
    if bench:
        lines.append(f"## Benchmark Comparison ({analytics.get('benchmark', 'N/A')})")
        lines.append("")
        lines.append(f"- **Benchmark Return:** {bench.get('benchmark_total_return_pct', 'N/A')}%")

        port_ret = returns.get('total_return_pct', 0)
        bench_ret = bench.get('benchmark_total_return_pct', 0)
        outperformance = port_ret - bench_ret
        lines.append(f"- **Outperformance:** {outperformance:+.2f}%")

        lines.append(f"- **Alpha:** {bench.get('alpha_pct', 'N/A')}% annually")
        lines.append(f"- **Beta:** {bench.get('beta', 'N/A')}")
        lines.append(f"- **R²:** {bench.get('r_squared', 'N/A')}")
        lines.append(f"- **Information Ratio:** {bench.get('information_ratio', 'N/A')}")
        lines.append("")
    else:
        lines.append("## Benchmark Comparison")
        lines.append("")
        lines.append("*Benchmark data not available*")
        lines.append("")

    # Risk metrics
    lines.append("## Risk Metrics")
    lines.append("")
    lines.append(f"- **Sharpe Ratio:** {returns.get('sharpe_ratio', 'N/A')}")
    lines.append(f"- **Calmar Ratio:** {returns.get('calmar_ratio', 'N/A')}")
    lines.append(f"- **Max Drawdown:** {risk.get('max_drawdown_pct', 'N/A')}% ({risk.get('max_drawdown_date', 'N/A')})")

    recovery = risk.get('recovery_months', 0)
    if recovery > 0:
        lines.append(f"- **Recovery Time:** {recovery} months")
    lines.append("")

    # Hit rates
    hit_rates = analytics.get('hit_rates', {})
    lines.append("## Hit Rates")
    lines.append("")

    if 'note' in hit_rates:
        lines.append(f"*{hit_rates['note']}*")
    else:
        lines.append(f"- **3-month:** {hit_rates.get('hit_rate_3m', 0)*100:.0f}%")
        lines.append(f"- **6-month:** {hit_rates.get('hit_rate_6m', 0)*100:.0f}%")
        lines.append(f"- **12-month:** {hit_rates.get('hit_rate_12m', 0)*100:.0f}%")
    lines.append("")

    # Attribution
    attribution = analytics.get('attribution', {})
    lines.append("## Top Contributors")
    lines.append("")

    top_contrib = attribution.get('top_contributors', [])
    if top_contrib:
        for i, item in enumerate(top_contrib, 1):
            lines.append(f"{i}. {item['symbol']}: {item['contribution_pct']:.2f}%")
    else:
        lines.append("*No data*")
    lines.append("")

    lines.append("## Top Detractors")
    lines.append("")

    top_detract = attribution.get('top_detractors', [])
    if top_detract:
        for i, item in enumerate(top_detract, 1):
            lines.append(f"{i}. {item['symbol']}: {item['contribution_pct']:.2f}%")
    else:
        lines.append("*No data*")
    lines.append("")

    # Turnover
    if 'avg_turnover_pct' in attribution:
        lines.append("## Turnover")
        lines.append("")
        lines.append(f"- **Average Turnover:** {attribution['avg_turnover_pct']:.1f}%")
        lines.append(f"- **Turnover Cost:** {attribution['turnover_cost_pct']:.2f}%")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    metadata = analytics.get('metadata', {})
    lines.append(f"*Data sources: Local DB (portfolio_positions, prices), Snapshots (stage CSVs)*")
    lines.append(f"*Positions analyzed: {metadata.get('positions_analyzed', 'N/A')}*")
    lines.append(f"*Months with data: {metadata.get('months_with_data', 'N/A')}*")
    lines.append("")

    # Write file
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    return output_file


def print_analytics_summary(analytics: Dict) -> None:
    """Print analytics summary to console using Rich"""
    console = Console()

    console.print()
    console.print(f"[bold]Analytics Report - {analytics['as_of']}[/bold]")
    console.print()

    if 'error' in analytics:
        console.print(f"[red]Error: {analytics['error']}[/red]")
        return

    # Returns table
    table = Table(title="Returns & Risk", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="yellow", justify="right")

    returns = analytics.get('returns', {})
    risk = analytics.get('risk', {})

    table.add_row("Total Return", f"{returns.get('total_return_pct', 0):.2f}%")
    table.add_row("CAGR", f"{returns.get('cagr_pct', 0):.2f}%")
    table.add_row("Volatility", f"{returns.get('volatility_pct', 0):.2f}%")
    table.add_row("Sharpe Ratio", f"{returns.get('sharpe_ratio', 0):.2f}")
    table.add_row("Calmar Ratio", f"{returns.get('calmar_ratio', 0):.2f}")
    table.add_row("Max Drawdown", f"{risk.get('max_drawdown_pct', 0):.2f}%")

    console.print(table)
    console.print()

    # Benchmark comparison
    bench = analytics.get('benchmark_comparison')
    if bench:
        table2 = Table(title=f"Benchmark Comparison ({analytics.get('benchmark')})", show_header=True)
        table2.add_column("Metric", style="cyan")
        table2.add_column("Value", style="yellow", justify="right")

        table2.add_row("Benchmark Return", f"{bench.get('benchmark_total_return_pct', 0):.2f}%")
        table2.add_row("Alpha (annualized)", f"{bench.get('alpha_pct', 0):.2f}%")
        table2.add_row("Beta", f"{bench.get('beta', 0):.2f}")
        table2.add_row("R²", f"{bench.get('r_squared', 0):.2f}")
        table2.add_row("Information Ratio", f"{bench.get('information_ratio', 0):.2f}")

        console.print(table2)
        console.print()

    # Attribution
    attribution = analytics.get('attribution', {})
    if attribution.get('top_contributors'):
        table3 = Table(title="Top 5 Contributors", show_header=True)
        table3.add_column("Symbol", style="cyan")
        table3.add_column("Contribution", style="green", justify="right")

        for item in attribution['top_contributors']:
            table3.add_row(item['symbol'], f"{item['contribution_pct']:.2f}%")

        console.print(table3)
        console.print()
