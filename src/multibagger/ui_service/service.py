#!/usr/bin/env python3
"""
UI Service Layer - Phase 7 Extension

Thin facade that wraps core operations and returns typed results.
No business logic here - just orchestration and result formatting.

All functions return dicts with standard keys:
- DataFrames for tables
- Dicts for metrics
- Paths for artifacts
- Warnings/errors lists
"""

import json
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple, Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.schema import get_engine
from multibagger.database.models import PortfolioRun, PortfolioPosition, PortfolioAction


def get_latest_snapshot() -> Dict:
    """
    Find the most recent snapshot directory.

    Returns:
        {
            "as_of": str (YYYY-MM) or None,
            "path": Path or None,
            "stage_files": list[str],
            "exists": bool
        }
    """
    snapshots_dir = Path("snapshots")

    if not snapshots_dir.exists():
        return {
            "as_of": None,
            "path": None,
            "stage_files": [],
            "exists": False
        }

    # Find all YYYY-MM directories
    month_dirs = []
    for item in snapshots_dir.iterdir():
        if item.is_dir() and len(item.name) == 7 and "-" in item.name:
            try:
                # Validate format
                year, month = item.name.split("-")
                if len(year) == 4 and len(month) == 2:
                    month_dirs.append(item.name)
            except:
                pass

    if not month_dirs:
        return {
            "as_of": None,
            "path": None,
            "stage_files": [],
            "exists": False
        }

    # Get latest
    latest = sorted(month_dirs)[-1]
    latest_path = snapshots_dir / latest

    # List stage files
    stage_files = []
    for pattern in ["stage_*.csv", "*.md", "*.json"]:
        stage_files.extend([f.name for f in latest_path.glob(pattern)])

    return {
        "as_of": latest,
        "path": latest_path,
        "stage_files": sorted(stage_files),
        "exists": True
    }


def get_health_summary(as_of: str) -> Dict:
    """
    Get quick health summary (without running full checks).

    Args:
        as_of: Month (YYYY-MM)

    Returns:
        {
            "status": str (GREEN/YELLOW/RED/UNKNOWN),
            "checks_run": bool,
            "report_path": Path or None,
            "metrics": dict
        }
    """
    snapshot_dir = Path("snapshots") / as_of
    health_file = snapshot_dir / f"health_check_{as_of}.json"

    if not health_file.exists():
        return {
            "status": "UNKNOWN",
            "checks_run": False,
            "report_path": None,
            "metrics": {}
        }

    with open(health_file) as f:
        health_data = json.load(f)

    return {
        "status": health_data.get("overall_status", "UNKNOWN"),
        "checks_run": True,
        "report_path": health_file,
        "metrics": health_data
    }


def list_stage_artifacts(as_of: str) -> List[Dict]:
    """
    List all stage artifacts for a given month.

    Args:
        as_of: Month (YYYY-MM)

    Returns:
        List of {
            "name": str,
            "path": Path,
            "size_bytes": int,
            "type": str (csv/json/md)
        }
    """
    snapshot_dir = Path("snapshots") / as_of

    if not snapshot_dir.exists():
        return []

    artifacts = []

    for filepath in snapshot_dir.rglob("*"):
        if filepath.is_file():
            artifacts.append({
                "name": filepath.relative_to(snapshot_dir).as_posix(),
                "path": filepath,
                "size_bytes": filepath.stat().st_size,
                "type": filepath.suffix[1:] if filepath.suffix else "unknown"
            })

    return sorted(artifacts, key=lambda x: x["name"])


def run_monthly(as_of: str, output_dir: str = "snapshots", dry_run: bool = False) -> Dict:
    """
    Run full monthly pipeline.

    Args:
        as_of: Month (YYYY-MM)
        output_dir: Output directory
        dry_run: Preview only

    Returns:
        {
            "success": bool,
            "metrics": dict,
            "artifacts": list[Path],
            "log": str,
            "warnings": list[str]
        }
    """
    from multibagger.ops.runner import run_monthly as core_run_monthly

    try:
        warnings = []

        # Run monthly orchestration
        metrics = core_run_monthly(as_of=as_of, dry_run=dry_run)

        # List generated artifacts
        artifacts = []
        snapshot_dir = Path(output_dir) / as_of
        if snapshot_dir.exists():
            artifacts = list(snapshot_dir.rglob("*.csv")) + list(snapshot_dir.rglob("*.json"))

        return {
            "success": True,
            "metrics": metrics,
            "artifacts": artifacts,
            "log": f"Monthly run completed for {as_of}",
            "warnings": warnings
        }

    except Exception as e:
        return {
            "success": False,
            "metrics": {},
            "artifacts": [],
            "log": str(e),
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def run_daily(check_date: date, as_of: str | None = None, dry_run: bool = False) -> Dict:
    """
    Run daily monitoring.

    Args:
        check_date: Date to check (YYYY-MM-DD)
        as_of: Portfolio month (defaults to latest)
        dry_run: Preview only

    Returns:
        {
            "success": bool,
            "metrics": dict,
            "artifacts": list[Path],
            "log": str,
            "warnings": list[str]
        }
    """
    from multibagger.ops.runner import run_daily as core_run_daily

    try:
        warnings = []

        # Run daily orchestration
        metrics = core_run_daily(check_date=check_date, as_of=as_of, dry_run=dry_run)

        # List generated artifacts
        artifacts = []
        if as_of:
            alert_dir = Path("snapshots") / as_of / "alerts"
            if alert_dir.exists():
                artifacts = list(alert_dir.glob("*.json")) + list(alert_dir.glob("*.csv"))

        return {
            "success": True,
            "metrics": metrics,
            "artifacts": artifacts,
            "log": f"Daily run completed for {check_date}",
            "warnings": warnings
        }

    except Exception as e:
        return {
            "success": False,
            "metrics": {},
            "artifacts": [],
            "log": str(e),
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def get_research_table(as_of: str, filters: Dict | None = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Get research stage results with filters.

    Args:
        as_of: Month (YYYY-MM)
        filters: {
            "min_upside_pct": float,
            "sector": str,
            "red_flags_passed_only": bool
        }

    Returns:
        (DataFrame, {"paths": dict, "warnings": list})
    """
    filters = filters or {}
    snapshot_dir = Path("snapshots") / as_of
    research_file = snapshot_dir / f"stage_research_{as_of}.csv"

    if not research_file.exists():
        return pd.DataFrame(), {
            "paths": {},
            "warnings": [f"Research file not found: {research_file}"]
        }

    try:
        df = pd.read_csv(research_file)

        # Apply filters
        if "min_upside_pct" in filters and filters["min_upside_pct"] is not None:
            df = df[df.get("upside_pct", 0) >= filters["min_upside_pct"]]

        if "sector" in filters and filters["sector"] and filters["sector"] != "All":
            df = df[df.get("sector", "") == filters["sector"]]

        if filters.get("red_flags_passed_only", False):
            # Check if red_flags column exists
            if "red_flags" in df.columns:
                df = df[df["red_flags"] == 0]

        return df, {
            "paths": {"csv": research_file},
            "warnings": []
        }

    except Exception as e:
        return pd.DataFrame(), {
            "paths": {},
            "warnings": [f"Error loading research: {type(e).__name__}: {e}"]
        }


def reconcile_portfolio(
    as_of: str,
    holdings_file_path: str,
    persist: bool = False,
    top_n: int = 15
) -> Dict:
    """
    Reconcile portfolio holdings vs model recommendations.

    Args:
        as_of: Month (YYYY-MM)
        holdings_file_path: Path to holdings CSV/JSON
        persist: Save to database
        top_n: Number of top candidates

    Returns:
        {
            "actions_df": DataFrame,
            "reconcile_df": DataFrame,
            "unmatched_df": DataFrame,
            "metrics": dict,
            "output_paths": dict,
            "warnings": list
        }
    """
    try:
        # Use CLI to run reconciliation
        cmd = [
            sys.executable, "-m", "multibagger.cli.main",
            "portfolio", "reconcile",
            "--holdings", holdings_file_path,
            "--as-of", as_of,
            "--top-n", str(top_n)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return {
                "actions_df": pd.DataFrame(),
                "reconcile_df": pd.DataFrame(),
                "unmatched_df": pd.DataFrame(),
                "metrics": {},
                "output_paths": {},
                "warnings": [f"Reconciliation failed: {result.stderr}"]
            }

        # Load results
        snapshot_dir = Path("snapshots") / as_of
        reconcile_file = snapshot_dir / f"portfolio_reconciliation_{as_of}.csv"
        actions_file = snapshot_dir / f"portfolio_actions_{as_of}.csv"

        reconcile_df = pd.read_csv(reconcile_file) if reconcile_file.exists() else pd.DataFrame()
        actions_df = pd.read_csv(actions_file) if actions_file.exists() else pd.DataFrame()

        return {
            "actions_df": actions_df,
            "reconcile_df": reconcile_df,
            "unmatched_df": pd.DataFrame(),  # TODO: Extract from reconcile output
            "metrics": {},
            "output_paths": {
                "reconcile": reconcile_file,
                "actions": actions_file
            },
            "warnings": []
        }

    except Exception as e:
        return {
            "actions_df": pd.DataFrame(),
            "reconcile_df": pd.DataFrame(),
            "unmatched_df": pd.DataFrame(),
            "metrics": {},
            "output_paths": {},
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def portfolio_show(as_of: str) -> Dict:
    """
    Show saved portfolio from database.

    Args:
        as_of: Month (YYYY-MM)

    Returns:
        {
            "positions_df": DataFrame,
            "actions_df": DataFrame,
            "metrics": dict,
            "warnings": list
        }
    """
    try:
        engine = get_engine()
        session = Session(engine)

        as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d").date()

        # Get portfolio run
        run = session.query(PortfolioRun).filter_by(as_of_date=as_of_date).first()

        if not run:
            session.close()
            return {
                "positions_df": pd.DataFrame(),
                "actions_df": pd.DataFrame(),
                "metrics": {},
                "warnings": [f"No portfolio run found for {as_of}"]
            }

        # Get positions
        positions = session.query(PortfolioPosition).filter_by(run_id=run.id).all()
        positions_data = []
        for pos in positions:
            positions_data.append({
                "symbol": pos.ticker.symbol if pos.ticker else f"ID:{pos.ticker_id}",
                "weight_pct": float(pos.weight_pct),
                "entry_price": float(pos.entry_price) if pos.entry_price else None,
                "target_price": float(pos.target_price) if pos.target_price else None,
                "conviction_score": float(pos.conviction_score) if pos.conviction_score else None
            })

        positions_df = pd.DataFrame(positions_data)

        # Get actions
        actions = session.query(PortfolioAction).filter_by(run_id=run.id).all()
        actions_data = []
        for action in actions:
            details = json.loads(action.details_json) if action.details_json else {}
            actions_data.append({
                "action": action.action,
                "symbol": details.get("symbol", f"ID:{action.ticker_id}"),
                "reason": action.reason or ""
            })

        actions_df = pd.DataFrame(actions_data)

        # Get metrics
        metrics = json.loads(run.metrics_json) if run.metrics_json else {}

        session.close()

        return {
            "positions_df": positions_df,
            "actions_df": actions_df,
            "metrics": metrics,
            "warnings": []
        }

    except Exception as e:
        return {
            "positions_df": pd.DataFrame(),
            "actions_df": pd.DataFrame(),
            "metrics": {},
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def monitor_daily(check_date: date, as_of: str | None = None, dry_run: bool = False) -> Dict:
    """
    Run daily monitoring and return alerts.

    Args:
        check_date: Date to check
        as_of: Portfolio month (defaults to latest)
        dry_run: Preview only

    Returns:
        {
            "alerts_df": DataFrame,
            "metrics": dict,
            "output_paths": dict,
            "warnings": list
        }
    """
    try:
        # Use CLI to run monitoring
        cmd = [
            sys.executable, "-m", "multibagger.cli.main",
            "monitor", "daily",
            "--date", str(check_date)
        ]

        if as_of:
            cmd.extend(["--as-of", as_of])

        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return {
                "alerts_df": pd.DataFrame(),
                "metrics": {},
                "output_paths": {},
                "warnings": [f"Monitoring failed: {result.stderr}"]
            }

        # Load results
        if as_of:
            alert_dir = Path("snapshots") / as_of / "alerts"
            date_str = check_date.strftime("%Y-%m-%d")
            alerts_file = alert_dir / f"alerts_{date_str}.csv"

            if alerts_file.exists():
                alerts_df = pd.read_csv(alerts_file)
            else:
                alerts_df = pd.DataFrame()
        else:
            alerts_df = pd.DataFrame()

        return {
            "alerts_df": alerts_df,
            "metrics": {},
            "output_paths": {"alerts": alerts_file} if as_of else {},
            "warnings": []
        }

    except Exception as e:
        return {
            "alerts_df": pd.DataFrame(),
            "metrics": {},
            "output_paths": {},
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def analytics_compute(
    as_of: str,
    window: int = 36,
    bench_symbols: List[str] | None = None
) -> Dict:
    """
    Compute portfolio performance analytics.

    Args:
        as_of: End month (YYYY-MM)
        window: Lookback months
        bench_symbols: Benchmark symbols (default: ["SPY"])

    Returns:
        {
            "metrics_json": dict,
            "timeseries_df": DataFrame,
            "contrib_df": DataFrame,
            "outputs": dict,
            "warnings": list
        }
    """
    from multibagger.analytics import compute_analytics, generate_reports

    try:
        bench_symbols = bench_symbols or ["SPY"]

        # Compute analytics
        analytics = compute_analytics(as_of=as_of, window_months=window)

        if "error" in analytics:
            return {
                "metrics_json": analytics,
                "timeseries_df": pd.DataFrame(),
                "contrib_df": pd.DataFrame(),
                "outputs": {},
                "warnings": [analytics["error"]]
            }

        # Generate reports (don't save if dry-run, but we'll generate anyway)
        outputs = generate_reports(analytics)

        # Extract time series (placeholder - would need to be added to compute_analytics)
        timeseries_df = pd.DataFrame()

        # Extract contributions
        contrib_data = analytics.get("attribution", {})
        top_contrib = contrib_data.get("top_contributors", [])
        top_detract = contrib_data.get("top_detractors", [])

        contrib_df = pd.DataFrame(top_contrib + top_detract)

        return {
            "metrics_json": analytics,
            "timeseries_df": timeseries_df,
            "contrib_df": contrib_df,
            "outputs": outputs,
            "warnings": []
        }

    except Exception as e:
        return {
            "metrics_json": {},
            "timeseries_df": pd.DataFrame(),
            "contrib_df": pd.DataFrame(),
            "outputs": {},
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def ops_health(as_of: str) -> Dict:
    """
    Run system health checks.

    Args:
        as_of: Month (YYYY-MM)

    Returns:
        {
            "checks_df": DataFrame,
            "status": str (GREEN/YELLOW/RED),
            "metrics_json": dict,
            "report_path": Path,
            "warnings": list
        }
    """
    from multibagger.ops.health import check_system_health, save_health_report

    try:
        overall_status, checks = check_system_health(as_of=as_of)

        # Convert checks to DataFrame
        checks_data = []
        for check in checks:
            checks_data.append({
                "check": check.name,
                "status": check.status,
                "message": check.message
            })

        checks_df = pd.DataFrame(checks_data)

        # Save report
        report_path = save_health_report(overall_status, checks, as_of)

        # Load full metrics
        with open(report_path) as f:
            metrics_json = json.load(f)

        return {
            "checks_df": checks_df,
            "status": overall_status,
            "metrics_json": metrics_json,
            "report_path": report_path,
            "warnings": []
        }

    except Exception as e:
        return {
            "checks_df": pd.DataFrame(),
            "status": "ERROR",
            "metrics_json": {},
            "report_path": None,
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }


def ops_rotate(keep_months: int = 12, execute: bool = False) -> Dict:
    """
    Rotate (prune) old snapshots.

    Args:
        keep_months: Number of recent months to keep
        execute: Actually delete (default: dry-run)

    Returns:
        {
            "preview_df": DataFrame,
            "deleted_paths": list[Path],
            "bytes_freed": int,
            "warnings": list
        }
    """
    from multibagger.ops.rotation import rotate_snapshots

    try:
        dry_run = not execute

        report = rotate_snapshots(
            keep_months=keep_months,
            keep_alert_days=90,
            dry_run=dry_run
        )

        # Convert to DataFrame
        deleted_data = report.get("deleted", [])
        skipped_data = report.get("skipped", [])

        preview_data = []
        for item in deleted_data:
            preview_data.append({
                "month": item["month"],
                "size_mb": item["size_mb"],
                "action": "DELETED" if not dry_run else "TO DELETE"
            })

        for item in skipped_data:
            preview_data.append({
                "month": item["month"],
                "size_mb": item["size_mb"],
                "action": f"SKIPPED: {item['reason']}"
            })

        preview_df = pd.DataFrame(preview_data)

        return {
            "preview_df": preview_df,
            "deleted_paths": [Path("snapshots") / d["month"] for d in deleted_data],
            "bytes_freed": int(report.get("space_freed_mb", 0) * 1024 * 1024),
            "warnings": []
        }

    except Exception as e:
        return {
            "preview_df": pd.DataFrame(),
            "deleted_paths": [],
            "bytes_freed": 0,
            "warnings": [f"Error: {type(e).__name__}: {e}"]
        }
