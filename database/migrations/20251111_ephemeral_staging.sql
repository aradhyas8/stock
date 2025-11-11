-- Migration: Add ephemeral staging tables for fundamentals and factors
-- Purpose: Store heavy data for non-finalists temporarily during screening
-- Only finalists (Top N in Research) get promoted to canonical tables
-- Created: 2025-11-11

-- ============================================================================
-- Fundamentals Staging Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS fundamentals_temp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    report_type TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER,

    -- Income Statement
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    ebit REAL,
    ebitda REAL,
    net_income REAL,

    -- Balance Sheet
    total_assets REAL,
    current_assets REAL,
    non_current_assets REAL,
    total_liabilities REAL,
    current_liabilities REAL,
    long_term_debt REAL,
    shareholders_equity REAL,

    -- Cash Flow
    operating_cash_flow REAL,
    investing_cash_flow REAL,
    financing_cash_flow REAL,
    free_cash_flow REAL,

    -- Per Share Data
    shares_outstanding REAL,
    book_value_per_share REAL,
    earnings_per_share REAL,

    -- Metadata
    currency TEXT NOT NULL DEFAULT 'USD',
    filed_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Unique constraint (same as canonical)
    UNIQUE(ticker_id, period_end)
);

-- Indexes for fast lookups during screening
CREATE INDEX IF NOT EXISTS idx_fundamentals_temp_ticker
    ON fundamentals_temp(ticker_id);

CREATE INDEX IF NOT EXISTS idx_fundamentals_temp_period
    ON fundamentals_temp(period_end);

CREATE INDEX IF NOT EXISTS idx_fundamentals_temp_ticker_period
    ON fundamentals_temp(ticker_id, period_end);


-- ============================================================================
-- Factors Staging Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS factors_temp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,

    -- Profitability Factors
    roe REAL,
    roa REAL,
    roce REAL,
    roic REAL,
    gross_margin REAL,
    operating_margin REAL,
    net_margin REAL,

    -- Growth Factors
    revenue_growth_1y REAL,
    revenue_growth_3y REAL,
    revenue_growth_5y REAL,
    earnings_growth_1y REAL,
    earnings_growth_3y REAL,
    earnings_growth_5y REAL,

    -- Quality Factors
    debt_to_equity REAL,
    current_ratio REAL,
    interest_coverage REAL,
    piotroski_score INTEGER,
    altman_z_score REAL,

    -- Valuation Factors
    pe_ratio REAL,
    pb_ratio REAL,
    ps_ratio REAL,
    peg_ratio REAL,
    ev_ebitda REAL,
    fcf_yield REAL,

    -- Risk Factors
    beta REAL,
    volatility_1y REAL,
    max_drawdown_1y REAL,

    -- Forensic Factors
    beneish_m_score REAL,
    days_sales_outstanding REAL,
    asset_quality_index REAL,

    -- Composite Scores
    quality_score REAL,
    growth_score REAL,
    value_score REAL,
    momentum_score REAL,
    overall_score REAL,

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Unique constraint (same as canonical)
    UNIQUE(ticker_id, as_of_date)
);

-- Indexes for fast lookups during screening
CREATE INDEX IF NOT EXISTS idx_factors_temp_ticker
    ON factors_temp(ticker_id);

CREATE INDEX IF NOT EXISTS idx_factors_temp_date
    ON factors_temp(as_of_date);

CREATE INDEX IF NOT EXISTS idx_factors_temp_ticker_date
    ON factors_temp(ticker_id, as_of_date);

CREATE INDEX IF NOT EXISTS idx_factors_temp_overall_score
    ON factors_temp(overall_score);

CREATE INDEX IF NOT EXISTS idx_factors_temp_quality_score
    ON factors_temp(quality_score);


-- ============================================================================
-- Notes
-- ============================================================================

-- 1. No foreign keys: Temp tables optimized for write speed during screening
-- 2. Schema mirrors canonical tables exactly (minus relationships)
-- 3. UNIQUE constraints enforce same deduplication as canonical
-- 4. Indexes match canonical for consistent query performance
-- 5. Promotion: UPSERT temp → canonical when ticker becomes finalist
-- 6. Purging: Phase B will add cleanup policies
