"""Symbol canonicalization and ticker matching for portfolio reconciliation"""

import logging
from typing import Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def canonicalize_symbol(symbol: str, exchange: Optional[str] = None) -> Tuple[str, str]:
    """
    Normalize symbol and extract/validate exchange code.

    Handles:
    - Exchange suffixes: .NS, .NSE, .BSE, .TO
    - Class shares: BRK.B → BRK-B
    - Whitespace normalization

    Args:
        symbol: Raw symbol (e.g., "HDFCBANK.NS", "BRK.B")
        exchange: Optional exchange override

    Returns:
        Tuple of (normalized_symbol, exchange_code)

    Examples:
        >>> canonicalize_symbol("AAPL", "NASDAQ")
        ("AAPL", "NASDAQ")

        >>> canonicalize_symbol("HDFCBANK.NS")
        ("HDFCBANK", "NSE")

        >>> canonicalize_symbol("BRK.B", "NYSE")
        ("BRK-B", "NYSE")
    """
    symbol = symbol.strip().upper()

    # Extract exchange from symbol suffix (overrides provided exchange)
    if '.' in symbol:
        parts = symbol.rsplit('.', 1)
        base = parts[0]
        suffix = parts[1]

        # Map common suffixes to exchange codes
        suffix_map = {
            'NS': 'NSE',
            'NSE': 'NSE',
            'BO': 'BSE',
            'BSE': 'BSE',
            'TO': 'TSX',
        }

        if suffix in suffix_map:
            # Exchange suffix found
            exchange_code = suffix_map[suffix]
            symbol = base
        elif suffix in ['A', 'B', 'C']:
            # Class share (e.g., BRK.B)
            symbol = f"{base}-{suffix}"
            exchange_code = exchange or 'UNKNOWN'
        else:
            # Unknown suffix, keep as-is
            exchange_code = exchange or 'UNKNOWN'
    else:
        exchange_code = exchange or 'UNKNOWN'

    return (symbol, exchange_code)


def lookup_ticker(
    session: Session,
    symbol: str,
    exchange: str
) -> Dict[str, any]:
    """
    Find ticker_id for given symbol+exchange.

    Args:
        session: DB session
        symbol: Normalized symbol
        exchange: Exchange code

    Returns:
        Dict with:
        - status: 'matched' | 'ambiguous' | 'not_found'
        - ticker_id: Matched ticker ID (if status='matched')
        - candidates: List of candidate ticker IDs (if ambiguous)
        - reason: Human-readable explanation
    """
    # Query tickers
    query = text("""
        SELECT t.id, t.symbol, e.code as exchange_code, e.name as exchange_name
        FROM tickers t
        INNER JOIN exchanges e ON t.exchange_id = e.id
        WHERE UPPER(t.symbol) = UPPER(:symbol)
          AND UPPER(e.code) = UPPER(:exchange)
          AND t.active = 1
    """)

    result = session.execute(query, {'symbol': symbol, 'exchange': exchange})
    rows = result.fetchall()

    if len(rows) == 0:
        # Try fallback: match symbol only (any exchange)
        fallback_query = text("""
            SELECT t.id, t.symbol, e.code as exchange_code
            FROM tickers t
            INNER JOIN exchanges e ON t.exchange_id = e.id
            WHERE UPPER(t.symbol) = UPPER(:symbol)
              AND t.active = 1
            LIMIT 3
        """)

        fallback_result = session.execute(fallback_query, {'symbol': symbol})
        fallback_rows = fallback_result.fetchall()

        if len(fallback_rows) == 0:
            return {
                'status': 'not_found',
                'ticker_id': None,
                'candidates': [],
                'reason': f'No active ticker found for {symbol}'
            }
        else:
            # Found on other exchanges
            candidate_ids = [row[0] for row in fallback_rows]
            exchanges_found = [row[2] for row in fallback_rows]
            return {
                'status': 'ambiguous',
                'ticker_id': None,
                'candidates': candidate_ids,
                'reason': f'Symbol found on {",".join(exchanges_found)} but not {exchange}'
            }

    elif len(rows) == 1:
        # Unique match
        return {
            'status': 'matched',
            'ticker_id': rows[0][0],
            'candidates': [],
            'reason': 'Exact match'
        }

    else:
        # Multiple matches (should not happen with symbol+exchange, but handle)
        candidate_ids = [row[0] for row in rows]
        return {
            'status': 'ambiguous',
            'ticker_id': None,
            'candidates': candidate_ids,
            'reason': f'Multiple tickers found (IDs: {",".join(map(str, candidate_ids))})'
        }


def match_holdings_to_tickers(
    session: Session,
    holdings_symbols: list[Dict[str, str]]
) -> Dict[str, Dict]:
    """
    Batch match holdings symbols to ticker IDs.

    Args:
        session: DB session
        holdings_symbols: List of dicts with 'symbol' and optional 'exchange'

    Returns:
        Dict keyed by original symbol with match results
    """
    results = {}

    for holding in holdings_symbols:
        raw_symbol = holding['symbol']
        raw_exchange = holding.get('exchange')

        # Canonicalize
        normalized_symbol, exchange_code = canonicalize_symbol(raw_symbol, raw_exchange)

        # Lookup
        match_result = lookup_ticker(session, normalized_symbol, exchange_code)

        # Store result
        results[raw_symbol] = {
            'normalized_symbol': normalized_symbol,
            'exchange_code': exchange_code,
            **match_result
        }

        if match_result['status'] == 'matched':
            logger.info(f"Matched {raw_symbol} → ticker_id={match_result['ticker_id']}")
        else:
            logger.warning(f"Unmatched {raw_symbol}: {match_result['reason']}")

    return results
