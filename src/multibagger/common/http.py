"""HTTP utilities with retry and backoff logic"""

import logging
import random
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def create_http_session(
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    timeout: int = 30,
    user_agent: str = "MultiBagger/1.0",
) -> requests.Session:
    """
    Create HTTP session with retry logic and sensible defaults.

    Single reusable session reduces connection overhead.
    """
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set default headers
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json,text/html,text/csv",
    })

    # Store timeout as session attribute
    session.timeout = timeout  # type: ignore

    return session


def exponential_backoff(
    attempt: int,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2 ** attempt), max_delay)

    if jitter:
        # Add ±25% jitter
        delay *= random.uniform(0.75, 1.25)

    return delay


def retry_with_backoff(
    func: Any,
    max_attempts: int = 4,
    base_delay: float = 2.0,
    exceptions: tuple = (requests.RequestException,),
) -> Any:
    """
    Retry function with exponential backoff.

    Args:
        func: Callable to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay for backoff
        exceptions: Exceptions to catch and retry

    Returns:
        Function result
    """
    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as e:
            if attempt == max_attempts - 1:
                raise

            delay = exponential_backoff(attempt, base_delay)
            logger.warning(
                f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    return None
