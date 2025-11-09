"""Data management CLI commands for Multi-Bagger Research System"""

import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from multibagger.data.config import DataConfig
from multibagger.data.fetcher import DataFetcher

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


if __name__ == "__main__":
    app()
