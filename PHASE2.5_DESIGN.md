# Phase 2.5: Data Population - Design Document

## Think First

### Requirements Extraction

**Primary Goal**: Populate database with real market data for ~5,000 tickers

**Key Requirements**:
1. **Coverage**: Fetch for ≥95% of tickers (US + India)
2. **Efficiency**: Cache-first, batch-based, no per-ticker loops
3. **Rate Limits**: Respect API ToS (yfinance ~1 req/sec)
4. **TTLs**: prices=1 day, fundamentals=90 days
5. **Validation**: Re-run Phase 2 pipeline end-to-end
6. **Reproducibility**: Same --as-of → same results

### Data Sources Mapping

| Data Type | US Primary | India Primary | Batch Size | TTL |
|-----------|------------|---------------|------------|-----|
| **Prices (OHLCV)** | yfinance | yfinance (.NS suffix) | 50 tickers | 1 day |
| **Fundamentals** | yfinance | yfinance (.NS suffix) | 10 tickers | 90 days |
| **Factors** | Derived locally | Derived locally | N/A | Computed |

**Why yfinance**:
- Free, no API key required
- Supports both US and India (.NS suffix)
- Batch download capability
- Well-documented Python SDK

### Existing Components Assessment

**✅ Already Implemented**:
- Database schema (prices, fundamentals, factors tables)
- Data layer structure (cache.py, config.py, fetcher.py, models.py)
- Common utilities (HTTP session, retry, chunking)
- Screening pipeline (all 3 stages)

**🔜 Needs Implementation**:
1. Real yfinance adapter (currently placeholder)
2. Batch price fetching with 90-day window
3. Fundamentals parsing from yfinance
4. Factor computation (ROCE, revenue_cagr_5y, etc.)
5. CLI `populate` command
6. Validation reporting

### Data Mapping: API → Database

**Prices Table**:
```python
yfinance.Ticker.history(period='90d') →
{
  ticker_id: FK to tickers
  date: Date
  open_price: Open
  high_price: High
  low_price: Low
  close_price: Close
  adj_close: Adj Close
  volume: Volume
}
```

**Fundamentals Table**:
```python
yfinance.Ticker.financials (annual) →
{
  ticker_id: FK
  period_end: Date from index
  report_type: 'A'
  fiscal_year: Extract from date
  revenue: Total Revenue
  gross_profit: Gross Profit
  net_income: Net Income
  operating_cash_flow: Operating Cash Flow
  free_cash_flow: Free Cash Flow
  total_assets: Total Assets
  total_liabilities: Total Liabilities
  shareholders_equity: Stockholders Equity
}
```

**Factors Table** (computed locally):
```python
fundamentals (5 years) →
{
  ticker_id: FK
  as_of_date: Latest period
  roce: net_income / (total_assets - current_liabilities)
  revenue_growth_5y: CAGR(revenue[-5:])
  gross_margin: avg(gross_profit / revenue) * 100
  debt_to_equity: total_liabilities / shareholders_equity
  fcf_yield: fcf / market_cap
}
```

### Batch Strategy & Optimization

**Phase 1: Fetch Prices (All Tickers)**
```python
# Step 1: Get universe from tickers table (~5000)
# Step 2: Chunk into batches of 50
# Step 3: For each chunk:
#   - Check cache (TTL=1 day)
#   - If miss: yf.download(tickers, period='90d')
#   - Parse and upsert to prices table
#   - Update cache
# Expected: 5000 / 50 = 100 API calls (if cache cold)
# Runtime: 100 calls × 1s = ~2 minutes
```

**Phase 2: Run Stage 2.1 → Get Survivors (~500)**
```python
# Run fast screening on populated prices
# Output: ~500 tickers (10% survival rate)
```

**Phase 3: Fetch Fundamentals (Survivors Only)**
```python
# Step 1: For each survivor ticker:
#   - Check cache (TTL=90 days)
#   - If miss: yf.Ticker(symbol).financials, balance_sheet, cashflow
#   - Parse 5 years of data
#   - Upsert to fundamentals table
# Expected: ~500 API calls (if cache cold)
# Runtime: 500 × 0.2s = ~2 minutes
```

**Phase 4: Compute Factors (Local)**
```python
# For each ticker with fundamentals:
#   - Load 5 years of data
#   - Compute metrics (vectorized pandas)
#   - Upsert to factors table
# Runtime: <10 seconds (in-memory computation)
```

**Total Expected Runtime**: ~5 minutes (cold cache)

### Rate Limit Handling

**yfinance Limits**:
- No official rate limit, but recommended ~1 req/sec
- Batch downloads more efficient (50 tickers per call)
- Implement 1-second delay between batch calls

**Implementation**:
```python
import time

for chunk in chunks(tickers, 50):
    data = yf.download(chunk, period='90d')
    # Process data
    time.sleep(1)  # Polite delay
```

### Cache Strategy

**3-Tier Cache**:
1. **In-memory hot cache**: Recent requests (last 1000)
2. **SQLite http_cache**: Persistent across runs
3. **Network**: yfinance API

**TTL Policy**:
- Prices: 1 day (market data changes daily)
- Fundamentals: 90 days (quarterly updates)
- Factors: Recompute when fundamentals change

**Cache Key Generation**:
```python
prices_key = f"prices_{symbol}_{start_date}_{end_date}"
fundamentals_key = f"fundamentals_{symbol}_annual"
```

### Error Handling & Fallbacks

**Missing Data**:
- If yfinance returns empty → log warning, skip ticker
- If partial data (e.g., only 3 years) → use available data, flag in logs
- If API error → retry with exponential backoff (3 attempts)

**Data Quality Checks**:
- Prices: Validate no negative prices, volume > 0
- Fundamentals: Check for NULL critical fields (revenue, net_income)
- Factors: Validate computed values in reasonable ranges

### Validation Metrics

**Coverage**:
- Prices: Count(tickers with ≥60 days of data) / Total tickers
- Fundamentals: Count(tickers with ≥3 years) / Survivors count
- Target: ≥95% for prices, ≥90% for fundamentals

**Performance**:
- API calls total
- Cache hit rate on rerun
- Runtime per phase
- Errors by type

**Data Quality**:
- Row counts per table
- Missing data by ticker
- Outliers detected

### Implementation Plan (Detailed Steps)

**Step 1: Implement yfinance Price Adapter** (30 min)
- [ ] `data/adapters/yfinance_prices.py`
- [ ] Batch download with chunking
- [ ] Parse DataFrame → PriceBar model
- [ ] Upsert to prices table

**Step 2: Implement yfinance Fundamentals Adapter** (40 min)
- [ ] `data/adapters/yfinance_fundamentals.py`
- [ ] Fetch financials, balance_sheet, cashflow
- [ ] Parse multi-year data
- [ ] Upsert to fundamentals table

**Step 3: Implement Factor Computation** (30 min)
- [ ] `data/compute_factors.py`
- [ ] Load fundamentals per ticker
- [ ] Compute ROCE, CAGR, margins, etc.
- [ ] Upsert to factors table

**Step 4: CLI Populate Command** (20 min)
- [ ] `cli/main.py`: Add `populate` command
- [ ] Progress bars for each phase
- [ ] Summary statistics

**Step 5: Validation Command** (15 min)
- [ ] `cli/main.py`: Add `validate` command
- [ ] Coverage reports
- [ ] Data quality checks

**Step 6: End-to-End Test** (30 min)
- [ ] Run populate command
- [ ] Run Phase 2 screening pipeline
- [ ] Verify outputs
- [ ] Generate report

**Total Estimate**: ~3 hours

### Expected Outputs

**Database Rows** (after population):
```
prices:        ~450,000 rows (5000 tickers × 90 days)
fundamentals:  ~2,500 rows (500 survivors × 5 years)
factors:       ~500 rows (1 per survivor)
```

**Coverage Report**:
```
US Tickers: 3,500 (70%)
  - Prices: 3,450 (98.6%)
  - Fundamentals: 350 (10% screened)

India Tickers: 1,500 (30%)
  - Prices: 1,470 (98.0%)
  - Fundamentals: 150 (10% screened)

Total Coverage: 98.4% prices, 100% fundamentals (for survivors)
```

**Performance Report**:
```
API Calls:
  - Prices: 100 calls (50 tickers each)
  - Fundamentals: 500 calls (1 ticker each)
  - Total: 600 calls

Cache Stats:
  - Hit rate (cold): 0%
  - Hit rate (rerun): 95%+

Runtime:
  - Prices fetch: 2m 30s
  - Stage 2.1 screen: 15s
  - Fundamentals fetch: 1m 40s
  - Factor compute: 8s
  - Total: ~5 minutes
```

### Go/No-Go Criteria

**✅ GO if**:
- Prices coverage ≥95%
- Fundamentals coverage ≥90% (of survivors)
- Phase 2 pipeline completes in <60s
- No critical errors in data quality
- Cache hit rate ≥80% on rerun

**❌ NO-GO if**:
- API rate limits exceeded (banned)
- Critical data corruption
- Pipeline fails with real data
- Coverage <80% (investigate source issues)

---

## Next Actions

1. Implement yfinance adapters
2. Create CLI populate command
3. Run end-to-end test
4. Generate validation report
5. Proceed to Phase 3 if GO

**Estimated Completion**: 2025-11-10 (today)
