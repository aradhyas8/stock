-- Description: Create risk_flags table for Phase 3 forensics screening
-- Up:

CREATE TABLE IF NOT EXISTS risk_flags (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,

    -- Forensics metrics
    beneish_m_score DECIMAL(8, 4),
    altman_z_score DECIMAL(8, 4),
    accruals_ratio DECIMAL(8, 4),
    forensics_score DECIMAL(5, 2),

    -- Governance metrics (stub for MVP)
    insider_sell_90d INTEGER,
    promoter_pledge DECIMAL(5, 2),
    governance_score DECIMAL(5, 2),

    -- Sentiment metrics (stub for MVP)
    neg_news_30d INTEGER,
    severity_score DECIMAL(5, 2),
    sentiment_score DECIMAL(5, 2),

    -- Composite score
    composite_score DECIMAL(5, 2),
    first_fail_reason VARCHAR(100),
    details_json TEXT,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ticker_id) REFERENCES tickers(id),
    UNIQUE(ticker_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS ix_risk_flag_ticker_date ON risk_flags(ticker_id, as_of_date);
CREATE INDEX IF NOT EXISTS ix_risk_flag_composite ON risk_flags(composite_score);

-- Down:
-- DROP TABLE IF EXISTS risk_flags;
