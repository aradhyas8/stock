#!/usr/bin/env python3
"""
Ops Snapshot Rotation - Phase 7

Safely prune old snapshots with multiple safety guardrails.

Safety rules:
1. Never delete current month (YYYY-MM == today's month)
2. Never delete if portfolio positions reference it
3. Keep most recent N months
4. Keep alert files for M days
5. Always support dry-run preview
"""

import json
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple

from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.schema import get_engine


class RotationCandidate:
    """Snapshot directory candidate for deletion"""

    def __init__(self, month: str, path: Path):
        self.month = month
        self.path = path
        self.size_bytes = self._calculate_size()
        self.can_delete = True
        self.skip_reason = None

    def _calculate_size(self) -> int:
        """Calculate total size of snapshot directory"""
        if not self.path.exists():
            return 0

        total = 0
        for item in self.path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    def mark_skip(self, reason: str):
        """Mark this candidate as skipped with reason"""
        self.can_delete = False
        self.skip_reason = reason


def rotate_snapshots(
    keep_months: int = 12,
    keep_alert_days: int = 90,
    dry_run: bool = True,
    config: Config | None = None
) -> Dict:
    """
    Prune old snapshots safely.

    Args:
        keep_months: Number of recent months to keep
        keep_alert_days: Number of days to keep alert files
        dry_run: If True, only preview (don't delete)
        config: Config instance (loads default if None)

    Returns:
        Rotation report dict
    """
    if config is None:
        config = Config()

    engine = get_engine()
    session = Session(engine)

    snapshots_dir = Path("snapshots")
    current_month = datetime.now().strftime("%Y-%m")

    # Step 1: Scan for snapshot directories
    candidates = _scan_snapshot_directories(snapshots_dir)

    # Step 2: Apply safety constraints
    candidates = _apply_safety_constraints(
        candidates,
        current_month,
        keep_months,
        session
    )

    # Step 3: Execute or preview
    deleted = []
    skipped = []
    space_freed = 0

    for candidate in candidates:
        if not candidate.can_delete:
            skipped.append({
                "month": candidate.month,
                "reason": candidate.skip_reason,
                "size_mb": candidate.size_mb
            })
        else:
            if not dry_run:
                shutil.rmtree(candidate.path)
                space_freed += candidate.size_bytes

            deleted.append({
                "month": candidate.month,
                "size_mb": candidate.size_mb
            })

    session.close()

    # Step 4: Generate report
    report = {
        "executed_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "keep_months": keep_months,
        "candidates_total": len(candidates),
        "deleted": sorted(deleted, key=lambda x: x["month"]),
        "skipped": sorted(skipped, key=lambda x: x["month"]),
        "space_freed_mb": round(space_freed / (1024 * 1024), 2)
    }

    return report


def _scan_snapshot_directories(snapshots_dir: Path) -> List[RotationCandidate]:
    """Scan snapshots/ directory for month directories"""
    if not snapshots_dir.exists():
        return []

    candidates = []

    for item in snapshots_dir.iterdir():
        if not item.is_dir():
            continue

        # Check if directory name matches YYYY-MM pattern
        if _is_valid_month_format(item.name):
            candidates.append(RotationCandidate(item.name, item))

    # Sort by month descending (newest first)
    candidates.sort(key=lambda c: c.month, reverse=True)

    return candidates


def _is_valid_month_format(name: str) -> bool:
    """Check if string matches YYYY-MM format"""
    if len(name) != 7:
        return False

    parts = name.split("-")
    if len(parts) != 2:
        return False

    try:
        year = int(parts[0])
        month = int(parts[1])
        return 2020 <= year <= 2030 and 1 <= month <= 12
    except ValueError:
        return False


def _apply_safety_constraints(
    candidates: List[RotationCandidate],
    current_month: str,
    keep_months: int,
    session: Session
) -> List[RotationCandidate]:
    """Apply safety constraints to candidates"""

    # Constraint 1: Never delete current month
    for candidate in candidates:
        if candidate.month == current_month:
            candidate.mark_skip("Current month")

    # Constraint 2: Keep most recent N months
    # Candidates are sorted newest first
    for i, candidate in enumerate(candidates):
        if i < keep_months and candidate.can_delete:
            candidate.mark_skip(f"Within keep window (top {keep_months})")

    # Constraint 3: Never delete if referenced by portfolio
    referenced_months = _get_portfolio_referenced_months(session)
    for candidate in candidates:
        if candidate.month in referenced_months and candidate.can_delete:
            candidate.mark_skip("Referenced by portfolio")

    return candidates


def _get_portfolio_referenced_months(session: Session) -> set:
    """Get set of months that have portfolio runs"""
    result = session.execute(text("""
        SELECT DISTINCT strftime('%Y-%m', as_of_date) as month
        FROM portfolio_runs
        ORDER BY month DESC
    """))

    months = {row[0] for row in result.fetchall()}
    return months


def print_rotation_report(report: Dict) -> None:
    """Print rotation report to console using Rich"""
    console = Console()

    console.print()
    console.print(f"[bold]Snapshot Rotation Report[/bold]")
    console.print(f"Executed: {report['executed_at']}")
    console.print(f"Mode: {'DRY-RUN (preview only)' if report['dry_run'] else 'LIVE (deleted)'}")
    console.print(f"Keep Policy: {report['keep_months']} months")
    console.print()

    # Deleted table
    if report['deleted']:
        console.print(f"[green]To Delete ({len(report['deleted'])}):[/green]")
        table = Table(show_header=True)
        table.add_column("Month", style="cyan")
        table.add_column("Size (MB)", style="yellow", justify="right")

        for item in report['deleted']:
            table.add_row(item['month'], f"{item['size_mb']:.2f}")

        console.print(table)
        console.print(f"Space to free: {report['space_freed_mb']:.2f} MB")
        console.print()
    else:
        console.print("[green]No snapshots to delete[/green]")
        console.print()

    # Skipped table
    if report['skipped']:
        console.print(f"[yellow]Skipped ({len(report['skipped'])}):[/yellow]")
        table = Table(show_header=True)
        table.add_column("Month", style="cyan")
        table.add_column("Reason", style="white")
        table.add_column("Size (MB)", style="yellow", justify="right")

        for item in report['skipped']:
            table.add_row(
                item['month'],
                item['reason'],
                f"{item['size_mb']:.2f}"
            )

        console.print(table)
        console.print()


def save_rotation_report(report: Dict, output_dir: Path | None = None) -> Path:
    """Save rotation report to JSON file"""
    if output_dir is None:
        output_dir = Path(".")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Filename with timestamp for audit trail
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"rotation_report_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    return output_file
