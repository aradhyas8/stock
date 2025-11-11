"""Main CLI interface for Multi-Bagger Research System"""

import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from multibagger.config import get_config
from multibagger.data.cache import HttpCache
from multibagger.database.operations import (
    create_database_snapshot,
    get_database_info,
    initialize_database,
    verify_database,
)
from multibagger.universe.builder import UniverseBuilder

from .data import app as data_app

app = typer.Typer(
    name="multibagger",
    help="Multi-Bagger Research System - Systematic investment research pipeline",
    rich_markup_mode="rich",
)

# Add data subcommand
app.add_typer(data_app, name="data", help="Data fetching and caching management")

console = Console()


def create_snapshot_dir(base_dir: str) -> Path:
    """Create timestamped snapshot directory"""
    timestamp = datetime.datetime.now().strftime("%Y-%m")
    snapshot_dir = Path(base_dir) / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "reports").mkdir(exist_ok=True)
    (snapshot_dir / "logs").mkdir(exist_ok=True)
    return snapshot_dir


@app.command()
def monthly(
    output_dir: str = typer.Option(
        "snapshots", "--output-dir", "-o", help="Output directory for results"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate run without actual processing"
    ),
) -> None:
    """Execute monthly multi-bagger research pipeline"""

    console.print(
        Panel.fit(
            "[bold blue]Monthly Multi-Bagger Hunt[/bold blue]\n"
            "Systematic analysis of 5,000+ stocks to find multi-bagger candidates",
            border_style="blue",
        )
    )

    if dry_run:
        console.print(
            "[yellow]Running in DRY RUN mode - no actual processing[/yellow]\n"
        )

    # Create snapshot directory
    snapshot_dir = create_snapshot_dir(output_dir)
    console.print(f"📁 Results will be saved to: [bold]{snapshot_dir}[/bold]\n")

    # Placeholder pipeline steps
    steps = [
        ("Loading universe", "Building list of 5,000+ stocks"),
        ("Quick screening", "Applying basic filters (liquidity, size, price)"),
        ("Quality analysis", "Calculating financial quality metrics"),
        ("Business evaluation", "Assessing competitive advantages"),
        ("Red flag detection", "Checking for accounting irregularities"),
        ("Deep research", "Generating detailed investment reports"),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        for step, description in steps:
            task = progress.add_task(f"[blue]{step}[/blue]: {description}", total=None)

            # Simulate processing time
            import time

            time.sleep(1)

            progress.remove_task(task)
            console.print(f"✅ {step} complete")

    # Create placeholder result files
    candidates_file = snapshot_dir / "candidates.json"
    metrics_file = snapshot_dir / "metrics.json"

    candidates_file.write_text(
        '{"candidates": [], "timestamp": "' + datetime.datetime.now().isoformat() + '"}'
    )
    metrics_file.write_text(
        '{"pipeline_runtime": 60, "stocks_processed": 0, "reports_generated": 0}'
    )

    console.print("\n" + "=" * 50)
    console.print("[bold green]✅ Monthly Multi-Bagger Hunt Complete![/bold green]")
    console.print(f"📊 Results saved to: {snapshot_dir}")
    console.print("📋 Generated 0 research reports (placeholder)")
    console.print("🎯 Ready for Phase 1 development")


@app.command()
def monitor(
    action: str = typer.Argument("daily", help="Action: daily"),
    date: str = typer.Option(None, "--date", help="Price date (YYYY-MM-DD), defaults to latest"),
    as_of: str = typer.Option(None, "--as-of", help="Portfolio run (YYYY-MM), defaults to latest"),
    output_dir: str = typer.Option("snapshots", "--output-dir", "-o", help="Output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print alerts without writing files"),
) -> None:
    """Run portfolio monitoring checks"""
    console.print("[blue]🔍 Portfolio Monitoring[/blue]\n")

    if action != "daily":
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: daily")
        raise typer.Exit(1)

    try:
        from multibagger.monitor import run_daily_monitor

        config = get_config()

        # Run monitor
        results = run_daily_monitor(
            config=config,
            date_str=date,
            as_of=as_of,
            output_dir=output_dir,
            dry_run=dry_run
        )

        if results['status'] == 'no_positions':
            console.print(f"[yellow]⚠️  No positions found for monitoring[/yellow]")
            console.print(f"Portfolio as of: {results['as_of']}")
            raise typer.Exit(0)

        # Display summary
        console.print(f"[cyan]Portfolio as of:[/cyan] {results['as_of']}")
        console.print(f"[cyan]Price date:[/cyan] {results['price_date']}")
        console.print(f"[cyan]Positions checked:[/cyan] {results['positions_checked']}\n")

        # Display alerts table
        alerts_df = results['alerts']

        if not alerts_df.empty:
            # Group by signal
            signal_counts = alerts_df['signal'].value_counts()

            metrics_table = Table(title="Alert Summary")
            metrics_table.add_column("Signal", style="yellow")
            metrics_table.add_column("Count", justify="right", style="red")

            for signal in ['STOP_LOSS', 'THESIS_RISK', 'NEAR_TARGET']:
                if signal in signal_counts:
                    metrics_table.add_column = f"{signal}: {signal_counts[signal]}"
                    metrics_table.add_row(signal, str(signal_counts[signal]))

            console.print(metrics_table)
            console.print()

            # Display detailed alerts
            alerts_table = Table(title="Detailed Alerts", show_header=True)
            alerts_table.add_column("Symbol", style="cyan")
            alerts_table.add_column("Signal", style="yellow")
            alerts_table.add_column("Current", justify="right")
            alerts_table.add_column("Entry", justify="right")
            alerts_table.add_column("Target", justify="right")
            alerts_table.add_column("Weight %", justify="right")
            alerts_table.add_column("Reason", style="dim")

            for _, alert in alerts_df.head(20).iterrows():  # Show first 20
                alerts_table.add_row(
                    alert['symbol'],
                    alert['signal'],
                    f"${alert['current_price']:.2f}",
                    f"${alert['entry_price']:.2f}" if alert['entry_price'] else "-",
                    f"${alert['target_price']:.2f}" if alert['target_price'] else "-",
                    f"{alert['held_weight_pct']:.1f}",
                    alert['reason'][:50] + "..." if len(alert['reason']) > 50 else alert['reason']
                )

            console.print(alerts_table)

            if len(alerts_df) > 20:
                console.print(f"\n[dim]... and {len(alerts_df) - 20} more alerts[/dim]")

        else:
            console.print("[green]✅ No alerts - all positions within normal bounds[/green]")

        # Output files
        if not dry_run and results['output_paths']:
            console.print(f"\n[dim]Outputs:[/dim]")
            console.print(f"  Alerts CSV: {results['output_paths']['alerts_csv']}")
            console.print(f"  Metrics JSON: {results['output_paths']['metrics_json']}")
        elif dry_run:
            console.print("\n[yellow]DRY RUN: No files written[/yellow]")

        console.print(f"\n[green]✅ Monitoring complete[/green]")

    except FileNotFoundError as e:
        console.print(f"[red]❌ File not found: {e}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]❌ Monitoring failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1) from e


@app.command()
def universe(
    action: str = typer.Argument(..., help="Action: build, verify, info"),
    snapshot_dir: str = typer.Option(
        "snapshots", "--snapshot-dir", "-s", help="Snapshot directory"
    ),
    force_refresh: bool = typer.Option(
        False, "--force-refresh", "-f", help="Force refresh data sources"
    ),
) -> None:
    """Manage stock universe: build, verify, or get info"""
    console.print("[blue]🌍 Stock Universe Management[/blue]")

    try:
        # Load configuration
        main_config = get_config()
        # Use default database path for cache
        cache = HttpCache("data/multibagger.db")
        builder = UniverseBuilder(main_config, cache)

        if action == "build":
            console.print("Building universe from exchange data sources...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Building universe...", total=None)
                stats = builder.build_universe(force_refresh=force_refresh)
                progress.remove_task(task)

            # Display results
            table = Table(title="Universe Build Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Raw Entries", str(stats["total_raw_entries"]))
            table.add_row("Normalized", str(stats["normalized_entries"]))
            table.add_row("Eligible", str(stats["eligible_entries"]))
            table.add_row("Final Universe", str(stats["final_universe_size"]))

            console.print(table)

            # Save snapshot
            if stats["final_universe_size"] > 0:
                snapshot_path = builder.save_snapshot(snapshot_dir, stats)
                console.print(f"\n✅ Snapshot saved to: {snapshot_path}")

        elif action == "verify":
            console.print("Verifying universe integrity...")

            verification = builder.verify_universe()

            table = Table(title="Universe Verification")
            table.add_column("Check", style="cyan")
            table.add_column("Status", style="magenta")

            table.add_row("Total Tickers", str(verification["total_tickers"]))
            table.add_row("Active Tickers", str(verification["active_tickers"]))
            table.add_row("Exchanges", str(verification["exchanges"]))
            table.add_row("Sectors", str(verification["sectors"]))
            table.add_row(
                "Valid Symbols", "✅ Yes" if verification["is_valid"] else "❌ No"
            )

            console.print(table)

            if verification["exchange_breakdown"]:
                console.print("\n[blue]Exchange Breakdown:[/blue]")
                for exchange, count in verification["exchange_breakdown"].items():
                    console.print(f"  {exchange}: {count} tickers")

            if verification["invalid_symbols"]:
                console.print(
                    f"\n[red]Invalid Symbols ({len(verification['invalid_symbols'])}):[/red]"
                )
                for symbol in verification["invalid_symbols"][:5]:  # Show first 5
                    console.print(f"  • {symbol}")
                if len(verification["invalid_symbols"]) > 5:
                    console.print(
                        f"  ... and {len(verification['invalid_symbols']) - 5} more"
                    )

        elif action == "info":
            console.print("Universe information...")

            info = builder.get_universe_info()

            # Config info
            config_table = Table(title="Configuration")
            config_table.add_column("Setting", style="cyan")
            config_table.add_column("Value", style="green")

            config_table.add_row("Markets", ", ".join(info["config"]["markets"]))
            config_table.add_row(
                "Min Market Cap", f"${info['config']['min_market_cap']:,}"
            )
            config_table.add_row("Min Price", f"${info['config']['min_price']}")
            config_table.add_row(
                "Exclude OTC", "Yes" if info["config"]["exclude_otc"] else "No"
            )
            config_table.add_row(
                "Exclude ADRs", "Yes" if info["config"]["exclude_adrs"] else "No"
            )

            console.print(config_table)

            # Verification summary
            verification = info["verification"]
            summary_table = Table(title="Universe Summary")
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Count", style="magenta")

            summary_table.add_row("Total Tickers", str(verification["total_tickers"]))
            summary_table.add_row("Active Tickers", str(verification["active_tickers"]))
            summary_table.add_row("Exchanges", str(verification["exchanges"]))
            summary_table.add_row("Sectors", str(verification["sectors"]))

            console.print(summary_table)

        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            console.print("Available actions: build, verify, info")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]❌ Universe operation failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def screen(
    stage: str = typer.Argument(..., help="Stage: fast, quality, business, redflags, research, or all"),
    as_of: str = typer.Option(
        None, "--as-of", help="Run as-of YYYY-MM (defaults to current month)"
    ),
    output_dir: str = typer.Option(
        "snapshots", "--output-dir", "-o", help="Output directory"
    ),
) -> None:
    """Run screening pipeline stages"""
    console.print(f"[blue]🔬 Running {stage.upper()} Screen[/blue]")

    try:
        from multibagger.screens.fast import screen_fast
        from multibagger.screens.quality import screen_quality
        from multibagger.screens.business import screen_business
        from multibagger.screens.redflags import screen_redflags
        from multibagger.screens.research import screen_research

        config = get_config()

        if stage == "fast" or stage == "all":
            console.print("\n[cyan]Stage 2.1: Quick Screener[/cyan]")
            result = screen_fast(config, as_of=as_of, output_dir=output_dir)
            console.print(f"✅ {result.total_survivors:,} survivors (eliminated {result.total_input - result.total_survivors:,})")

        if stage == "quality" or stage == "all":
            console.print("\n[cyan]Stage 2.2: Quality Filter[/cyan]")
            result = screen_quality(config, as_of=as_of, output_dir=output_dir)
            console.print(f"✅ {result.total_survivors:,} survivors (eliminated {result.total_input - result.total_survivors:,})")

        if stage == "business" or stage == "all":
            console.print("\n[cyan]Stage 2.3: Business Filter[/cyan]")
            result = screen_business(config, as_of=as_of, output_dir=output_dir)
            console.print(f"✅ {result.total_survivors:,} survivors (eliminated {result.total_input - result.total_survivors:,})")

        if stage == "redflags" or stage == "all":
            console.print("\n[cyan]Stage 2.4: Red Flag Detection[/cyan]")
            result = screen_redflags(config, as_of=as_of, output_dir=output_dir)

            # Display detailed summary
            console.print(f"\n[bold]Red Flag Analysis Summary:[/bold]")
            console.print(f"  Input tickers: {result.total_input:,}")
            console.print(f"  Survivors: {result.total_survivors:,} ({result.total_survivors/result.total_input*100:.1f}%)")
            console.print(f"  Eliminated: {result.total_input - result.total_survivors:,}")
            console.print(f"  Runtime: {result.runtime_seconds:.2f}s")

            # Show elimination breakdown
            if result.removed_by_rule:
                console.print(f"\n[bold]Elimination Breakdown:[/bold]")
                for rule, count in result.removed_by_rule.items():
                    console.print(f"  {rule}: {count:,} tickers")

            console.print(f"\n✅ Red flag detection complete")

        if stage == "research" or stage == "all":
            console.print("\n[cyan]Stage 2.5: Research & Valuation[/cyan]")
            result = screen_research(config, as_of=as_of, output_dir=output_dir)
            console.print(f"\n✅ Generated {result.total_survivors} research reports")

        if stage not in ["fast", "quality", "business", "redflags", "research", "all"]:
            console.print(f"[red]Unknown stage: {stage}[/red]")
            console.print("Available stages: fast, quality, business, redflags, research, all")
            raise typer.Exit(1)

        console.print("\n[green]✅ Screening complete![/green]")

    except Exception as e:
        console.print(f"[red]❌ Screening failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def version() -> None:
    """Show version information"""
    from multibagger import __version__

    table = Table(show_header=False, box=None)
    table.add_row("[bold]Multi-Bagger Research System[/bold]")
    table.add_row(f"Version: {__version__}")
    table.add_row("Phase: Foundation/MVP (Phases 1-2)")
    table.add_row("Status: Development scaffold ready")

    console.print(table)


@app.command()
def status() -> None:
    """Show system status and configuration"""
    console.print("[blue]📊 System Status[/blue]")

    table = Table(title="Multi-Bagger Research System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Details", style="green")

    # Check configuration files
    config_status = "✅ Found" if Path("config.yml").exists() else "❌ Missing"
    env_status = "✅ Found" if Path(".env").exists() else "❌ Missing"
    db_status = (
        "✅ Found" if Path("data/multibagger.db").exists() else "❌ Not initialized"
    )

    table.add_row("Configuration", config_status, "config.yml")
    table.add_row("Environment", env_status, ".env file")
    table.add_row("Database", db_status, "SQLite database")
    table.add_row("Phase", "✅ Active", "Foundation/MVP")

    console.print(table)


# Database Management Commands
@app.command()
def db_init(
    db_path: str | None = typer.Option(None, "--db-path", help="Custom database path")
) -> None:
    """Initialize database with schema and initial data"""
    console.print("[blue]🔧 Initializing Database[/blue]")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating database schema...", total=None)

            result = initialize_database(db_path)

            progress.remove_task(task)

        # Display results
        table = Table(title="Database Initialization Results")
        table.add_column("Operation", style="cyan")
        table.add_column("Result", style="green")

        table.add_row(
            "Database Created",
            "✅ Yes" if result["database_created"] else "ℹ️ Already exists",
        )
        table.add_row("Migrations Applied", str(result["migrations_applied"]))
        table.add_row(
            "Initial Data Loaded",
            "✅ Yes" if result["initial_data_loaded"] else "ℹ️ Skipped",
        )
        table.add_row("Schema Version", result["schema_version"] or "None")
        table.add_row("Database Path", result["database_path"])

        console.print(table)
        console.print("\n✅ Database initialization complete!")

    except Exception as e:
        console.print(f"[red]❌ Database initialization failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def db_verify(
    db_path: str | None = typer.Option(None, "--db-path", help="Custom database path")
) -> None:
    """Verify database schema and integrity"""
    console.print("[blue]🔍 Verifying Database Schema[/blue]")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running schema verification...", total=None)

            result = verify_database(db_path)

            progress.remove_task(task)

        # Display results
        table = Table(title="Database Verification Results")
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="magenta")

        table.add_row(
            "Tables Exist", "✅ Pass" if result["tables_exist"] else "❌ Fail"
        )
        table.add_row(
            "Indexes Exist", "✅ Pass" if result["indexes_exist"] else "❌ Fail"
        )
        table.add_row(
            "Constraints Valid", "✅ Pass" if result["constraints_valid"] else "❌ Fail"
        )
        table.add_row(
            "Test Operations", "✅ Pass" if result["test_operations"] else "❌ Fail"
        )

        console.print(table)

        if result["issues"]:
            console.print("\n[red]Issues Found:[/red]")
            for issue in result["issues"]:
                console.print(f"  • {issue}")
            raise typer.Exit(1)
        else:
            console.print("\n✅ Database schema verification passed!")

    except Exception as e:
        console.print(f"[red]❌ Database verification failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def db_info(
    db_path: str | None = typer.Option(None, "--db-path", help="Custom database path")
) -> None:
    """Show detailed database information"""
    console.print("[blue]📋 Database Information[/blue]")

    try:
        info = get_database_info(db_path)

        # Basic info
        basic_table = Table(title="Database Overview")
        basic_table.add_column("Property", style="cyan")
        basic_table.add_column("Value", style="green")

        basic_table.add_row("Database Path", info["database_path"])
        basic_table.add_row(
            "Database Exists", "✅ Yes" if info["database_exists"] else "❌ No"
        )
        basic_table.add_row("Schema Version", info["schema_version"] or "None")
        basic_table.add_row("Applied Migrations", str(len(info["applied_migrations"])))

        console.print(basic_table)

        # Table counts
        if info["table_counts"]:
            counts_table = Table(title="Table Record Counts")
            counts_table.add_column("Table", style="cyan")
            counts_table.add_column("Records", style="magenta")

            for table, count in info["table_counts"].items():
                counts_table.add_row(table, str(count))

            console.print(counts_table)

        # Indexes
        if info["indexes"]:
            console.print(f"\n[blue]Indexes ({len(info['indexes'])}):[/blue]")
            for idx in sorted(info["indexes"])[:10]:  # Show first 10
                console.print(f"  • {idx}")
            if len(info["indexes"]) > 10:
                console.print(f"  ... and {len(info['indexes']) - 10} more")

    except Exception as e:
        console.print(f"[red]❌ Failed to get database info: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def db_snapshot(
    snapshot_dir: str | None = typer.Option(
        None, "--snapshot-dir", help="Custom snapshot directory"
    ),
    db_path: str | None = typer.Option(None, "--db-path", help="Custom database path"),
) -> None:
    """Create a monthly snapshot of the database"""
    console.print("[blue]📸 Creating Database Snapshot[/blue]")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Creating snapshot...", total=None)

            result = create_database_snapshot(snapshot_dir, db_path)

            progress.remove_task(task)

        # Display results
        table = Table(title="Snapshot Results")
        table.add_column("Operation", style="cyan")
        table.add_column("Result", style="green")

        table.add_row(
            "Snapshot Created", "✅ Yes" if result["snapshot_created"] else "❌ Failed"
        )
        table.add_row(
            "Database Copied", "✅ Yes" if result["database_copied"] else "❌ Failed"
        )
        table.add_row(
            "Run Recorded", "✅ Yes" if result["run_recorded"] else "❌ Failed"
        )
        table.add_row("Snapshot Path", result["snapshot_path"])
        table.add_row("Timestamp", result["timestamp"])

        console.print(table)
        console.print("\n✅ Database snapshot created successfully!")

    except Exception as e:
        console.print(f"[red]❌ Snapshot creation failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def portfolio(
    action: str = typer.Argument(..., help="Action: reconcile"),
    holdings_file: str = typer.Option(..., "--holdings", "-h", help="Path to holdings CSV/JSON file"),
    as_of: str = typer.Option(None, "--as-of", help="Run as-of YYYY-MM (defaults to current month)"),
    output_dir: str = typer.Option("snapshots", "--output-dir", "-o", help="Output directory"),
    top_n: int = typer.Option(15, "--top-n", help="Top N candidates from research"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without writing files"),
) -> None:
    """Portfolio reconciliation and rebalancing"""
    console.print("[blue]📊 Portfolio Reconciliation[/blue]")

    if action != "reconcile":
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: reconcile")
        raise typer.Exit(1)

    try:
        from multibagger.portfolio import (
            reconcile_portfolio,
            save_reconciliation_outputs,
            print_reconciliation_summary,
        )

        config = get_config()

        # Default as_of to current month
        if as_of is None:
            as_of = datetime.datetime.now().strftime("%Y-%m")

        console.print(f"\n[cyan]Reconciling portfolio as of {as_of}[/cyan]")
        console.print(f"Holdings file: {holdings_file}")
        console.print(f"Top N candidates: {top_n}\n")

        # Run reconciliation
        results = reconcile_portfolio(
            config=config,
            as_of=as_of,
            holdings_file=holdings_file,
            output_dir=output_dir,
            top_n=top_n
        )

        if results['status'] != 'success':
            console.print(f"[red]❌ Reconciliation failed: {results.get('reason', 'Unknown error')}[/red]")
            raise typer.Exit(1)

        # Save outputs (unless dry-run)
        if not dry_run:
            output_paths = save_reconciliation_outputs(results, as_of, output_dir)
        else:
            console.print("\n[yellow]DRY RUN: No files written[/yellow]")
            output_paths = {}

        # Print summary
        print_reconciliation_summary(results, output_paths)

    except FileNotFoundError as e:
        console.print(f"[red]❌ File not found: {e}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]❌ Portfolio reconciliation failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1) from e


@app.command(name="portfolio-show")
def portfolio_show(
    as_of: str = typer.Option(..., "--as-of", help="Show portfolio for YYYY-MM"),
) -> None:
    """Show saved portfolio reconciliation from database (no recompute)"""
    console.print(f"[blue]📊 Portfolio Report for {as_of}[/blue]\n")

    try:
        from datetime import datetime as dt
        from sqlalchemy import text
        from sqlalchemy.orm import Session
        from multibagger.database.schema import get_engine
        from multibagger.database.models import PortfolioRun, PortfolioPosition, PortfolioAction
        import json

        # Convert to date
        as_of_date = dt.strptime(f"{as_of}-01", "%Y-%m-%d").date()

        engine = get_engine()
        with Session(engine) as session:
            # Fetch run
            run = session.query(PortfolioRun).filter_by(as_of_date=as_of_date).first()

            if not run:
                console.print(f"[red]❌ No portfolio run found for {as_of}[/red]")
                console.print("Run 'portfolio reconcile' first to create a portfolio.")
                raise typer.Exit(1)

            # Parse metrics
            metrics = json.loads(run.metrics_json)

            # Display metrics
            metrics_table = Table(title=f"Portfolio Metrics - {as_of}", show_header=True)
            metrics_table.add_column("Metric", style="cyan")
            metrics_table.add_column("Value", style="green")

            metrics_table.add_row("Turnover", f"{metrics['turnover_pct']}%")
            metrics_table.add_row("Position Count", str(metrics['position_count']))

            for action, count in metrics['action_counts'].items():
                metrics_table.add_row(f"{action.title()} Actions", str(count))

            console.print(metrics_table)

            # Display config assumptions
            console.print(f"\n[dim]Config: max_positions={metrics['config_assumptions']['max_positions']}, "
                         f"max_weight={metrics['config_assumptions']['max_weight_pct']}%, "
                         f"min_weight={metrics['config_assumptions']['min_weight_pct']}%, "
                         f"drift_tolerance={metrics['config_assumptions']['drift_tolerance_pct']*100}%[/dim]\n")

            # Fetch positions
            positions = session.query(PortfolioPosition).filter_by(run_id=run.id).order_by(
                PortfolioPosition.weight_pct.desc()
            ).all()

            # Display positions
            positions_table = Table(title="Target Portfolio Positions", show_header=True)
            positions_table.add_column("Symbol", style="cyan")
            positions_table.add_column("Weight %", justify="right", style="green")
            positions_table.add_column("Entry Price", justify="right")
            positions_table.add_column("Target Price", justify="right")
            positions_table.add_column("Upside %", justify="right")
            positions_table.add_column("Conviction", justify="right")

            total_weight = 0.0
            for pos in positions:
                notes = json.loads(pos.notes_json) if pos.notes_json else {}
                symbol = notes.get('symbol', f"ID:{pos.ticker_id}")
                upside = notes.get('upside_pct', 0)
                total_weight += float(pos.weight_pct)

                positions_table.add_row(
                    symbol,
                    f"{pos.weight_pct:.2f}",
                    f"${pos.entry_price:.2f}" if pos.entry_price else "-",
                    f"${pos.target_price:.2f}" if pos.target_price else "-",
                    f"{upside:.1f}%" if upside else "-",
                    f"{pos.conviction_score:.0f}" if pos.conviction_score else "-"
                )

            console.print(positions_table)
            console.print(f"\n[dim]Total Weight: {total_weight:.2f}%[/dim]")

            # Fetch actions
            actions = session.query(PortfolioAction).filter_by(run_id=run.id).all()

            if actions:
                console.print("\n")
                actions_table = Table(title="Recommended Actions", show_header=True)
                actions_table.add_column("Action", style="yellow")
                actions_table.add_column("Symbol", style="cyan")
                actions_table.add_column("Reason", style="white")

                for action in actions:
                    details = json.loads(action.details_json) if action.details_json else {}
                    symbol = details.get('symbol', f"ID:{action.ticker_id}" if action.ticker_id else "CASH")
                    actions_table.add_row(
                        action.action,
                        symbol,
                        action.reason or "-"
                    )

                console.print(actions_table)

            console.print(f"\n[green]✅ Portfolio snapshot from database (run_id={run.id})[/green]")

    except Exception as e:
        console.print(f"[red]❌ Failed to fetch portfolio: {e}[/red]")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
