"""Holdings file loader (CSV/JSON) with validation"""

import json
import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def load_holdings_csv(file_path: str) -> pd.DataFrame:
    """
    Load holdings from CSV file.

    Expected columns:
    - symbol (required)
    - exchange (optional)
    - quantity OR weight_pct (one required)
    - avg_cost (optional)
    - currency (optional)

    Args:
        file_path: Path to CSV file

    Returns:
        DataFrame with validated holdings

    Raises:
        ValueError: If required columns missing or data invalid
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Holdings file not found: {file_path}")

    df = pd.read_csv(file_path)

    # Validate required columns
    if 'symbol' not in df.columns:
        raise ValueError("Holdings CSV must have 'symbol' column")

    if 'quantity' not in df.columns and 'weight_pct' not in df.columns:
        raise ValueError("Holdings CSV must have either 'quantity' or 'weight_pct' column")

    # Add defaults for optional columns
    if 'exchange' not in df.columns:
        df['exchange'] = None

    if 'avg_cost' not in df.columns:
        df['avg_cost'] = None

    if 'currency' not in df.columns:
        df['currency'] = 'USD'  # Default assumption

    # Normalize: prefer quantity, fallback to weight_pct
    if 'quantity' in df.columns:
        df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
    else:
        df['quantity'] = None

    if 'weight_pct' in df.columns:
        df['weight_pct'] = pd.to_numeric(df['weight_pct'], errors='coerce')
    else:
        df['weight_pct'] = None

    # Drop rows with invalid data
    initial_count = len(df)
    df = df[df['symbol'].notna()]

    if len(df) < initial_count:
        logger.warning(f"Dropped {initial_count - len(df)} rows with missing symbols")

    logger.info(f"Loaded {len(df)} holdings from {file_path}")

    return df


def load_holdings_json(file_path: str) -> pd.DataFrame:
    """
    Load holdings from JSON file.

    Expected format:
    {
      "holdings": [
        {"symbol": "AAPL", "exchange": "NASDAQ", "quantity": 100, "avg_cost": 150.0},
        {"symbol": "MSFT", "exchange": "NASDAQ", "weight_pct": 15.5}
      ]
    }

    OR array of holdings objects directly.

    Args:
        file_path: Path to JSON file

    Returns:
        DataFrame with validated holdings
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Holdings file not found: {file_path}")

    with open(file_path, 'r') as f:
        data = json.load(f)

    # Handle both {"holdings": [...]} and [...] formats
    if isinstance(data, dict) and 'holdings' in data:
        holdings_list = data['holdings']
    elif isinstance(data, list):
        holdings_list = data
    else:
        raise ValueError("JSON must be array of holdings or object with 'holdings' key")

    # Convert to DataFrame
    df = pd.DataFrame(holdings_list)

    # Same validation as CSV
    if 'symbol' not in df.columns:
        raise ValueError("Holdings JSON must have 'symbol' field")

    if 'quantity' not in df.columns and 'weight_pct' not in df.columns:
        raise ValueError("Holdings JSON must have either 'quantity' or 'weight_pct' field")

    # Add defaults
    if 'exchange' not in df.columns:
        df['exchange'] = None

    logger.info(f"Loaded {len(df)} holdings from {file_path}")

    return df


def load_holdings(file_path: str) -> pd.DataFrame:
    """
    Load holdings from CSV or JSON (auto-detect from extension).

    Args:
        file_path: Path to holdings file (.csv or .json)

    Returns:
        DataFrame with holdings
    """
    path = Path(file_path)

    if path.suffix.lower() == '.csv':
        return load_holdings_csv(file_path)
    elif path.suffix.lower() == '.json':
        return load_holdings_json(file_path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}. Use .csv or .json")


def validate_holdings(holdings_df: pd.DataFrame) -> Dict[str, any]:
    """
    Validate holdings DataFrame and return summary.

    Args:
        holdings_df: Holdings DataFrame

    Returns:
        Dict with validation summary
    """
    summary = {
        'total_holdings': len(holdings_df),
        'has_quantities': holdings_df['quantity'].notna().sum() if 'quantity' in holdings_df.columns else 0,
        'has_weights': holdings_df['weight_pct'].notna().sum() if 'weight_pct' in holdings_df.columns else 0,
        'has_exchange': holdings_df['exchange'].notna().sum() if 'exchange' in holdings_df.columns else 0,
        'has_avg_cost': holdings_df['avg_cost'].notna().sum() if 'avg_cost' in holdings_df.columns else 0,
        'needs_pricing': False,
        'warnings': []
    }

    # Check if we need pricing data
    if summary['has_quantities'] > 0 and summary['has_weights'] == 0:
        summary['needs_pricing'] = True
        summary['warnings'].append('Quantities provided without weights; will fetch prices')

    if summary['has_exchange'] < summary['total_holdings']:
        missing_count = summary['total_holdings'] - summary['has_exchange']
        summary['warnings'].append(f'{missing_count} holdings missing exchange (may cause match failures)')

    return summary
