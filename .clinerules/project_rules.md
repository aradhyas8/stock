Workspace Rules: Multi-Bagger Research System
Project Identity

Name: Multi-Bagger Research System
Type: Personal investment research pipeline
Purpose: Systematically identify 2-5x return opportunities from ~5,000 stocks
Current Phase: Foundation/MVP (Phases 1-2)

Tech Stack (Non-Negotiable)

Language: Python 3.10+
Database: PostgreSQL for historical data, Redis for caching
Orchestration: Apache Airflow for pipeline scheduling
Data Sources: Yahoo Finance (yfinance), Alpha Vantage, Financial Modeling Prep
Output: PDF reports (ReportLab) + JSON data files
LLM Integration: OpenAI API (for NLP analysis in Phase 3+)

Project Structure
multi-bagger-research/
├── src/
│   ├── data_ingestion/      # Phase 1: API connectors, rate limiters
│   ├── screening/           # Phase 2: Factor calculations, scoring
│   ├── forensics/           # Phase 3: Red flag detection
│   ├── business_analysis/   # Phase 4: Moat analysis
│   ├── management/          # Phase 5: Management assessment
│   ├── catalysts/           # Phase 6: Catalyst tracking
│   ├── valuation/           # Phase 7: DCF, multiples
│   ├── risk/                # Phase 8: Risk modeling
│   ├── portfolio/           # Phase 9: Optimization
│   └── reporting/           # Phase 10: Report generation
├── airflow/
│   └── dags/                # Pipeline definitions
├── database/
│   └── migrations/          # Schema definitions
├── tests/
└── config/
Development Phase Rules
Current MVP Scope (Phases 1-2)

IN SCOPE: Data ingestion, basic screening, simple valuation, basic monitoring
OUT OF SCOPE: Forensic accounting, management analysis, portfolio optimization, ML models

Never Suggest

Trading execution systems
Real-time/intraday analysis
Social features or multi-user support
Mobile apps
Backtesting engines (not in initial scope)
Generic stock screeners without forensic depth

Coding Standards
Data Handling

All financial data must be adjusted for splits/dividends
Cache API responses in Redis (respect rate limits)
Validate data completeness before calculations
Store timestamps in UTC
Handle missing data explicitly (no silent fails)

Database Patterns

Use SQLAlchemy ORM for database interactions
All tables must have: id, created_at, updated_at
Stock identifiers: Store both ticker and ISIN/CUSIP
Never hardcode SQL queries
Use database migrations for schema changes

API Integration

Implement exponential backoff for retries
Log all API calls with response codes
Never exceed free tier rate limits
Cache responses for minimum 24 hours
Handle API failures gracefully (degrade, don't crash)

Calculations

Use Decimal for monetary values
Round percentages to 2 decimal places
Document all formulas with academic/industry sources
Validate outputs against known benchmarks
Handle division by zero explicitly

Factor Calculations (Phase 2)

ROE = Net Income / Shareholders' Equity
ROCE = EBIT / (Total Assets - Current Liabilities)
ROIC = NOPAT / Invested Capital
Use trailing 12 months (TTM) for consistency
Calculate 3-year and 5-year averages where applicable

Performance Requirements

Pipeline must process 5,000 stocks in < 30 minutes
Database queries must complete in < 5 seconds
API calls must respect rate limits (never exceed)
Reports must generate in < 2 minutes each

Data Sources & Assumptions
Market Coverage

MVP: US markets (NYSE, NASDAQ)
v2: India markets (NSE, BSE)
Minimum liquidity: $5M daily volume, $100M market cap

Historical Data Requirements

Minimum 5 years of price data
Minimum 5 years of financial statements
Quarterly earnings data
Corporate actions history

Data Quality Filters

Exclude stocks with < 80% data completeness
Flag stocks with irregular reporting
Exclude ADRs and foreign ordinaries (initially)

Scoring & Ranking
Composite Scoring Rules

Use z-score normalization for all factors
Equal weights initially (no ML optimization yet)
Percentile rankings within universe
Output top 500 candidates from screening

Red Flags (Phase 3+)

Beneish M-Score > -1.78 = potential manipulation
Altman Z-Score < 1.8 = bankruptcy risk
Piotroski F-Score < 7 = weak fundamentals
Auto-eliminate stocks with 3+ red flags

Output Standards
Reports Must Include

Executive summary (1 page)
Investment thesis (2-3 bullet points)
Financial analysis (key metrics table)
Valuation summary (multiple methods)
Risk assessment
Catalysts timeline
Exit criteria

Data Outputs

JSON files for all screening results
CSV exports for factor scores
Audit trail of all decisions
Timestamped snapshots

Error Handling

Log all errors with context
Never fail silently
Retry failed API calls (max 3 attempts)
Alert on data quality issues
Graceful degradation (proceed with warnings, not crashes)

Security & Privacy

Store API keys in environment variables
No hardcoded credentials
No PII collection (this is a personal tool)
Secure database connections only

Testing Requirements

Unit tests for all calculations
Integration tests for API connectors
Validate against known stock examples
Test with edge cases (zero revenue, negative equity)

Documentation Standards

Docstrings for all functions (Google style)
Explain all financial formulas with sources
Comment complex business logic
Maintain changelog for pipeline versions

Constraints & Boundaries
API Limitations

Alpha Vantage: 5 calls/minute, 500 calls/day (free tier)
Financial Modeling Prep: 250 calls/day (free tier)
Yahoo Finance: No official limit, but rate-limit conservatively

Computational

Single-threaded initially
Add multiprocessing in Phase 2 optimization
No GPU requirements
Run on standard laptop (16GB RAM minimum)

Phase-Specific Reminders
When Working on Phase 1

Focus on data infrastructure robustness
Build retry logic from day one
Schema design is critical (hard to change later)

When Working on Phase 2

Document all factor calculations with sources
Validate outputs against known benchmarks
Build audit trail for debugging

For Future Phases (3+)

Don't prematurely optimize
Build each phase end-to-end before moving to next
Test with real stocks, not synthetic data
