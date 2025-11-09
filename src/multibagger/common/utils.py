"""General utility functions"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def chunk_list(items: list[T], chunk_size: int) -> list[list[T]]:
    """
    Split list into chunks of specified size.

    Single reusable chunking utility for batch operations.

    Args:
        items: List to chunk
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def check_ttl_fresh(
    created_at: datetime,
    ttl_days: int,
    now: datetime | None = None,
) -> bool:
    """
    Check if cached item is still fresh based on TTL.

    Single TTL checking utility used across all cache lookups.

    Args:
        created_at: When item was created/cached
        ttl_days: Time-to-live in days
        now: Current time (defaults to utcnow)

    Returns:
        True if fresh, False if expired
    """
    if now is None:
        now = datetime.utcnow()

    expires_at = created_at + timedelta(days=ttl_days)
    return now < expires_at


def generate_cache_key(*args: Any, **kwargs: Any) -> str:
    """
    Generate consistent cache key from arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        MD5 hash as cache key
    """
    # Combine all args into a stable string
    parts = [str(arg) for arg in args]
    parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_string = "|".join(parts)

    # Hash to fixed length
    return hashlib.md5(key_string.encode()).hexdigest()


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float with default.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Float value
    """
    if value is None:
        return default

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int with default.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Integer value
    """
    if value is None:
        return default

    try:
        return int(value)
    except (ValueError, TypeError):
        return default
