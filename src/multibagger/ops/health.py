#!/usr/bin/env python3
"""
Ops Health Checks - Phase 7

Validates system state across database, snapshots, and pipeline outputs.

Status levels:
- GREEN: All checks pass
- YELLOW: Non-critical issues (e.g., price slightly stale, research coverage 70-80%)
- RED: Critical issues (missing stages, no portfolio run, price >30 days old)
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Any

from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.schema import get_engine


class HealthStatus:
    """Health check status levels"""
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class HealthCheck:
    """Individual health check result"""

    def __init__(
        self,
        name: str,
        status: str,
        message: str,
        details: Dict[str, Any] | None = None
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details
        }


def check_system_health(
    as_of: str | None = None,
    check_date: date | None = None,
    config: Config | None = None
) -> Tuple[str, List[HealthCheck]]:
    """
    Run all health checks and return overall status + individual results.

    Args:
        as_of: Month to check (YYYY-MM). Defaults to current month.
        check_date: Date for price freshness check. Defaults to today.
        config: Config instance. Loads from default if None.

    Returns:
        (overall_status, list_of_health_checks)
        overall_status: GREEN/YELLOW/RED
    """
    if config is None:
        config = Config()

    if as_of is None:
        as_of = datetime.now().strftime("%Y-%m")

    if check_date is None:
        check_date = date.today()

    engine = get_engine()
    session = Session(engine)

    checks = []

    try:
        # 1. Universe size check
        checks.append(_check_universe_size(session, config))

        # 2. Stage outputs check
        checks.append(_check_stage_outputs(as_of))

        # 3. Stage counts check
        checks.append(_check_stage_counts(as_of))

        # 4. Research coverage check
        checks.append(_check_research_coverage(session, as_of, config))

        # 5. Red flag coverage check
        checks.append(_check_red_flag_coverage(session, as_of))

        # 6. Portfolio run check
        checks.append(_check_portfolio_run(session, as_of))

        # 7. Price freshness check
        checks.append(_check_price_freshness(session, check_date, config))

        # 8. Snapshot integrity check
        checks.append(_check_snapshot_integrity(as_of))

    finally:
        session.close()

    # Determine overall status
    overall_status = _compute_overall_status(checks)

    return overall_status, checks


def _check_universe_size(session: Session, config: Config) -> HealthCheck:
    """Check universe size (4500-5500 active tickers)"""
    ops_config = config.get("ops", {})
    health_config = ops_config.get("health", {})
    min_size = health_config.get("universe_size_min", 4500)
    max_size = health_config.get("universe_size_max", 5500)

    result = session.execute(text("""
        SELECT COUNT(*) FROM tickers WHERE active = 1
    """))
    count = result.scalar()

    if min_size <= count <= max_size:
        return HealthCheck(
            "Universe Size",
            HealthStatus.GREEN,
            f"Universe size: {count} (within range {min_size}-{max_size})",
            {"count": count, "min": min_size, "max": max_size}
        )
    elif count < min_size:
        return HealthCheck(
            "Universe Size",
            HealthStatus.RED,
            f"Universe size: {count} (below minimum {min_size})",
            {"count": count, "min": min_size, "max": max_size}
        )
    else:
        return HealthCheck(
            "Universe Size",
            HealthStatus.YELLOW,
            f"Universe size: {count} (above maximum {max_size})",
            {"count": count, "min": min_size, "max": max_size}
        )


def _check_stage_outputs(as_of: str) -> HealthCheck:
    """Check that all stage CSV files exist"""
    snapshot_dir = Path("snapshots") / as_of

    required_files = [
        "stage_fast.csv",
        "stage_quality.csv",
        "stage_business.csv",
        "stage_redflags.csv",
        "stage_research.csv"
    ]

    missing = []
    for filename in required_files:
        if not (snapshot_dir / filename).exists():
            missing.append(filename)

    if not missing:
        return HealthCheck(
            "Stage Outputs",
            HealthStatus.GREEN,
            f"All {len(required_files)} stage files present",
            {"required": required_files, "missing": []}
        )
    else:
        return HealthCheck(
            "Stage Outputs",
            HealthStatus.RED,
            f"Missing {len(missing)} stage file(s): {', '.join(missing)}",
            {"required": required_files, "missing": missing}
        )


def _check_stage_counts(as_of: str) -> HealthCheck:
    """Check stage CSV row counts are within expected ranges"""
    snapshot_dir = Path("snapshots") / as_of

    # Expected ranges (lenient for now)
    expected_ranges = {
        "stage_fast.csv": (400, 600),      # ~500 after fast filter
        "stage_quality.csv": (80, 120),    # ~100 after quality
        "stage_business.csv": (25, 35),    # ~30 after business
        "stage_redflags.csv": (12, 18),    # ~15 after red flags
        "stage_research.csv": (12, 18)     # ~15 with research
    }

    issues = []
    counts = {}

    for filename, (min_count, max_count) in expected_ranges.items():
        filepath = snapshot_dir / filename
        if not filepath.exists():
            continue  # Already caught by stage outputs check

        try:
            import csv
            with open(filepath) as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                row_count = sum(1 for _ in reader)

            counts[filename] = row_count

            if not (min_count <= row_count <= max_count):
                issues.append(f"{filename}: {row_count} (expected {min_count}-{max_count})")
        except Exception as e:
            issues.append(f"{filename}: error reading ({e})")

    if not issues:
        return HealthCheck(
            "Stage Counts",
            HealthStatus.GREEN,
            "All stage counts within expected ranges",
            {"counts": counts}
        )
    else:
        return HealthCheck(
            "Stage Counts",
            HealthStatus.YELLOW,
            f"{len(issues)} stage(s) outside expected range",
            {"counts": counts, "issues": issues}
        )


def _check_research_coverage(session: Session, as_of: str, config: Config) -> HealthCheck:
    """Check that 80%+ survivors have research data"""
    ops_config = config.get("ops", {})
    health_config = ops_config.get("health", {})
    min_coverage = health_config.get("research_coverage_min", 0.80)

    as_of_date = f"{as_of}-01"

    # Count survivors (passed red flags)
    result = session.execute(text("""
        SELECT COUNT(DISTINCT ticker_id)
        FROM risk_flags
        WHERE as_of_date = :as_of
          AND first_fail_reason IS NULL
    """), {"as_of": as_of_date})
    survivors = result.scalar() or 0

    # Count survivors with research
    result = session.execute(text("""
        SELECT COUNT(DISTINCT r.ticker_id)
        FROM research r
        JOIN risk_flags rf ON rf.ticker_id = r.ticker_id AND rf.as_of_date = r.as_of_date
        WHERE r.as_of_date = :as_of
          AND rf.first_fail_reason IS NULL
    """), {"as_of": as_of_date})
    with_research = result.scalar() or 0

    if survivors == 0:
        return HealthCheck(
            "Research Coverage",
            HealthStatus.RED,
            "No survivors found (no red flag data?)",
            {"survivors": 0, "with_research": 0, "coverage_pct": 0}
        )

    coverage = with_research / survivors
    coverage_pct = round(coverage * 100, 1)

    if coverage >= min_coverage:
        return HealthCheck(
            "Research Coverage",
            HealthStatus.GREEN,
            f"Research coverage: {coverage_pct}% ({with_research}/{survivors})",
            {"survivors": survivors, "with_research": with_research, "coverage_pct": coverage_pct}
        )
    elif coverage >= min_coverage - 0.10:  # Within 10% of target
        return HealthCheck(
            "Research Coverage",
            HealthStatus.YELLOW,
            f"Research coverage: {coverage_pct}% (below {min_coverage*100}%)",
            {"survivors": survivors, "with_research": with_research, "coverage_pct": coverage_pct}
        )
    else:
        return HealthCheck(
            "Research Coverage",
            HealthStatus.RED,
            f"Research coverage: {coverage_pct}% (critically low)",
            {"survivors": survivors, "with_research": with_research, "coverage_pct": coverage_pct}
        )


def _check_red_flag_coverage(session: Session, as_of: str) -> HealthCheck:
    """Check that all business survivors have red flag data"""
    as_of_date = f"{as_of}-01"

    # Count survivors from business stage CSV
    snapshot_dir = Path("snapshots") / as_of
    business_file = snapshot_dir / "stage_business.csv"

    if not business_file.exists():
        return HealthCheck(
            "Red Flag Coverage",
            HealthStatus.YELLOW,
            "Cannot check: stage_business.csv missing",
            {}
        )

    import csv
    with open(business_file) as f:
        reader = csv.DictReader(f)
        business_survivors = {int(row['ticker_id']) for row in reader}

    # Check red flag coverage in DB
    if not business_survivors:
        return HealthCheck(
            "Red Flag Coverage",
            HealthStatus.YELLOW,
            "No business survivors to check",
            {"business_count": 0, "flagged_count": 0}
        )

    result = session.execute(text("""
        SELECT COUNT(DISTINCT ticker_id)
        FROM risk_flags
        WHERE as_of_date = :as_of
          AND ticker_id IN :ticker_ids
    """), {"as_of": as_of_date, "ticker_ids": tuple(business_survivors)})
    flagged = result.scalar() or 0

    coverage = flagged / len(business_survivors)

    if coverage == 1.0:
        return HealthCheck(
            "Red Flag Coverage",
            HealthStatus.GREEN,
            f"Red flag coverage: 100% ({flagged}/{len(business_survivors)})",
            {"business_count": len(business_survivors), "flagged_count": flagged}
        )
    else:
        return HealthCheck(
            "Red Flag Coverage",
            HealthStatus.YELLOW,
            f"Red flag coverage: {coverage*100:.1f}% ({flagged}/{len(business_survivors)})",
            {"business_count": len(business_survivors), "flagged_count": flagged}
        )


def _check_portfolio_run(session: Session, as_of: str) -> HealthCheck:
    """Check that portfolio run exists for as_of month"""
    as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d").date()

    result = session.execute(text("""
        SELECT id, created_at
        FROM portfolio_runs
        WHERE as_of_date = :as_of
    """), {"as_of": as_of_date})
    row = result.fetchone()

    if row:
        run_id, created_at = row
        return HealthCheck(
            "Portfolio Run",
            HealthStatus.GREEN,
            f"Portfolio run exists (id={run_id})",
            {"run_id": run_id, "created_at": str(created_at)}
        )
    else:
        return HealthCheck(
            "Portfolio Run",
            HealthStatus.RED,
            f"No portfolio run found for {as_of}",
            {}
        )


def _check_price_freshness(session: Session, check_date: date, config: Config) -> HealthCheck:
    """Check that latest price is within acceptable staleness"""
    ops_config = config.get("ops", {})
    health_config = ops_config.get("health", {})
    warn_days = health_config.get("price_staleness_warn_days", 7)
    error_days = health_config.get("price_staleness_error_days", 30)

    result = session.execute(text("""
        SELECT MAX(date) as latest_date
        FROM prices
    """))
    row = result.fetchone()

    if not row or not row[0]:
        return HealthCheck(
            "Price Freshness",
            HealthStatus.RED,
            "No price data found in database",
            {}
        )

    latest_date_str = row[0]
    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").date()

    days_old = (check_date - latest_date).days

    if days_old <= warn_days:
        return HealthCheck(
            "Price Freshness",
            HealthStatus.GREEN,
            f"Latest price: {latest_date} ({days_old} days old)",
            {"latest_date": str(latest_date), "days_old": days_old}
        )
    elif days_old <= error_days:
        return HealthCheck(
            "Price Freshness",
            HealthStatus.YELLOW,
            f"Latest price: {latest_date} ({days_old} days old, warn threshold: {warn_days})",
            {"latest_date": str(latest_date), "days_old": days_old}
        )
    else:
        return HealthCheck(
            "Price Freshness",
            HealthStatus.RED,
            f"Latest price: {latest_date} ({days_old} days old, critically stale)",
            {"latest_date": str(latest_date), "days_old": days_old}
        )


def _check_snapshot_integrity(as_of: str) -> HealthCheck:
    """Check that snapshot directory and key files exist"""
    snapshot_dir = Path("snapshots") / as_of

    if not snapshot_dir.exists():
        return HealthCheck(
            "Snapshot Integrity",
            HealthStatus.RED,
            f"Snapshot directory missing: {snapshot_dir}",
            {}
        )

    # Check for key files
    required = ["stage_research.csv"]
    optional = ["portfolio_reconciliation.csv", "alerts/"]

    missing_required = [f for f in required if not (snapshot_dir / f).exists()]
    present_optional = [f for f in optional if (snapshot_dir / f).exists()]

    if not missing_required:
        return HealthCheck(
            "Snapshot Integrity",
            HealthStatus.GREEN,
            f"Snapshot directory intact ({len(present_optional)} optional files present)",
            {"present_optional": present_optional}
        )
    else:
        return HealthCheck(
            "Snapshot Integrity",
            HealthStatus.RED,
            f"Missing required files: {', '.join(missing_required)}",
            {"missing_required": missing_required}
        )


def _compute_overall_status(checks: List[HealthCheck]) -> str:
    """Compute overall status from individual checks"""
    if any(c.status == HealthStatus.RED for c in checks):
        return HealthStatus.RED
    elif any(c.status == HealthStatus.YELLOW for c in checks):
        return HealthStatus.YELLOW
    else:
        return HealthStatus.GREEN


def print_health_report(
    overall_status: str,
    checks: List[HealthCheck],
    as_of: str
) -> None:
    """Print health report to console using Rich"""
    console = Console()

    # Header
    status_color = {
        HealthStatus.GREEN: "green",
        HealthStatus.YELLOW: "yellow",
        HealthStatus.RED: "red"
    }[overall_status]

    console.print()
    console.print(f"[bold]System Health Check - {as_of}[/bold]")
    console.print(f"Overall Status: [{status_color}]●[/{status_color}] {overall_status}")
    console.print()

    # Table
    table = Table(show_header=True)
    table.add_column("Check", style="cyan", width=20)
    table.add_column("Status", width=10)
    table.add_column("Message", width=60)

    for check in checks:
        status_icon = {
            HealthStatus.GREEN: "[green]✓[/green]",
            HealthStatus.YELLOW: "[yellow]⚠[/yellow]",
            HealthStatus.RED: "[red]✗[/red]"
        }[check.status]

        table.add_row(
            check.name,
            status_icon,
            check.message
        )

    console.print(table)
    console.print()


def save_health_report(
    overall_status: str,
    checks: List[HealthCheck],
    as_of: str,
    output_dir: Path | None = None
) -> Path:
    """Save health report to JSON file"""
    if output_dir is None:
        output_dir = Path("snapshots") / as_of

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"health_check_{as_of}.json"

    report = {
        "as_of": as_of,
        "timestamp": datetime.now().isoformat(),
        "overall_status": overall_status,
        "checks": [c.to_dict() for c in checks]
    }

    # Sort keys for determinism
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    return output_file
