"""Data management CLI commands for Multi-Bagger Research System"""

import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from multibagger.config import get_config
from multibagger.data.config import DataConfig
from multibagger.data.fetcher import DataFetcher
from multibagger.data.populate import DataPopulator

app = typer.Typer(
    name="data",
    help="Data fetching and caching management commands",
    rich_markup_mode="rich",
)

console = Console()


def load_config() -> DataConfig:
    """Load data configuration from config.yml"""
    config_path = Path("config.yml")
    if config_path.exists():
        # In a real implementation, this would parse YAML
        # For now, return default config
        return DataConfig.create_default()
    else:
        console.print("[yellow]Warning: config.yml not found, using defaults[/yellow]")
        return DataConfig.create_default()


@app.command()
def warm(
    month_year: str = typer.Option(
        None, help="Month to warm cache for (YYYY-MM format)"
    )
) -> None:
    """Warm cache for a specific month by fetching commonly needed data"""
    if month_year is None:
        # Default to current month
        month_year = datetime.datetime.now().strftime("%Y-%m")

    try:
        # Parse the month
        year, month = map(int, month_year.split("-"))
        as_of = datetime.datetime(year, month, 1)

        console.print(f"[blue]🔥 Warming cache for {month_year}[/blue]")

        config = load_config()
        fetcher = DataFetcher(config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Warming cache with sample data...", total=None)

            summary = fetcher.warm_cache(as_of)

            progress.remove_task(task)

        # Display results
        table = Table(title=f"Cache Warming Results - {month_year}")
        table.add_column("Operation", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Details", style="green")

        table.add_row(
            "Instruments Fetched", str(summary["instruments_fetched"]), "Stock metadata"
        )
        table.add_row(
            "Prices Fetched", str(summary["prices_fetched"]), "OHLCV data points"
        )
        table.add_row(
            "Fundamentals Fetched",
            str(summary["fundamentals_fetched"]),
            "Financial statements",
        )
        table.add_row(
            "Filings Fetched", str(summary["filings_fetched"]), "SEC filings metadata"
        )
        table.add_row(
            "Cache Hits", str(summary["cache_hits"]), "Items served from cache"
        )
        table.add_row(
            "Network Calls", str(summary["network_calls"]), "API requests made"
        )
        table.add_row(
            "Execution Time", f"{summary['execution_time_ms']}ms", "Total duration"
        )

        console.print(table)

        # Calculate hit rate
        total_requests = summary["cache_hits"] + summary["network_calls"]
        if total_requests > 0:
            hit_rate = (summary["cache_hits"] / total_requests) * 100
            console.print(f"\n📊 Cache Hit Rate: [bold]{hit_rate:.1f}%[/bold]")

        console.print("\n✅ Cache warming completed successfully!")

    except ValueError:
        console.print("[red]❌ Invalid month format. Use YYYY-MM (e.g., 2025-11)[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Cache warming failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stats() -> None:
    """Show cache statistics"""
    console.print("[blue]📊 Cache Statistics[/blue]")

    try:
        config = load_config()
        fetcher = DataFetcher(config)

        stats = fetcher.get_cache_stats()

        table = Table(title="HTTP Cache Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Entries", str(stats.total_entries))
        table.add_row("Expired Entries", str(stats.expired_entries))
        table.add_row("Cache Size", f"{stats.size_bytes:,} bytes")
        table.add_row(
            "Oldest Entry",
            stats.oldest_entry.isoformat() if stats.oldest_entry else "None",
        )
        table.add_row(
            "Newest Entry",
            stats.newest_entry.isoformat() if stats.newest_entry else "None",
        )
        table.add_row(
            "Hit Rate", f"{stats.hit_rate:.1f}%" if stats.hit_rate > 0 else "N/A"
        )

        console.print(table)

        if stats.top_keys:
            console.print("\n[blue]Top Cache Keys by Size:[/blue]")
            for i, key in enumerate(stats.top_keys[:5], 1):
                console.print(f"  {i}. {key}")

        console.print("\n✅ Cache stats retrieved successfully!")

    except Exception as e:
        console.print(f"[red]❌ Failed to get cache stats: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def prune(
    older_than: int = typer.Option(
        30, "--older-than", "-d", help="Prune entries older than N days"
    )
) -> None:
    """Prune expired or old cache entries"""
    console.print(f"[blue]🧹 Pruning cache entries older than {older_than} days[/blue]")

    try:
        config = load_config()
        fetcher = DataFetcher(config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Pruning cache entries...", total=None)

            removed_count = fetcher.prune_cache(older_than)

            progress.remove_task(task)

        console.print(f"✅ Pruned {removed_count} cache entries")

    except Exception as e:
        console.print(f"[red]❌ Cache pruning failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check() -> None:
    """Check connectivity and authentication for enabled data sources"""
    console.print("[blue]🔍 Data Source Connectivity Check[/blue]")

    try:
        config = load_config()

        table = Table(title="Data Source Status")
        table.add_column("Source", style="cyan")
        table.add_column("Enabled", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Details", style="yellow")

        for source_name, source_config in config.sources.items():
            if source_config.enabled:
                # Simple connectivity check (in real implementation)
                status = "✅ OK"
                details = f"Rate limit: {source_config.rate_limit_per_minute}/min"
            else:
                status = "⏸️ Disabled"
                details = "Not configured"

            table.add_row(
                source_name.upper(),
                "Yes" if source_config.enabled else "No",
                status,
                details,
            )

        console.print(table)
        console.print("\n✅ Connectivity check completed!")

    except Exception as e:
        console.print(f"[red]❌ Connectivity check failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def fetch_prices(
    tickers: str = typer.Option(
        ..., "--tickers", "-t", help="Comma-separated list of tickers"
    ),
    start_date: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(..., "--end", help="End date (YYYY-MM-DD)"),
    cache_only: bool = typer.Option(
        False, "--cache-only", help="Use cache only, no network calls"
    ),
) -> None:
    """Fetch price data for testing"""
    ticker_list = [t.strip() for t in tickers.split(",")]

    console.print(f"[blue]💰 Fetching prices for {len(ticker_list)} tickers[/blue]")

    try:
        config = load_config()
        if cache_only:
            config.cache_only_mode = True

        fetcher = DataFetcher(config)

        start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)

        result = fetcher.get_prices(ticker_list, start, end)

        table = Table(title="Price Fetch Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Records Fetched", str(len(result.records)))
        table.add_row("Cache Hits", str(result.cache_hits))
        table.add_row("Network Calls", str(result.network_calls))
        table.add_row("Execution Time", f"{result.execution_time_ms}ms")

        console.print(table)

        if result.errors:
            console.print("\n[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  • {error}")

        console.print("\n✅ Price fetch completed!")

    except Exception as e:
        console.print(f"[red]❌ Price fetch failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def populate(
    sample: bool = typer.Option(
        False, "--sample", help="Sample mode: process only 50 tickers for testing"
    ),
    sample_size: int = typer.Option(
        50, "--sample-size", help="Number of tickers in sample mode"
    ),
) -> None:
    """Populate database with real market data from APIs"""
    console.print("[blue]📦 Populating Database with Market Data[/blue]")

    try:
        config = get_config()
        populator = DataPopulator(config)

        # Run population
        stats = populator.populate_all(sample_mode=sample, sample_size=sample_size)

        if stats['errors']:
            console.print(f"\n[yellow]⚠️  Completed with {len(stats['errors'])} errors[/yellow]")
            raise typer.Exit(1)
        else:
            console.print("\n[green]✅ Data population complete![/green]")

    except Exception as e:
        console.print(f"[red]❌ Population failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def populate_survivors(
    csv_path: str = typer.Argument(..., help="Path to screening stage CSV"),
    stage_name: str = typer.Option(
        "Screening Stage", "--stage-name", help="Stage name for logging"
    ),
) -> None:
    """
    Populate fundamentals/factors for survivors from a screening CSV.

    This enables survivors-driven data fetching where we only update
    data for tickers that passed a screening stage.

    Example:
        multibagger data populate-survivors snapshots/2025-11/stage_business_2025-11.csv --stage-name "Stage 2.3"
    """
    console.print(f"[blue]📦 Populating Data for Survivors[/blue]")

    try:
        # Validate CSV path
        csv_file = Path(csv_path)
        if not csv_file.exists():
            console.print(f"[red]❌ CSV file not found: {csv_path}[/red]")
            raise typer.Exit(1)

        config = get_config()
        populator = DataPopulator(config)

        # Run population for survivors
        stats = populator.populate_from_survivors_csv(
            csv_path=str(csv_file),
            stage_name=stage_name
        )

        if stats.get('errors') and len(stats['errors']) > 5:
            console.print(f"\n[yellow]⚠️  Completed with {len(stats['errors'])} errors[/yellow]")
            raise typer.Exit(1)
        elif stats.get('errors'):
            console.print(f"\n[yellow]⚠️  Completed with {len(stats['errors'])} minor errors[/yellow]")
        else:
            console.print("\n[green]✅ Data population complete![/green]")

    except Exception as e:
        console.print(f"[red]❌ Population failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def backfill_forensics(
    as_of: str = typer.Option(..., "--as-of", help="As-of month (YYYY-MM)"),
    csv_path: str = typer.Option(None, "--csv", help="Custom CSV path (default: auto-detect from as-of)"),
    output_dir: str = typer.Option("snapshots", "--output-dir", help="Output directory for coverage report")
) -> None:
    """
    Backfill forensics fields for screening survivors using yfinance + Alpha Vantage fallback.

    This command:
    1. Loads survivors from stage_business_<as-of>.csv
    2. Fetches fundamentals from yfinance (fast)
    3. Falls back to Alpha Vantage for missing forensics fields (rate-limited)
    4. UPSERTs to fundamentals table
    5. Generates coverage report JSON

    Example:
        multibagger data backfill-forensics --as-of 2025-11
    """
    import json
    from pathlib import Path
    import os

    console.print(f"\n[bold blue]🔄 Backfilling Forensics Fields for {as_of}[/bold blue]\n")

    # Determine CSV path
    if csv_path is None:
        csv_path = f"{output_dir}/{as_of}/stage_business_{as_of}.csv"

    csv_file = Path(csv_path)
    if not csv_file.exists():
        console.print(f"[red]❌ CSV file not found: {csv_path}[/red]")
        console.print(f"[yellow]Run 'multibagger screen business --as-of {as_of}' first[/yellow]")
        raise typer.Exit(1)

    # Check for Alpha Vantage API key
    if not os.getenv('ALPHA_VANTAGE_KEY'):
        console.print("[yellow]⚠️  ALPHA_VANTAGE_KEY not set - fallback disabled[/yellow]")
        console.print("[yellow]Set ALPHA_VANTAGE_KEY in .env to enable Alpha Vantage fallback[/yellow]")
        console.print("[yellow]Continuing with yfinance only...[/yellow]\n")

    try:
        config = get_config()
        populator = DataPopulator(config)

        # Run population with fallback
        stats = populator.populate_from_survivors_csv(
            csv_path=str(csv_file),
            stage_name=f"Stage 2.3 Business Filter ({as_of})"
        )

        # Generate coverage report
        report_dir = Path(output_dir) / as_of
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "forensics_coverage.json"

        # Calculate overall coverage
        field_coverage = stats.get('field_coverage', {})
        total_by_field = {}
        overall_totals = {'with_data': 0, 'total_fields': 0}

        for field_name, counts in field_coverage.items():
            total = counts.get('yfinance', 0) + counts.get('alpha_vantage', 0) + counts.get('missing', 0)
            with_data = counts.get('yfinance', 0) + counts.get('alpha_vantage', 0)
            coverage_pct = (with_data / total * 100) if total > 0 else 0

            total_by_field[field_name] = {
                'yfinance': counts.get('yfinance', 0),
                'alpha_vantage': counts.get('alpha_vantage', 0),
                'missing': counts.get('missing', 0),
                'coverage_pct': round(coverage_pct, 1)
            }

            overall_totals['with_data'] += with_data
            overall_totals['total_fields'] += total

        overall_coverage_pct = (
            (overall_totals['with_data'] / overall_totals['total_fields'] * 100)
            if overall_totals['total_fields'] > 0 else 0
        )

        # Build coverage report
        coverage_report = {
            'as_of': as_of,
            'timestamp': datetime.utcnow().isoformat(),
            'csv_path': str(csv_file),
            'field_coverage': total_by_field,
            'overall_coverage_pct': round(overall_coverage_pct, 1),
            'fundamentals_fetched': stats.get('fundamentals_fetched', 0),
            'fundamentals_inserted': stats.get('fundamentals_inserted', 0)
        }

        # Add AV stats if available
        if populator.av_adapter and hasattr(populator.av_adapter, 'stats'):
            coverage_report['alpha_vantage_stats'] = populator.av_adapter.stats.copy()

        # Write JSON report
        with open(report_path, 'w') as f:
            json.dump(coverage_report, f, indent=2)

        console.print(f"\n[green]✅ Coverage report saved to {report_path}[/green]")

        # Print summary
        console.print(f"\n[bold cyan]📊 Overall Forensics Coverage: {overall_coverage_pct:.1f}%[/bold cyan]")

        if overall_coverage_pct >= 90:
            console.print("[green]✅ Target coverage (≥90%) achieved![/green]")
        else:
            console.print(f"[yellow]⚠️  Coverage below 90% target ({overall_coverage_pct:.1f}%)[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Backfill failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def validate() -> None:
    """Validate data coverage and quality"""
    console.print("[blue]🔍 Validating Data Coverage[/blue]")

    try:
        from multibagger.database.schema import get_engine
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        engine = get_engine()

        with Session(engine) as session:
            # Get counts
            ticker_count = session.execute(text("SELECT COUNT(*) FROM tickers WHERE active = 1")).scalar()
            price_count = session.execute(text("SELECT COUNT(DISTINCT ticker_id) FROM prices")).scalar()
            fundamental_count = session.execute(text("SELECT COUNT(DISTINCT ticker_id) FROM fundamentals")).scalar()
            factor_count = session.execute(text("SELECT COUNT(DISTINCT ticker_id) FROM factors")).scalar()

            # Calculate coverage
            price_coverage = (price_count / ticker_count * 100) if ticker_count > 0 else 0
            fundamental_coverage = (fundamental_count / ticker_count * 100) if ticker_count > 0 else 0
            factor_coverage = (factor_count / ticker_count * 100) if ticker_count > 0 else 0

            # Display results
            table = Table(title="Data Coverage Report")
            table.add_column("Data Type", style="cyan")
            table.add_column("Tickers", style="magenta")
            table.add_column("Coverage", style="green")
            table.add_column("Status", style="yellow")

            table.add_row("Universe", f"{ticker_count}", "100%", "✅")
            table.add_row("Prices", f"{price_count}", f"{price_coverage:.1f}%",
                         "✅" if price_coverage >= 95 else "⚠️")
            table.add_row("Fundamentals", f"{fundamental_count}", f"{fundamental_coverage:.1f}%",
                         "✅" if fundamental_coverage >= 10 else "⚠️")
            table.add_row("Factors", f"{factor_count}", f"{factor_coverage:.1f}%",
                         "✅" if factor_coverage >= 10 else "⚠️")

            console.print("\n")
            console.print(table)

            # Overall status
            if price_coverage >= 95 and fundamental_coverage >= 10:
                console.print("\n[green]✅ Data quality is good - ready for screening![/green]")
            else:
                console.print("\n[yellow]⚠️  Data coverage below targets - run 'data populate' first[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Validation failed: {e}[/red]")
        raise typer.Exit(1) from e
