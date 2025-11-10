"""SQL query utilities for database operations"""

from typing import Any


def build_in_clause_params(
    values: list[int | str],
    param_prefix: str = "id",
) -> tuple[str, dict[str, Any]]:
    """
    Build SQL IN clause with dynamic placeholders for SQLite compatibility.

    SQLite doesn't support binding tuples directly to IN clauses, so we need
    to generate individual parameter placeholders dynamically.

    Args:
        values: List of values for IN clause (ticker IDs, symbols, etc.)
        param_prefix: Prefix for parameter names (default: 'id')

    Returns:
        Tuple of (placeholders_string, params_dict)

    Example:
        >>> placeholders, params = build_in_clause_params([10, 20, 30], 'ticker')
        >>> query = text(f"SELECT * FROM tickers WHERE id IN ({placeholders})")
        >>> result = session.execute(query, params)

        # Executes: SELECT * FROM tickers WHERE id IN (:ticker0,:ticker1,:ticker2)
        # With params: {'ticker0': 10, 'ticker1': 20, 'ticker2': 30}

    Raises:
        ValueError: If values list is empty
    """
    if not values:
        raise ValueError("values list cannot be empty for IN clause")

    # Generate placeholders: :id0, :id1, :id2, ...
    placeholders = ",".join([f":{param_prefix}{i}" for i in range(len(values))])

    # Build params dict: {id0: value0, id1: value1, ...}
    params = {f"{param_prefix}{i}": val for i, val in enumerate(values)}

    return placeholders, params
