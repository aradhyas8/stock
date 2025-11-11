# Phase 7: Scheduling, Ops & Performance Analytics

## Overview

Add operational automation (monthly/daily runners, health checks, snapshot rotation) and comprehensive performance analytics (returns, risk metrics, attribution) using only local DB and snapshot data.

---

## Module Structure

```
src/multibagger/
├── ops/
│   ├── __init__.py
│   ├── runner.py      # Monthly/daily orchestration
│   ├── health.py      # System health validation
│   └── rotation.py    # Snapshot cleanup
└── analytics/
    ├── __init__.py
    ├── compute.py     # Performance calculations
    └── report.py      # Report generation
```

---

## Ops Module

### 1. ops run monthly

**Purpose:** Orchestrate full monthly pipeline

**Command:**
```bash
ops run monthly --as-of YYYY-MM [--dry-run]
```

**Steps:**
1. Run universe build (if needed)
2. Run all screen stages (fast → quality → business → redflags → research)
3. Run portfolio reconciliation
4. Generate health check
5. Emit `ops_monthly_metrics.json`

**Outputs:**
- `snapshots/YYYY-MM/ops_monthly_metrics.json`
- Standard stage outputs in `snapshots/YYYY-MM/`

**Determinism:**
- Fixed as-of date
- No wall-clock timestamps in filenames
- Stable ordering in metrics JSON

### 2. ops run daily

**Purpose:** Daily monitoring wrapper

**Command:**
```bash
ops run daily [--date YYYY-MM-DD] [--as-of YYYY-MM] [--dry-run]
```

**Steps:**
1. Call existing `monitor daily`
2. Validate outputs
3. Emit `ops_daily_metrics.json`

**Outputs:**
- `snapshots/YYYY-MM/alerts/ops_daily_metrics_{YYYY-MM-DD}.json`
- Wraps existing monitor outputs

### 3. ops health

**Purpose:** Validate system state

**Command:**
```bash
ops health [--as-of YYYY-MM] [--date YYYY-MM-DD]
```

**Checks:**

| Check | Source | Green Criteria |
|-------|--------|----------------|
| **Universe Size** | `tickers` table | 4500-5500 active tickers |
| **Stage Outputs** | CSV files | All stages present |
| **Stage Counts** | CSV row counts | Within expected ranges |
| **Research Coverage** | `research` table | 80%+ survivors have research |
| **Red Flag Coverage** | `risk_flags` table | 100% survivors have flags |
| **Portfolio Run** | `portfolio_runs` | Run exists for as_of |
| **Price Freshness** | `prices` table | Latest price within 7 days |
| **Snapshot Integrity** | File existence | All required files present |

**Status Logic:**
- **GREEN**: All checks pass
- **YELLOW**: Non-critical issues (e.g., price slightly stale, research coverage 70-80%)
- **RED**: Critical issues (missing stages, no portfolio run, price >30 days old)

**Outputs:**
- Console: Rich table with status
- `snapshots/YYYY-MM/health_check_{YYYY-MM}.json`

### 4. ops rotate

**Purpose:** Prune old snapshots safely

**Command:**
```bash
ops rotate --keep-months N --keep-alert-days M [--dry-run]
```

**Safety Rules:**
1. Never delete current month (YYYY-MM == today's month)
2. Never delete if portfolio positions reference it
3. Keep most recent N months
4. Keep alert files for M days

**Process:**
1. Scan `snapshots/` directory
2. Identify candidates for deletion (older than keep period)
3. Check safety constraints
4. Preview deletions (if dry-run) OR execute
5. Emit `rotation_report.json`

**Outputs:**
- `rotation_report_{timestamp}.json`
  ```json
  {
    "executed_at": "2025-12-01T10:00:00",
    "dry_run": false,
    "candidates": ["2024-01", "2024-02"],
    "deleted": ["2024-01"],
    "skipped": [{"month": "2024-02", "reason": "Referenced by portfolio"}],
    "space_freed_mb": 250.5
  }
  ```

---

## Analytics Module

### Inputs (Local Only)

**Portfolio Positions:**
- `portfolio_positions` table (run_id, ticker_id, weight_pct)
- `stage_research_{YYYY-MM}.csv` (fallback for older snapshots)

**Prices:**
- `prices` table (ticker_id, date, adj_close)
- Benchmark: SPY prices from same table

**Time Window:**
- `--window 36` = 36 months back from --as-of
- Load all monthly positions + prices in single query

### Calculations (Vectorized)

#### 1. Portfolio Returns

**Monthly Return Calculation:**
```
For each month t:
  - Load portfolio weights from portfolio_positions (or CSV)
  - Get month-end prices for all positions
  - Compute position returns: (price_t / price_{t-1} - 1)
  - Weighted portfolio return: Σ(weight_i * return_i)
  - Account for turnover cost: subtract (turnover_pct * slippage_bps / 10000)
```

**Cumulative:**
```
cumulative_return = ∏(1 + monthly_return_i) - 1
```

**CAGR:**
```
CAGR = (1 + cumulative_return)^(12/months) - 1
```

#### 2. Risk Metrics

**Volatility:**
```
volatility = std(monthly_returns) * sqrt(12)  # Annualized
```

**Max Drawdown:**
```
For each month:
  - cumulative_value = 100 * ∏(1 + return_i)
  - running_max = max(cumulative_value to date)
  - drawdown = (cumulative_value / running_max - 1)
max_drawdown = min(drawdowns)
```

**Sharpe Ratio (assume 0% risk-free):**
```
sharpe = (mean_return * 12) / volatility
```

**Calmar Ratio:**
```
calmar = CAGR / abs(max_drawdown)
```

#### 3. Benchmark Comparison (CAPM-lite)

**Load SPY returns (if available):**
- Query `prices WHERE ticker_id = (SELECT id FROM tickers WHERE symbol = 'SPY')`

**OLS Regression:**
```
portfolio_returns = alpha + beta * benchmark_returns + epsilon

beta = cov(portfolio_returns, benchmark_returns) / var(benchmark_returns)
alpha = mean(portfolio_returns) - beta * mean(benchmark_returns)
R² = explained variance
```

**Information Ratio:**
```
active_return = portfolio_return - benchmark_return
tracking_error = std(active_returns) * sqrt(12)
information_ratio = (mean(active_returns) * 12) / tracking_error
```

#### 4. Hit Rates

**For each position at time t:**
- Check returns at t+3, t+6, t+12 months
- Hit = (position_return > benchmark_return)

**Aggregate:**
```
hit_rate_3m = count(hits) / count(positions)
hit_rate_6m = ...
hit_rate_12m = ...
```

#### 5. Attribution

**By Position:**
```
contribution_i = weight_i * return_i
```

**By Turnover:**
```
turnover_cost = Σ|weight_t - weight_{t-1}| * slippage_bps / 10000
```

**Top Contributors/Detractors:**
- Sort by contribution DESC
- Report top 5 and bottom 5

### Outputs (Deterministic)

#### 1. analytics_{YYYY-MM}.json

```json
{
  "as_of": "2025-11",
  "window_months": 36,
  "start_date": "2022-12",
  "end_date": "2025-11",
  "benchmark": "SPY",
  
  "returns": {
    "total_return_pct": 48.5,
    "cagr_pct": 14.2,
    "volatility_pct": 18.3,
    "sharpe_ratio": 0.78,
    "calmar_ratio": 0.85
  },
  
  "risk": {
    "max_drawdown_pct": -16.7,
    "max_drawdown_date": "2024-03",
    "recovery_months": 4
  },
  
  "benchmark_comparison": {
    "benchmark_total_return_pct": 35.2,
    "alpha_pct": 1.2,
    "beta": 1.15,
    "r_squared": 0.82,
    "information_ratio": 0.45
  },
  
  "hit_rates": {
    "hit_rate_3m": 0.62,
    "hit_rate_6m": 0.58,
    "hit_rate_12m": 0.55
  },
  
  "attribution": {
    "top_contributors": [
      {"symbol": "NVDA", "contribution_pct": 12.3},
      {"symbol": "MSFT", "contribution_pct": 8.7}
    ],
    "top_detractors": [
      {"symbol": "IBM", "contribution_pct": -3.2}
    ],
    "avg_turnover_pct": 25.4,
    "turnover_cost_pct": -0.25
  },
  
  "metadata": {
    "positions_analyzed": 125,
    "months_with_data": 36,
    "benchmark_available": true,
    "config": {
      "slippage_bps": 10,
      "lookback_months": 36
    }
  }
}
```

#### 2. analytics_{YYYY-MM}.csv

Time series data:
```csv
date,portfolio_value,portfolio_return_pct,benchmark_value,benchmark_return_pct,active_return_pct,drawdown_pct,positions
2022-12,100.0,0.0,100.0,0.0,0.0,0.0,7
2023-01,102.3,2.3,101.5,1.5,0.8,0.0,7
2023-02,104.8,2.4,102.8,1.3,1.1,0.0,7
...
```

#### 3. analytics_report_{YYYY-MM}.md

```markdown
# Portfolio Performance Report - 2025-11

## Summary
- **Period:** 2022-12 to 2025-11 (36 months)
- **Total Return:** 48.5%
- **CAGR:** 14.2%
- **Volatility:** 18.3%
- **Max Drawdown:** -16.7%

## Benchmark Comparison (SPY)
- **Benchmark Return:** 35.2%
- **Outperformance:** +13.3%
- **Alpha:** 1.2% annually
- **Beta:** 1.15
- **Information Ratio:** 0.45

## Risk Metrics
- **Sharpe Ratio:** 0.78
- **Calmar Ratio:** 0.85
- **Max Drawdown:** -16.7% (2024-03)

## Hit Rates
- **3-month:** 62%
- **6-month:** 58%
- **12-month:** 55%

## Top Contributors
1. NVDA: +12.3%
2. MSFT: +8.7%

## Top Detractors
1. IBM: -3.2%

---
*Data sources: Local DB (portfolio_positions, prices), Snapshots (stage CSVs)*
```

---

## Configuration

Extend `config.example.yml`:

```yaml
ops:
  timezone: "America/Toronto"
  retention:
    months_to_keep: 12
    days_to_keep_alerts: 90
  
  health:
    universe_size_min: 4500
    universe_size_max: 5500
    research_coverage_min: 0.80
    price_staleness_warn_days: 7
    price_staleness_error_days: 30

analytics:
  lookback_months: 36
  bench_symbols: ["SPY"]
  slippage_bps: 10
  
  hit_rate_windows: [3, 6, 12]  # months
  
  attribution:
    top_n_positions: 5
```

---

## Determinism Rules

1. **Sorting:**
   - Time series: by date ASC
   - Positions: by symbol ASC (or ticker_id ASC)
   - Attribution: by contribution DESC, then symbol ASC

2. **Rounding:**
   - Percentages: 2 decimals (14.23%)
   - Prices: 4 decimals ($123.4567)
   - Ratios: 2 decimals (0.78)

3. **Timestamps:**
   - Output filenames: YYYY-MM or YYYY-MM-DD only
   - Metadata: ISO format with fixed timezone

4. **Ordering:**
   - JSON keys: alphabetical
   - CSV columns: fixed order

---

## Batch Processing

### SQL Patterns

**Load Position History (36 months):**
```sql
WITH monthly_runs AS (
    SELECT id, as_of_date
    FROM portfolio_runs
    WHERE as_of_date >= :start_date AND as_of_date <= :end_date
    ORDER BY as_of_date
)
SELECT 
    r.as_of_date,
    pp.ticker_id,
    t.symbol,
    pp.weight_pct
FROM monthly_runs r
JOIN portfolio_positions pp ON pp.run_id = r.id
JOIN tickers t ON t.id = pp.ticker_id
ORDER BY r.as_of_date, pp.ticker_id
```

**Load Price History (Single Query):**
```sql
WITH month_ends AS (
    SELECT DISTINCT date(as_of_date, 'start of month', '+1 month', '-1 day') as month_end
    FROM portfolio_runs
    WHERE as_of_date >= :start_date AND as_of_date <= :end_date
),
latest_prices_per_month AS (
    SELECT 
        ticker_id,
        date,
        adj_close,
        ROW_NUMBER() OVER (
            PARTITION BY ticker_id, strftime('%Y-%m', date)
            ORDER BY date DESC
        ) as rn
    FROM prices
    WHERE date >= :start_date AND date <= :end_date
)
SELECT ticker_id, date, adj_close
FROM latest_prices_per_month
WHERE rn = 1
ORDER BY date, ticker_id
```

**Vectorized Returns (Pandas):**
```python
# Load positions and prices in bulk
positions_df = load_positions_batch(...)  # Single SQL query
prices_df = load_prices_batch(...)        # Single SQL query

# Pivot for vectorized operations
price_matrix = prices_df.pivot(index='date', columns='ticker_id', values='adj_close')
position_matrix = positions_df.pivot(index='date', columns='ticker_id', values='weight_pct')

# Vectorized returns
returns = price_matrix.pct_change()

# Weighted portfolio returns
portfolio_returns = (returns * position_matrix).sum(axis=1)
```

---

## Safety Guardrails

### Rotation Safety

1. **Never delete current month:**
   ```python
   current_month = datetime.now().strftime('%Y-%m')
   if candidate == current_month:
       skip(reason="Current month")
   ```

2. **Check references:**
   ```python
   # Check if any portfolio positions reference this month
   if has_portfolio_positions(candidate):
       skip(reason="Referenced by portfolio")
   ```

3. **Dry-run preview:**
   ```python
   if dry_run:
       print_preview(candidates)
       return
   ```

4. **Audit trail:**
   ```python
   rotation_report = {
       "executed_at": timestamp,
       "dry_run": False,
       "deleted": [...],
       "skipped": [{"month": "2024-01", "reason": "..."}]
   }
   save_json(rotation_report)
   ```

### Health Check Warnings

- **YELLOW:** Warn but don't fail
- **RED:** Log error but don't crash
- Always emit JSON report

---

## Reusable Utilities

From existing codebase:

1. **SQL Helpers:**
   - `build_in_clause_params()` from `common/sql_utils.py`

2. **Config:**
   - `Config` class from `config.py`

3. **CLI:**
   - Rich `Console`, `Table` from existing patterns
   - `typer.Option` patterns

4. **Database:**
   - `get_engine()`, `Session` from `database/schema.py`

---

## Testing Strategy

### Unit Tests

- `tests/test_ops_health.py` - Health check logic
- `tests/test_ops_rotation.py` - Rotation logic with mocks
- `tests/test_analytics_compute.py` - Return/risk calculations

### Integration Tests

- Run on test fixtures with known outputs
- Verify determinism (run twice, compare hashes)

### Validation

```bash
# Health check
uv run python -m multibagger.cli.main ops health --as-of 2025-11

# Analytics (dry-run)
uv run python -m multibagger.cli.main analytics compute --as-of 2025-11 --dry-run

# Analytics (real)
uv run python -m multibagger.cli.main analytics compute --as-of 2025-11

# Verify determinism
sha256sum snapshots/2025-11/analytics/analytics_2025-11.json
# Run again
uv run python -m multibagger.cli.main analytics compute --as-of 2025-11
sha256sum snapshots/2025-11/analytics/analytics_2025-11.json
# Hashes should match
```

---

## Limitations & Assumptions

### Analytics

1. **No Intraday Data:** Use month-end prices only
2. **No Transaction Costs:** Model assumes perfect execution at month-end
3. **Survivorship Bias:** Only analyzes positions that existed at each rebalance
4. **Benchmark Availability:** If SPY not in DB, skip benchmark comparison
5. **Risk-Free Rate:** Assumes 0% for Sharpe calculation
6. **Attribution:** Simple contribution analysis, not factor-based

### Health Checks

1. **Ranges:** Hard-coded ranges may need adjustment
2. **Freshness:** 7-day staleness may be too strict for monthly-only systems

### Rotation

1. **Space Calculation:** Approximate (file sizes only, not DB)
2. **No Undo:** Once deleted, snapshots are gone (encourage backups)

---

## Next Steps (Post-Implementation)

1. **Scheduling:**
   - Cron jobs for monthly/daily runs
   - Email alerts for RED health status

2. **Enhanced Analytics:**
   - Factor attribution (value/growth/momentum)
   - Sector allocation vs benchmark
   - Holdings-based vs transaction-based attribution

3. **Monitoring:**
   - Prometheus metrics export
   - Grafana dashboards

---

## Summary

Phase 7 adds:
- ✅ Operational automation (runners, health, rotation)
- ✅ Comprehensive analytics (returns, risk, attribution)
- ✅ Deterministic, batch-first processing
- ✅ Safety guardrails (dry-run, never delete current)
- ✅ Local-only (no network calls)

**Ready for implementation.**
