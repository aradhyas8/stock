-- Description: initial_schema
-- Up:

-- Create exchanges table
CREATE TABLE exchanges (
    id INTEGER PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(3) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create sectors table
CREATE TABLE sectors (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INTEGER REFERENCES sectors(id),
    level INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create tickers table
CREATE TABLE tickers (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    name VARCHAR(200) NOT NULL,
    sector_id INTEGER REFERENCES sectors(id),
    market_cap DECIMAL(15,2),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    isin VARCHAR(12),
    cusip VARCHAR(9),
    active BOOLEAN NOT NULL DEFAULT 1,
    delisted_date DATE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create prices table
CREATE TABLE prices (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4) NOT NULL,
    adj_close DECIMAL(12,4) NOT NULL,
    volume INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create fundamentals table
CREATE TABLE fundamentals (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    period_end DATE NOT NULL,
    report_type VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER,
    revenue DECIMAL(15,2),
    gross_profit DECIMAL(15,2),
    operating_income DECIMAL(15,2),
    ebit DECIMAL(15,2),
    ebitda DECIMAL(15,2),
    net_income DECIMAL(15,2),
    total_assets DECIMAL(15,2),
    current_assets DECIMAL(15,2),
    non_current_assets DECIMAL(15,2),
    total_liabilities DECIMAL(15,2),
    current_liabilities DECIMAL(15,2),
    long_term_debt DECIMAL(15,2),
    shareholders_equity DECIMAL(15,2),
    operating_cash_flow DECIMAL(15,2),
    investing_cash_flow DECIMAL(15,2),
    financing_cash_flow DECIMAL(15,2),
    free_cash_flow DECIMAL(15,2),
    shares_outstanding DECIMAL(12,2),
    book_value_per_share DECIMAL(8,4),
    earnings_per_share DECIMAL(8,4),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    filed_date DATE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create factors table
CREATE TABLE factors (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    as_of_date DATE NOT NULL,
    roe DECIMAL(8,4),
    roa DECIMAL(8,4),
    roce DECIMAL(8,4),
    roic DECIMAL(8,4),
    gross_margin DECIMAL(8,4),
    operating_margin DECIMAL(8,4),
    net_margin DECIMAL(8,4),
    revenue_growth_1y DECIMAL(8,4),
    revenue_growth_3y DECIMAL(8,4),
    revenue_growth_5y DECIMAL(8,4),
    earnings_growth_1y DECIMAL(8,4),
    earnings_growth_3y DECIMAL(8,4),
    earnings_growth_5y DECIMAL(8,4),
    debt_to_equity DECIMAL(8,4),
    current_ratio DECIMAL(8,4),
    interest_coverage DECIMAL(8,4),
    piotroski_score INTEGER,
    altman_z_score DECIMAL(8,4),
    pe_ratio DECIMAL(8,4),
    pb_ratio DECIMAL(8,4),
    ps_ratio DECIMAL(8,4),
    peg_ratio DECIMAL(8,4),
    ev_ebitda DECIMAL(8,4),
    fcf_yield DECIMAL(8,4),
    beta DECIMAL(8,4),
    volatility_1y DECIMAL(8,4),
    max_drawdown_1y DECIMAL(8,4),
    beneish_m_score DECIMAL(8,4),
    days_sales_outstanding DECIMAL(8,4),
    asset_quality_index DECIMAL(8,4),
    quality_score DECIMAL(8,4),
    growth_score DECIMAL(8,4),
    value_score DECIMAL(8,4),
    momentum_score DECIMAL(8,4),
    overall_score DECIMAL(8,4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create http_cache table
CREATE TABLE http_cache (
    id INTEGER PRIMARY KEY,
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    url TEXT NOT NULL,
    response_data TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    content_type VARCHAR(100),
    ttl_days INTEGER NOT NULL DEFAULT 1,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create runs table
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL UNIQUE,
    month_year VARCHAR(7) NOT NULL,
    stage VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    input_count INTEGER,
    output_count INTEGER,
    duration_seconds INTEGER,
    parameters TEXT,
    error_message TEXT
);

-- Create decisions table
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    ticker_id INTEGER NOT NULL REFERENCES tickers(id),
    stage VARCHAR(50) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    reason VARCHAR(500),
    score DECIMAL(8,4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE UNIQUE INDEX ix_ticker_symbol_exchange ON tickers(symbol, exchange_id);
CREATE INDEX ix_ticker_active ON tickers(active);
CREATE INDEX ix_ticker_market_cap ON tickers(market_cap);
CREATE UNIQUE INDEX ix_price_ticker_date ON prices(ticker_id, date);
CREATE INDEX ix_price_date ON prices(date);
CREATE UNIQUE INDEX ix_fundamental_ticker_period ON fundamentals(ticker_id, period_end);
CREATE INDEX ix_fundamental_period ON fundamentals(period_end);
CREATE INDEX ix_fundamental_fiscal_year ON fundamentals(fiscal_year);
CREATE UNIQUE INDEX ix_factor_ticker_date ON factors(ticker_id, as_of_date);
CREATE INDEX ix_factor_date ON factors(as_of_date);
CREATE INDEX ix_factor_overall_score ON factors(overall_score);
CREATE INDEX ix_factor_quality_score ON factors(quality_score);
CREATE INDEX ix_cache_key ON http_cache(cache_key);
CREATE INDEX ix_cache_expires ON http_cache(expires_at);
CREATE INDEX ix_run_month_year ON runs(month_year);
CREATE INDEX ix_run_started_at ON runs(started_at);
CREATE INDEX ix_run_status ON runs(status);
CREATE INDEX ix_decision_run_ticker ON decisions(run_id, ticker_id);
CREATE INDEX ix_decision_stage ON decisions(stage);
CREATE INDEX ix_decision_decision ON decisions(decision);


-- Down:

DROP TABLE IF EXISTS decisions;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS http_cache;
DROP TABLE IF EXISTS factors;
DROP TABLE IF EXISTS fundamentals;
DROP TABLE IF EXISTS prices;
DROP TABLE IF EXISTS tickers;
DROP TABLE IF EXISTS sectors;
DROP TABLE IF EXISTS exchanges;

