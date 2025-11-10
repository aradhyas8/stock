# Phase 2: Fast Filtering Pipeline - Design Document

## Think First

### PRD Phase-2 Requirements Extraction

**Explicit Requirements:**

1. **Speed**: Stage 1 (Quick Screener) must complete <30s for 5000 tickers
2. **Deterministic**: All stages accept `--as-of YYYY-MM`; re-running yields identical outputs
3. **No network I/O**: All data from local DB/snapshots only
4. **Batch-first**: No per-ticker loops; SQL window functions or vectorized pandas only
5. **Config-driven**: All thresholds in `config.yml` under `screen.fast`, `screen.quality`, `screen.business`
6. **Outputs**: CSV to `snapshots/<AS_OF>/stageX_*.csv`, DB logging to `runs`/`decisions`, summary tables
7. **Observability**: Print removed-by-rule counts, survivors, runtime per stage
8. **Auditability**: Record first failing rule per ticker in `decisions.reason`

**Stage Targets:**
- **2.1 Quick Screener**: 5000 → ~500 (10%)
- **2.2 Quality Filter**: 500 → ~100 (2%)
- **2.3 Business Filter**: 100 → ~30 (0.6%)

### Data Availability Map

**Confirmed Tables/Columns:**

1. **Stage 2.1 (Quick Screener)** reads:
   - `tickers`: `id`, `symbol`, `exchange_id`, `active`, `market_cap`, `is_etf`
   - `exchanges`: `code` (to filter allowed exchanges)
   - `prices`: `ticker_id`, `date`, `adj_close`, `volume` (for last_close, avg_volume_30d)
   - **Computed**: `avg_volume_30d` via window function over prices
   - **Flags**: Infer `is_penny_stock` from `last_close`, `is_adr` from symbol suffix, `is_otc` from exchange

2. **Stage 2.2 (Quality Filter)** reads:
   - `factors`: `ticker_id`, `as_of_date`, `roce`, `revenue_growth_5y`, `gross_margin`, `debt_to_equity`, `fcf_yield`
   - **Fallback**: If `factors` empty, compute from `fundamentals` once and persist to `factors`

3. **Stage 2.3 (Business Filter)** reads:
   - `fundamentals`: Historical rows (5 years) for `ticker_id`, `period_end`, `free_cash_flow`, `gross_profit`, `operating_cash_flow`
   - **Computed metrics** (persist to `factors` if missing):
     - `positive_fcf_years`: Count of positive FCF in last 5 years
     - `cumulative_5yr_fcf`: Sum of FCF over 5 years
     - `margin_volatility`: Stddev of gross_margin over 5 years
     - `reinvestment_rate`: (capex + R&D) / gross_profit (if available)

**Missing Data Handling:**
- If `factors` table empty → compute from `fundamentals` and backfill
- If `fundamentals` has <5 years data → use available years, flag in logs
- If critical fields NULL → reject ticker with reason "insufficient_data"

### Design Choices

**SQL vs. Pandas:**

1. **Stage 2.1**: Single SQL query with window function for `avg_volume_30d`, join `tickers`/`exchanges`/`prices`
   - Rationale: DB is faster for large joins; avoid loading 5000 × 30 days of prices into memory
   - Output: DataFrame with survivors

2. **Stage 2.2**: Single SQL join of Stage 2.1 survivors with `factors` table
   - Rationale: Simple threshold filters; SQL WHERE clause is optimal
   - Fallback: If `factors` empty, run backfill query once, persist, then re-run filter

3. **Stage 2.3**:
   - First: SQL to fetch 5 years of `fundamentals` for Stage 2.2 survivors
   - Then: Pandas vectorized operations for per-ticker aggregations (count, sum, stddev)
   - Rationale: Complex aggregations easier in pandas; dataset small (~100 tickers × 5 years = 500 rows)

**as_of Propagation:**
- `--as-of` parameter → query `prices WHERE date <= as_of` for last_close
- All window functions constrained to `date <= as_of`
- Logged in `runs.month_year` and `runs.parameters` as JSON
- CSV filenames include `as_of`: `stage1_fast_2025-11.csv`

**First-Failing Rule Recording:**
- Evaluate rules sequentially
- On first failure: record `reason = "rule_name:threshold"` (e.g., `"min_price:5.0"`)
- Use pandas `.apply()` with early-exit logic per ticker
- Store in `decisions.reason` column

**Config Schema:**
```yaml
screen:
  fast:
    allowed_exchanges: ["NYSE", "NASDAQ", "NSE"]
    min_price_usd: 5.0
    min_price_inr: 100.0
    min_adv: 100000  # average daily volume
    min_market_cap: 100000000  # $100M
    exclude_etf: true
    exclude_adr: true
    exclude_otc: true
    exclude_penny: true

  quality:
    min_roce: 15.0  # %
    min_revenue_cagr_5y: 10.0  # %
    min_gross_margin: 20.0  # %
    max_debt_to_equity: 1.0
    min_fcf_margin: 5.0  # % (optional)

  business:
    min_positive_fcf_years: 3  # out of 5
    min_cumulative_5yr_fcf: 0  # must be positive
    max_margin_volatility: 10.0  # % stddev
    min_reinvestment_rate: 5.0  # % (optional)
    max_reinvestment_rate: 50.0  # % (optional)
```

### Minimal Plan (Small Steps)

**Step 1: Common Utilities** (20 min)
- [ ] `screens/common.py`: Rule evaluator with first-fail tracking
- [ ] `screens/common.py`: Summary table printer
- [ ] `screens/common.py`: CSV writer with as_of in filename

**Step 2: Stage 2.1 - Quick Screener** (30 min)
- [ ] `screens/fast.py`: SQL query for avg_volume_30d + filters
- [ ] `screens/fast.py`: Apply config thresholds
- [ ] `screens/fast.py`: Write CSV + DB logging

**Step 3: Stage 2.2 - Quality Filter** (25 min)
- [ ] `screens/quality.py`: Join survivors with factors table
- [ ] `screens/quality.py`: Threshold filters from config
- [ ] `screens/quality.py`: Backfill logic if factors empty (defer to separate task)

**Step 4: Stage 2.3 - Business Filter** (35 min)
- [ ] `screens/business.py`: Fetch 5yr fundamentals for survivors
- [ ] `screens/business.py`: Vectorized aggregations (count, sum, stddev)
- [ ] `screens/business.py`: Consistency checks + write outputs

**Step 5: CLI Wiring** (15 min)
- [ ] `cli/main.py`: Add `screen` command group
- [ ] Subcommands: `fast`, `quality`, `business`, `all`
- [ ] Parameters: `--as-of`, `--output-dir`, `--config-path`

**Step 6: Smoke Tests** (20 min)
- [ ] `tests/fixtures/screening_test.db`: Tiny DB with 50 tickers
- [ ] `tests/test_screening.py`: Test each stage independently
- [ ] Assert: survivor counts, CSV exists, DB writes

**Step 7: Config File** (10 min)
- [ ] Update `config.example.yml` with `screen.*` section
- [ ] Defaults match PRD targets (~10%, ~2%, ~0.6%)

**Total Estimate: ~2.5 hours**

---

## Implementation Notes

**Reversibility:**
- Each stage is independent function: `screen_fast(tickers_df, config) -> survivors_df`
- Can roll back by removing `screens/` module
- DB writes transactional (commit only on success)

**Testing Strategy:**
- Unit: Each rule function with boundary cases (threshold ±0.01)
- Integration: Full pipeline with 50-ticker fixture → expect ~5, ~1, ~0 survivors
- Smoke: Run against empty DB → graceful failure with warning

**Performance Targets:**
- Stage 2.1: <30s for 5000 tickers (PRD requirement)
- Stage 2.2: <5s for 500 tickers
- Stage 2.3: <10s for 100 tickers (pandas aggregations)
- **Total pipeline: <45s**

---

## Expected Outputs

### Stage 2.1 Results (Quick Screener)
```
Survivors: 487
Removed by rule:
  inactive: 234
  exchange_not_allowed: 156
  below_min_price: 1,234
  below_min_adv: 2,345
  below_min_market_cap: 456
  is_etf: 67
  is_adr: 21
Runtime: 12.3s
CSV: snapshots/2025-11/stage1_fast_2025-11.csv
```

### Stage 2.2 Results (Quality Filter)
```
Survivors: 93
Removed by rule:
  roce_below_15: 234
  revenue_growth_below_10: 123
  gross_margin_below_20: 45
  debt_to_equity_above_1: 12
Runtime: 3.2s
CSV: snapshots/2025-11/stage2_quality_2025-11.csv
```

### Stage 2.3 Results (Business Filter)
```
Survivors: 28
Removed by rule:
  insufficient_positive_fcf_years: 34
  negative_5yr_fcf: 18
  high_margin_volatility: 13
Runtime: 6.7s
CSV: snapshots/2025-11/stage3_business_2025-11.csv
```

---

**Next Actions**: Proceed with implementation in order of plan.
