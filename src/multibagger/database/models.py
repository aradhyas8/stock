"""SQLAlchemy models for Multi-Bagger Research System"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class SchemaVersion(Base):
    """Track database schema version for migrations"""

    __tablename__ = "schema_versions"

    version = Column(String(50), primary_key=True)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    description = Column(String(255))


class Exchange(Base):
    """Stock exchanges (NYSE, NASDAQ, NSE, BSE)"""

    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)  # NYSE, NASDAQ, NSE
    name = Column(String(100), nullable=False)
    country = Column(String(3), nullable=False)  # ISO country code
    timezone = Column(String(50), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    tickers = relationship("Ticker", back_populates="exchange")


class Sector(Base):
    """Industry sectors and sub-sectors"""

    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("sectors.id"), nullable=True)
    level = Column(
        Integer, nullable=False, default=1
    )  # 1=sector, 2=industry, 3=sub-industry
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    parent = relationship("Sector", remote_side=[id])
    tickers = relationship("Ticker", back_populates="sector")


class Ticker(Base):
    """Stock reference data"""

    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False)
    exchange_id = Column(Integer, ForeignKey("exchanges.id"), nullable=False)
    name = Column(String(200), nullable=False)
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=True)
    market_cap = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="USD")
    isin = Column(String(12), nullable=True)
    cusip = Column(String(9), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    delisted_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    exchange = relationship("Exchange", back_populates="tickers")
    sector = relationship("Sector", back_populates="tickers")
    prices = relationship("Price", back_populates="ticker")
    fundamentals = relationship("Fundamental", back_populates="ticker")
    factors = relationship("Factor", back_populates="ticker")

    # Constraints
    __table_args__ = (
        Index("ix_ticker_symbol_exchange", "symbol", "exchange_id", unique=True),
        Index("ix_ticker_active", "active"),
        Index("ix_ticker_market_cap", "market_cap"),
    )


class Price(Base):
    """Daily OHLCV price data"""

    __tablename__ = "prices"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    date = Column(Date, nullable=False)
    open_price = Column(Numeric(12, 4), nullable=True)
    high_price = Column(Numeric(12, 4), nullable=True)
    low_price = Column(Numeric(12, 4), nullable=True)
    close_price = Column(Numeric(12, 4), nullable=False)
    adj_close = Column(Numeric(12, 4), nullable=False)
    volume = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    ticker = relationship("Ticker", back_populates="prices")

    # Constraints
    __table_args__ = (
        Index("ix_price_ticker_date", "ticker_id", "date", unique=True),
        Index("ix_price_date", "date"),
    )


class Fundamental(Base):
    """Quarterly/Annual financial statements"""

    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    period_end = Column(Date, nullable=False)
    report_type = Column(String(10), nullable=False)  # 'Q' or 'A'
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(
        Integer, nullable=True
    )  # 1-4 for quarterly, NULL for annual

    # Income Statement
    revenue = Column(Numeric(15, 2), nullable=True)
    gross_profit = Column(Numeric(15, 2), nullable=True)
    operating_income = Column(Numeric(15, 2), nullable=True)
    ebit = Column(Numeric(15, 2), nullable=True)
    ebitda = Column(Numeric(15, 2), nullable=True)
    net_income = Column(Numeric(15, 2), nullable=True)

    # Balance Sheet
    total_assets = Column(Numeric(15, 2), nullable=True)
    current_assets = Column(Numeric(15, 2), nullable=True)
    non_current_assets = Column(Numeric(15, 2), nullable=True)
    total_liabilities = Column(Numeric(15, 2), nullable=True)
    current_liabilities = Column(Numeric(15, 2), nullable=True)
    long_term_debt = Column(Numeric(15, 2), nullable=True)
    shareholders_equity = Column(Numeric(15, 2), nullable=True)

    # Cash Flow
    operating_cash_flow = Column(Numeric(15, 2), nullable=True)
    investing_cash_flow = Column(Numeric(15, 2), nullable=True)
    financing_cash_flow = Column(Numeric(15, 2), nullable=True)
    free_cash_flow = Column(Numeric(15, 2), nullable=True)

    # Per Share Data
    shares_outstanding = Column(Numeric(12, 2), nullable=True)
    book_value_per_share = Column(Numeric(8, 4), nullable=True)
    earnings_per_share = Column(Numeric(8, 4), nullable=True)

    # Metadata
    currency = Column(String(3), nullable=False, default="USD")
    filed_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    ticker = relationship("Ticker", back_populates="fundamentals")

    # Constraints
    __table_args__ = (
        Index("ix_fundamental_ticker_period", "ticker_id", "period_end", unique=True),
        Index("ix_fundamental_period", "period_end"),
        Index("ix_fundamental_fiscal_year", "fiscal_year"),
    )


class Factor(Base):
    """Precomputed factor scores for screening"""

    __tablename__ = "factors"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    as_of_date = Column(Date, nullable=False)

    # Profitability Factors
    roe = Column(Numeric(8, 4), nullable=True)  # Return on Equity
    roa = Column(Numeric(8, 4), nullable=True)  # Return on Assets
    roce = Column(Numeric(8, 4), nullable=True)  # Return on Capital Employed
    roic = Column(Numeric(8, 4), nullable=True)  # Return on Invested Capital
    gross_margin = Column(Numeric(8, 4), nullable=True)
    operating_margin = Column(Numeric(8, 4), nullable=True)
    net_margin = Column(Numeric(8, 4), nullable=True)

    # Growth Factors
    revenue_growth_1y = Column(Numeric(8, 4), nullable=True)
    revenue_growth_3y = Column(Numeric(8, 4), nullable=True)
    revenue_growth_5y = Column(Numeric(8, 4), nullable=True)
    earnings_growth_1y = Column(Numeric(8, 4), nullable=True)
    earnings_growth_3y = Column(Numeric(8, 4), nullable=True)
    earnings_growth_5y = Column(Numeric(8, 4), nullable=True)

    # Quality Factors
    debt_to_equity = Column(Numeric(8, 4), nullable=True)
    current_ratio = Column(Numeric(8, 4), nullable=True)
    interest_coverage = Column(Numeric(8, 4), nullable=True)
    piotroski_score = Column(Integer, nullable=True)
    altman_z_score = Column(Numeric(8, 4), nullable=True)

    # Valuation Factors
    pe_ratio = Column(Numeric(8, 4), nullable=True)
    pb_ratio = Column(Numeric(8, 4), nullable=True)
    ps_ratio = Column(Numeric(8, 4), nullable=True)
    peg_ratio = Column(Numeric(8, 4), nullable=True)
    ev_ebitda = Column(Numeric(8, 4), nullable=True)
    fcf_yield = Column(Numeric(8, 4), nullable=True)

    # Risk Factors
    beta = Column(Numeric(8, 4), nullable=True)
    volatility_1y = Column(Numeric(8, 4), nullable=True)
    max_drawdown_1y = Column(Numeric(8, 4), nullable=True)

    # Forensic Factors
    beneish_m_score = Column(Numeric(8, 4), nullable=True)
    days_sales_outstanding = Column(Numeric(8, 4), nullable=True)
    asset_quality_index = Column(Numeric(8, 4), nullable=True)

    # Composite Scores
    quality_score = Column(Numeric(8, 4), nullable=True)
    growth_score = Column(Numeric(8, 4), nullable=True)
    value_score = Column(Numeric(8, 4), nullable=True)
    momentum_score = Column(Numeric(8, 4), nullable=True)
    overall_score = Column(Numeric(8, 4), nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    ticker = relationship("Ticker", back_populates="factors")

    # Constraints
    __table_args__ = (
        Index("ix_factor_ticker_date", "ticker_id", "as_of_date", unique=True),
        Index("ix_factor_date", "as_of_date"),
        Index("ix_factor_overall_score", "overall_score"),
        Index("ix_factor_quality_score", "quality_score"),
    )


class HttpCache(Base):
    """HTTP response cache for API calls"""

    __tablename__ = "http_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(255), unique=True, nullable=False)
    url = Column(Text, nullable=False)
    response_data = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False)
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    content_type = Column(String(100), nullable=True)
    ttl_days = Column(Integer, nullable=False, default=1)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        Index("ix_cache_key", "cache_key"),
        Index("ix_cache_expires", "expires_at"),
    )


class Run(Base):
    """Track pipeline execution runs"""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(50), unique=True, nullable=False)  # YYYY-MM-DD_HH-MM-SS
    month_year = Column(String(7), nullable=False)  # YYYY-MM
    stage = Column(String(50), nullable=False)  # universe, screen, research, etc.
    status = Column(String(20), nullable=False)  # running, completed, failed
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Pipeline Statistics
    input_count = Column(Integer, nullable=True)
    output_count = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    # Configuration
    parameters = Column(Text, nullable=True)  # JSON string of parameters
    error_message = Column(Text, nullable=True)

    # Relationships
    decisions = relationship("Decision", back_populates="run")

    # Constraints
    __table_args__ = (
        Index("ix_run_month_year", "month_year"),
        Index("ix_run_started_at", "started_at"),
        Index("ix_run_status", "status"),
    )


class Decision(Base):
    """Track individual stock decisions during pipeline runs"""

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    stage = Column(String(50), nullable=False)
    decision = Column(String(20), nullable=False)  # pass, fail, skip
    reason = Column(String(500), nullable=True)
    score = Column(Numeric(8, 4), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    run = relationship("Run", back_populates="decisions")
    ticker = relationship("Ticker")

    # Constraints
    __table_args__ = (
        Index("ix_decision_run_ticker", "run_id", "ticker_id"),
        Index("ix_decision_stage", "stage"),
        Index("ix_decision_decision", "decision"),
    )


class RiskFlag(Base):
    """Red flag detection results for ticker risk assessment"""

    __tablename__ = "risk_flags"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    as_of_date = Column(Date, nullable=False)

    # Forensics Metrics (Accounting/Financial)
    beneish_m_score = Column(Numeric(8, 4), nullable=True)
    altman_z_score = Column(Numeric(8, 4), nullable=True)
    accruals_ratio = Column(Numeric(8, 4), nullable=True)
    forensics_score = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Governance Metrics (Insiders/Ownership)
    insider_sell_90d = Column(Numeric(8, 4), nullable=True)  # % of shares
    promoter_pledge = Column(Numeric(8, 4), nullable=True)  # % of promoter holding
    governance_score = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Sentiment Metrics (News/Media)
    neg_news_30d = Column(Integer, nullable=True)  # count of adverse articles
    severity_score = Column(Numeric(5, 2), nullable=True)  # weighted severity
    sentiment_score = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Composite Metrics
    composite_score = Column(Numeric(5, 2), nullable=True)  # 0-100 (weighted avg)
    first_fail_reason = Column(String(100), nullable=True)  # null if no hard stop

    # Explainability (full breakdown with provenance)
    details_json = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    ticker = relationship("Ticker")

    # Constraints
    __table_args__ = (
        Index("ix_risk_flag_ticker_date", "ticker_id", "as_of_date", unique=True),
        Index("ix_risk_flag_composite", "composite_score"),
        Index("ix_risk_flag_date", "as_of_date"),
    )


class Research(Base):
    """Phase 4: Research reports with business analysis and valuation"""

    __tablename__ = "research"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    as_of_date = Column(Date, nullable=False)

    # Business Analysis
    thesis = Column(Text)  # Executive summary thesis
    moat = Column(String(50))  # cost_advantage, switching_costs, network_effects, ip_brand, scale, unknown
    business_model = Column(Text)  # Revenue model description
    growth_drivers = Column(Text)  # Key growth catalysts
    top_risks = Column(Text)  # Top 5 risks from filings + red flags

    # Valuation
    base_fair_value = Column(Numeric(15, 2))  # DCF base case fair value
    bear_fair_value = Column(Numeric(15, 2))  # DCF bear case
    bull_fair_value = Column(Numeric(15, 2))  # DCF bull case
    upside_pct = Column(Numeric(10, 2))  # (base_fair_value - current_price) / current_price * 100

    # JSON Payloads
    valuation_json = Column(Text)  # Full DCF model with projections
    comps_json = Column(Text)  # Peer comparables analysis
    assumptions_json = Column(Text)  # All assumptions for audit trail
    sources_json = Column(Text)  # Provenance (filings, fundamentals)

    # Report Artifacts
    report_md_path = Column(String(255))  # Path to Markdown report
    report_pdf_path = Column(String(255))  # Path to PDF report

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticker = relationship("Ticker")

    # Constraints
    __table_args__ = (
        Index("ix_research_ticker_date", "ticker_id", "as_of_date", unique=True),
        Index("ix_research_date", "as_of_date"),
        Index("ix_research_upside", "upside_pct"),
    )


class PortfolioRun(Base):
    """Phase 5: Portfolio reconciliation runs - monthly snapshots"""

    __tablename__ = "portfolio_runs"

    id = Column(Integer, primary_key=True)
    as_of_date = Column(Date, unique=True, nullable=False)  # YYYY-MM-01 for idempotency
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Metrics and configuration
    metrics_json = Column(Text, nullable=False)  # turnover_pct, position_counts, config assumptions

    # Relationships
    positions = relationship("PortfolioPosition", back_populates="run", cascade="all, delete-orphan")
    actions = relationship("PortfolioAction", back_populates="run", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        Index("ix_portfolio_run_date", "as_of_date"),
    )


class PortfolioPosition(Base):
    """Phase 5: Target portfolio positions for a given run"""

    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("portfolio_runs.id"), nullable=False)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)

    # Position sizing
    weight_pct = Column(Numeric(5, 2), nullable=False)  # Target allocation percentage

    # Pricing and targets
    entry_price = Column(Numeric(12, 4), nullable=True)  # Current/entry price
    target_price = Column(Numeric(12, 4), nullable=True)  # DCF fair value
    stop_loss_price = Column(Numeric(12, 4), nullable=True)  # Risk management

    # Conviction
    conviction_score = Column(Numeric(5, 2), nullable=True)  # 0-100 score

    # Additional metadata
    notes_json = Column(Text, nullable=True)  # Additional details (thesis, moat, etc.)

    # Relationships
    run = relationship("PortfolioRun", back_populates="positions")
    ticker = relationship("Ticker")

    # Constraints
    __table_args__ = (
        Index("ix_portfolio_position_run_ticker", "run_id", "ticker_id", unique=True),
        Index("ix_portfolio_position_run", "run_id"),
        Index("ix_portfolio_position_ticker", "ticker_id"),
    )


class PortfolioAction(Base):
    """Phase 5: Recommended portfolio actions for a given run"""

    __tablename__ = "portfolio_actions"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("portfolio_runs.id"), nullable=False)

    # Action type
    action = Column(String(10), nullable=False)  # BUY, SELL, TRIM, ADD, HOLD

    # Target (nullable for CASH adjustments)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=True)

    # Rationale
    reason = Column(Text, nullable=True)  # Human-readable reason

    # Details
    details_json = Column(Text, nullable=True)  # weights, drifts, prices

    # Relationships
    run = relationship("PortfolioRun", back_populates="actions")
    ticker = relationship("Ticker")

    # Constraints
    __table_args__ = (
        Index("ix_portfolio_action_run", "run_id"),
        Index("ix_portfolio_action_type", "action"),
        Index("ix_portfolio_action_ticker", "ticker_id"),
    )
