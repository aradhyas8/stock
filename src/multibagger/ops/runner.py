#!/usr/bin/env python3
"""
Ops Runners - Phase 7

Orchestrate monthly and daily operations.

Monthly: Full pipeline (universe → screens → research → portfolio)
Daily: Monitoring wrapper
"""

import json
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any

from rich.console import Console

from multibagger.config import Config
from .health import check_system_health, print_health_report, save_health_report


def run_monthly(as_of: str, dry_run: bool = False, config: Config | None = None) -> Dict:
    """
    Orchestrate full monthly pipeline.

    Steps:
    1. Run universe build (if needed)
    2. Run all screen stages (fast → quality → business → redflags → research)
    3. Run portfolio reconciliation
    4. Generate health check
    5. Emit ops_monthly_metrics.json

    Args:
        as_of: Month to run (YYYY-MM)
        dry_run: If True, preview only (no actual execution)
        config: Config instance

    Returns:
        Monthly metrics dict
    """
    if config is None:
        config = Config()

    console = Console()
    console.print()
    console.print(f"[bold cyan]Monthly Runner - {as_of}[/bold cyan]")
    console.print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    console.print()

    start_time = datetime.now()
    stages = []

    try:
        # Step 1: Universe (skip if already exists)
        console.print("[yellow]Step 1/5:[/yellow] Checking universe...")
        universe_exists = _check_universe_exists()
        if not universe_exists:
            if not dry_run:
                _run_command(["python", "-m", "multibagger.cli.main", "universe", "build"])
            stages.append({"name": "universe", "status": "run" if not dry_run else "skipped (dry-run)"})
        else:
            stages.append({"name": "universe", "status": "exists (skipped)"})
        console.print("[green]✓[/green] Universe ready")
        console.print()

        # Step 2: Screen stages
        console.print("[yellow]Step 2/5:[/yellow] Running screening pipeline...")
        screen_stages = ["fast", "quality", "business", "redflags", "research"]
        for stage in screen_stages:
            if not dry_run:
                _run_command([
                    "python", "-m", "multibagger.cli.main",
                    "screen", stage, "--as-of", as_of
                ])
            stages.append({"name": f"screen_{stage}", "status": "completed" if not dry_run else "skipped (dry-run)"})
            console.print(f"[green]✓[/green] {stage}")

        console.print("[green]✓[/green] All screens completed")
        console.print()

        # Step 3: Portfolio reconciliation
        console.print("[yellow]Step 3/5:[/yellow] Running portfolio reconciliation...")
        if not dry_run:
            _run_command([
                "python", "-m", "multibagger.cli.main",
                "portfolio", "reconcile", "--as-of", as_of
            ])
        stages.append({"name": "portfolio_reconcile", "status": "completed" if not dry_run else "skipped (dry-run)"})
        console.print("[green]✓[/green] Portfolio reconciliation completed")
        console.print()

        # Step 4: Health check
        console.print("[yellow]Step 4/5:[/yellow] Running health check...")
        overall_status, checks = check_system_health(as_of=as_of, config=config)
        print_health_report(overall_status, checks, as_of)

        if not dry_run:
            save_health_report(overall_status, checks, as_of)

        stages.append({"name": "health_check", "status": overall_status})
        console.print()

        # Step 5: Generate metrics
        console.print("[yellow]Step 5/5:[/yellow] Generating metrics...")
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()

        metrics = {
            "as_of": as_of,
            "executed_at": end_time.isoformat(),
            "dry_run": dry_run,
            "duration_seconds": round(duration_seconds, 2),
            "stages": stages,
            "health_status": overall_status,
            "health_checks_passed": sum(1 for c in checks if c.status == "GREEN"),
            "health_checks_total": len(checks)
        }

        # Save metrics
        if not dry_run:
            snapshot_dir = Path("snapshots") / as_of
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            metrics_file = snapshot_dir / "ops_monthly_metrics.json"

            with open(metrics_file, "w") as f:
                json.dump(metrics, f, indent=2, sort_keys=True)

            console.print(f"[green]✓[/green] Metrics saved: {metrics_file}")
        else:
            console.print("[yellow]⚠[/yellow] Metrics not saved (dry-run)")

        console.print()
        console.print(f"[bold green]Monthly run completed in {duration_seconds:.1f}s[/bold green]")
        console.print()

        return metrics

    except Exception as e:
        console.print(f"[bold red]Error during monthly run:[/bold red] {e}")
        raise


def run_daily(
    check_date: date | None = None,
    as_of: str | None = None,
    dry_run: bool = False,
    config: Config | None = None
) -> Dict:
    """
    Orchestrate daily monitoring.

    Steps:
    1. Call existing `monitor daily`
    2. Validate outputs
    3. Emit ops_daily_metrics.json

    Args:
        check_date: Date to check (defaults to today)
        as_of: Portfolio month (defaults to latest)
        dry_run: If True, preview only
        config: Config instance

    Returns:
        Daily metrics dict
    """
    if config is None:
        config = Config()

    if check_date is None:
        check_date = date.today()

    console = Console()
    console.print()
    console.print(f"[bold cyan]Daily Runner - {check_date}[/bold cyan]")
    console.print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    console.print()

    start_time = datetime.now()

    try:
        # Step 1: Run monitor daily
        console.print("[yellow]Step 1/2:[/yellow] Running daily monitor...")

        cmd = ["python", "-m", "multibagger.cli.main", "monitor", "daily", "--date", str(check_date)]
        if as_of:
            cmd.extend(["--as-of", as_of])
        if dry_run:
            cmd.append("--dry-run")

        if not dry_run:
            _run_command(cmd)

        console.print("[green]✓[/green] Daily monitor completed")
        console.print()

        # Step 2: Generate metrics
        console.print("[yellow]Step 2/2:[/yellow] Generating metrics...")
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()

        metrics = {
            "check_date": str(check_date),
            "as_of": as_of or "latest",
            "executed_at": end_time.isoformat(),
            "dry_run": dry_run,
            "duration_seconds": round(duration_seconds, 2),
            "monitor_status": "completed" if not dry_run else "skipped (dry-run)"
        }

        # Save metrics
        if not dry_run and as_of:
            alert_dir = Path("snapshots") / as_of / "alerts"
            alert_dir.mkdir(parents=True, exist_ok=True)

            date_str = check_date.strftime("%Y-%m-%d")
            metrics_file = alert_dir / f"ops_daily_metrics_{date_str}.json"

            with open(metrics_file, "w") as f:
                json.dump(metrics, f, indent=2, sort_keys=True)

            console.print(f"[green]✓[/green] Metrics saved: {metrics_file}")
        else:
            console.print("[yellow]⚠[/yellow] Metrics not saved (dry-run or no as_of)")

        console.print()
        console.print(f"[bold green]Daily run completed in {duration_seconds:.1f}s[/bold green]")
        console.print()

        return metrics

    except Exception as e:
        console.print(f"[bold red]Error during daily run:[/bold red] {e}")
        raise


def _check_universe_exists() -> bool:
    """Check if universe data exists in database"""
    from multibagger.database.schema import get_engine
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    engine = get_engine()
    with Session(engine) as session:
        result = session.execute(text("SELECT COUNT(*) FROM tickers WHERE active = 1"))
        count = result.scalar()
        return count > 1000  # Threshold for "universe exists"


def _run_command(cmd: list) -> None:
    """Run external command and raise on failure"""
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Command failed with code {result.returncode}")
