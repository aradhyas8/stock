"""Common utilities for screening stages"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ScreenResult:
    """Result of a screening stage"""

    survivors: pd.DataFrame
    removed_by_rule: dict[str, int]
    total_input: int
    total_survivors: int
    runtime_seconds: float
    stage_name: str


def apply_rules_with_tracking(
    df: pd.DataFrame,
    rules: list[tuple[str, callable]],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Apply rules sequentially, tracking first failure per ticker.

    Args:
        df: Input DataFrame with tickers
        rules: List of (rule_name, rule_function) tuples
        config: Configuration dict with thresholds

    Returns:
        Tuple of (survivors_df, removed_counts_dict)
    """
    removed_by_rule = {}
    current_df = df.copy()
    current_df["failure_reason"] = None

    for rule_name, rule_func in rules:
        # Apply rule
        mask = rule_func(current_df, config)

        # Track failures for this rule
        failed = current_df[~mask & current_df["failure_reason"].isna()]
        removed_count = len(failed)

        if removed_count > 0:
            # Record first failure reason
            current_df.loc[failed.index, "failure_reason"] = rule_name
            removed_by_rule[rule_name] = removed_count

        logger.info(f"Rule '{rule_name}': removed {removed_count}, survivors {mask.sum()}")

    # Final survivors are those with no failure reason
    survivors = current_df[current_df["failure_reason"].isna()].copy()
    survivors = survivors.drop(columns=["failure_reason"])

    return survivors, removed_by_rule


def print_stage_summary(result: ScreenResult) -> None:
    """Print screening stage summary table"""

    # Main results table
    table = Table(title=f"{result.stage_name} Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Input Count", f"{result.total_input:,}")
    table.add_row("Survivors", f"{result.total_survivors:,}")
    table.add_row(
        "Survival Rate", f"{result.total_survivors / result.total_input * 100:.1f}%"
    )
    table.add_row("Runtime", f"{result.runtime_seconds:.2f}s")

    console.print(table)

    # Removed by rule table
    if result.removed_by_rule:
        removed_table = Table(title="Removed by Rule")
        removed_table.add_column("Rule", style="yellow")
        removed_table.add_column("Count", style="red")

        for rule, count in sorted(
            result.removed_by_rule.items(), key=lambda x: x[1], reverse=True
        ):
            removed_table.add_row(rule, f"{count:,}")

        console.print(removed_table)


def save_stage_output(
    df: pd.DataFrame,
    stage_name: str,
    as_of: str,
    output_dir: str | Path,
) -> Path:
    """
    Save stage output to CSV.

    Args:
        df: Survivors DataFrame
        stage_name: Name of stage (e.g., "fast", "quality")
        as_of: YYYY-MM date string
        output_dir: Output directory path

    Returns:
        Path to saved CSV
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"stage_{stage_name}_{as_of}.csv"
    filepath = output_path / filename

    df.to_csv(filepath, index=False)
    logger.info(f"Saved {len(df)} survivors to {filepath}")

    return filepath


def compute_avg_volume_window(
    prices_df: pd.DataFrame,
    window_days: int = 30,
    as_of_date: datetime | None = None,
) -> pd.DataFrame:
    """
    Compute average volume over window using SQL-like group aggregation.

    Args:
        prices_df: DataFrame with columns [ticker_id, date, volume]
        window_days: Number of days for average
        as_of_date: Only consider prices before this date

    Returns:
        DataFrame with [ticker_id, avg_volume, last_close, last_date]
    """
    df = prices_df.copy()

    # Filter by as_of date
    if as_of_date:
        df = df[df["date"] <= as_of_date]

    # Sort by ticker and date
    df = df.sort_values(["ticker_id", "date"])

    # Get last N days per ticker
    df["row_num"] = df.groupby("ticker_id").cumcount(ascending=False)
    window_df = df[df["row_num"] < window_days]

    # Aggregate
    agg_df = (
        window_df.groupby("ticker_id")
        .agg(
            avg_volume=("volume", "mean"),
            last_close=("adj_close", "last"),
            last_date=("date", "last"),
            days_count=("date", "count"),
        )
        .reset_index()
    )

    return agg_df


def check_expected_range(
    count: int, expected_min: int, expected_max: int, stage_name: str
) -> None:
    """Warn if survivor count outside expected range"""
    if count < expected_min or count > expected_max:
        logger.warning(
            f"{stage_name}: Survivor count {count} outside expected range "
            f"[{expected_min}, {expected_max}]"
        )
        console.print(
            f"[yellow]⚠️  Warning: {stage_name} produced {count} survivors, "
            f"expected {expected_min}-{expected_max}[/yellow]"
        )
