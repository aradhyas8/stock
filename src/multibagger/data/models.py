"""Data models for financial data"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class PriceBar:
    """OHLCV price bar"""

    ticker: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float
    volume: int | None


@dataclass
class FundamentalSnapshot:
    """Fundamental financial data snapshot"""

    ticker: str
    period_end: date
    report_type: str  # 'Q' or 'A'
    fiscal_year: int
    fiscal_quarter: int | None

    # Income statement
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    ebitda: float | None = None

    # Balance sheet
    total_assets: float | None = None
    current_assets: float | None = None
    total_liabilities: float | None = None
    current_liabilities: float | None = None
    shareholders_equity: float | None = None

    # Cash flow
    operating_cash_flow: float | None = None
    free_cash_flow: float | None = None

    # Per share
    shares_outstanding: float | None = None
    earnings_per_share: float | None = None
    book_value_per_share: float | None = None


@dataclass
class InstrumentMeta:
    """Instrument metadata"""

    ticker: str
    name: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    currency: str = "USD"


@dataclass
class FilingMeta:
    """SEC filing metadata"""

    ticker: str
    form_type: str
    filing_date: date
    accession_number: str
    url: str


@dataclass
class FetchResult:
    """Result of data fetch operation with provenance"""

    records: list
    cache_hits: int
    network_calls: int
    execution_time_ms: int
    errors: list[str]
    source: str  # 'yahoo', 'alpha_vantage', etc.
    fetched_at: datetime
