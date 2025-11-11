# Daily Portfolio Monitoring

Batch-first, deterministic alert generation from local DB data.

## Overview

The daily monitor reads persisted portfolio positions (Phase 5.1) and compares them against latest prices to generate alerts for:

- **STOP_LOSS**: Price breaches downside protection
- **NEAR_TARGET**: Price approaching DCF fair value (90%)
- **THESIS_RISK**: New red flags or declining upside (<5%)

**Key Features:**
- ✅ Batch queries only - no per-ticker network calls
- ✅ Deterministic outputs (same DB + date → identical results)
- ✅ Vectorized signal computation
- ✅ Rich CLI output with tables

---

## Inputs

The monitor loads data from these tables in a single batch query:

### Primary Tables

1. **portfolio_runs** - Latest portfolio snapshot (or --as-of YYYY-MM)
2. **portfolio_positions** - Target positions with weights, prices, targets
3. **tickers** - Symbol names
4. **prices** - Latest adj_close <= --date (window function, no loops)
5. **research** - Target prices and upside from DCF models
6. **risk_flags** - New red flags since run.as_of_date

### Query Logic

```sql
WITH latest_prices AS (
    SELECT ticker_id, adj_close, date,
           ROW_NUMBER() OVER (PARTITION BY ticker_id ORDER BY date DESC) as rn
    FROM prices
    WHERE date <= :price_date
),
new_red_flags AS (
    SELECT ticker_id, COUNT(*) as flag_count, GROUP_CONCAT(first_fail_reason) as reasons
    FROM risk_flags
    WHERE as_of_date > :run_as_of AND as_of_date <= :price_date
          AND first_fail_reason IS NOT NULL
    GROUP BY ticker_id
)
SELECT ... FROM portfolio_runs
JOIN portfolio_positions ...
JOIN tickers ...
LEFT JOIN latest_prices ON ... AND rn = 1
LEFT JOIN research ...
LEFT JOIN new_red_flags ...
```

**No loops, no per-ticker queries.**

---

## Signal Rules

### 1. STOP_LOSS (Severity: HIGH)

**Condition:** `current_price <= stop_loss_price`

**Stop Loss Price:**
- Use `position.stop_loss_price` if set
- Otherwise: `entry_price * (1 + stop_loss_pct)` (default: -25%)

**Example:**
```
Entry: $100
Stop: $75 (explicit or default)
Current: $70
→ STOP_LOSS alert: "Price $70.00 ≤ stop $75.00 (-30.0% loss)"
```

### 2. NEAR_TARGET (Severity: MEDIUM)

**Condition:** `current_price >= target_price * near_target_pct`

**Target Price:**
- Use `position.target_price` if set
- Otherwise: `research.base_fair_value`

**Example:**
```
Entry: $50
Target: $150
Current: $135
→ NEAR_TARGET alert: "Price $135.00 is 90.0% of target $150.00"
```

### 3. THESIS_RISK (Severity: MEDIUM)

**Conditions (any):**
- New red flags detected since portfolio run date
- Current upside < `min_upside_pct` (default: 5%)

**Upside Calculation:** `(target_price / current_price - 1)`

**Example:**
```
Target: $150
Current: $145
Upside: 3.4% < 5.0%
→ THESIS_RISK alert: "Upside 3.4% < 5.0%"
```

**Or:**
```
New red flags: 1 (beneish_m_score_high)
→ THESIS_RISK alert: "1 new red flag(s): beneish_m_score_high"
```

---

## Outputs

### 1. Alerts CSV

**Path:** `snapshots/YYYY-MM/alerts/portfolio_alerts_YYYY-MM-DD.csv`

**Columns:**
```
as_of,price_date,ticker_id,symbol,signal,current_price,entry_price,
target_price,stop_loss_price,held_weight_pct,reason
```

**Sorting (Deterministic):**
1. Signal severity: STOP_LOSS → THESIS_RISK → NEAR_TARGET
2. Weight DESC (largest positions first)
3. Ticker ID ASC (stable tie-breaker)

**Example:**
```csv
as_of,price_date,ticker_id,symbol,signal,current_price,entry_price,target_price,stop_loss_price,held_weight_pct,reason
2025-12-01,2025-12-15,2000,STOP,STOP_LOSS,70.0,100.0,150.0,75.0,30.0,"Price $70.00 ≤ stop $75.00 (-30.0% loss)"
2025-12-01,2025-12-15,2001,TARGET,NEAR_TARGET,135.0,50.0,150.0,37.5,40.0,"Price $135.00 is 90.0% of target $150.00"
```

### 2. Metrics JSON

**Path:** `snapshots/YYYY-MM/alerts/monitor_metrics_YYYY-MM-DD.json`

**Structure:**
```json
{
  "date": "2025-12-15",
  "portfolio_as_of": "2025-12",
  "price_date": "2025-12-15",
  "positions_checked": 7,
  "total_alerts": 2,
  "signal_counts": {
    "STOP_LOSS": 1,
    "NEAR_TARGET": 1
  },
  "tickers_with_multiple_signals": 0,
  "multi_signal_ticker_ids": [],
  "config": {
    "near_target_pct": 0.9,
    "stop_loss_pct": -0.25,
    "min_upside_pct": 0.05
  }
}
```

---

## Configuration

Add to `config.yml`:

```yaml
monitoring:
  # Signal thresholds
  near_target_pct: 0.90              # Alert when current >= target * 0.90
  stop_loss_pct: -0.25               # Default stop loss: entry * 0.75
  min_upside_pct: 0.05               # Thesis risk if upside < 5%

  # Active signals
  signals:
    - STOP_LOSS
    - NEAR_TARGET
    - THESIS_RISK
```

---

## CLI Usage

### Basic (Latest Portfolio + Latest Prices)

```bash
uv run python -m multibagger.cli.main monitor daily
```

**Defaults:**
- Portfolio: Latest `portfolio_runs.as_of_date`
- Price Date: `MAX(prices.date)`

### Specify Date

```bash
uv run python -m multibagger.cli.main monitor daily --date 2025-12-15
```

### Specify Portfolio Run

```bash
uv run python -m multibagger.cli.main monitor daily --as-of 2025-11
```

### Dry Run (No File Writes)

```bash
uv run python -m multibagger.cli.main monitor daily --dry-run
```

### Full Example

```bash
uv run python -m multibagger.cli.main monitor daily \
  --date 2025-12-15 \
  --as-of 2025-12 \
  --output-dir snapshots \
  --dry-run
```

---

## CLI Output Example

```
🔍 Portfolio Monitoring

Portfolio as of: 2025-12
Price date: 2025-12-15
Positions checked: 7

          Alert Summary
┏━━━━━━━━━━━━━┳━━━━━━━┓
┃ Signal      ┃ Count ┃
┡━━━━━━━━━━━━━╇━━━━━━━┩
│ STOP_LOSS   │     1 │
│ NEAR_TARGET │     1 │
└─────────────┴───────┘

                Detailed Alerts
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Symbol ┃ Signal      ┃ Current ┃ Entry ┃ Target ┃ Weight% ┃ Reason           ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ STOP   │ STOP_LOSS   │  $70.00 │$100.00│ $150.00│     30.0│ Price $70.00 ≤...│
│ TARGET │ NEAR_TARGET │ $135.00 │ $50.00│ $150.00│     40.0│ Price $135.00 ...│
└────────┴─────────────┴─────────┴───────┴────────┴─────────┴──────────────────┘

Outputs:
  Alerts CSV: snapshots/2025-12/alerts/portfolio_alerts_2025-12-15.csv
  Metrics JSON: snapshots/2025-12/alerts/monitor_metrics_2025-12-15.json

✅ Monitoring complete
```

---

## Idempotency

**Same DB state + same --date → identical outputs**

The system is deterministic:
- Stable sorting (signal priority, weight DESC, ticker_id ASC)
- Fixed date comparisons (no wall-clock timestamps)
- Batch queries with explicit ordering

Running twice with same inputs produces:
- Identical CSV content (same rows, same order)
- Identical JSON metrics

---

## Testing

### Run Tests

```bash
uv run pytest tests/test_monitor_daily.py -v
```

### Test Fixtures

The test suite creates 3 positions:
1. **STOP** - Hits stop loss (entry $100, current $70, stop $75)
2. **TARGET** - Near target (entry $50, current $135, target $150)
3. **CLEAN** - No alerts (entry $100, current $110, target $150)

### Test Coverage

- ✅ Batch loading of positions
- ✅ Signal computation (vectorized)
- ✅ Determinism (identical outputs)
- ✅ End-to-end integration
- ✅ Dry-run mode
- ✅ File output validation
- ✅ Metrics accuracy

---

## Edge Cases

### Missing Data

**No Portfolio Runs**
```
❌ ValueError: No portfolio runs found in database
Run 'portfolio reconcile' first.
```

**No Prices for Date**
```
⚠️  No price data for AAPL (ticker_id=1000)
Skipped from alerts.
```

**Missing Target Price**
- Falls back to `research.base_fair_value`
- If both missing: NEAR_TARGET signal skipped

**Missing Stop Loss**
- Uses default: `entry_price * (1 + stop_loss_pct)`
- Default: -25% (configurable)

### Multiple Signals

A position can trigger multiple signals simultaneously:

**Example:**
```
AAPL:
- STOP_LOSS: Price $70 ≤ stop $75
- THESIS_RISK: 1 new red flag (beneish_m_score_high)
```

Metrics JSON tracks:
```json
{
  "tickers_with_multiple_signals": 1,
  "multi_signal_ticker_ids": [1000]
}
```

---

## Architecture

### Data Flow

```
1. Load Portfolio Run (latest or --as-of)
   ↓
2. Batch Query:
   - Positions + Tickers
   - Latest Prices (window function)
   - Research Targets
   - New Red Flags
   ↓
3. Compute Signals (vectorized)
   - Stop Loss Check
   - Near Target Check
   - Thesis Risk Check
   ↓
4. Sort Alerts (deterministic)
   ↓
5. Save Outputs
   - CSV: portfolio_alerts_{date}.csv
   - JSON: monitor_metrics_{date}.json
```

### No Network Calls

The monitor uses **only local DB data**:
- Positions from `portfolio_positions`
- Prices from `prices` table (cached/historical)
- Research from `research` table
- Risk flags from `risk_flags` table

**No API calls, no HTTP requests.**

---

## Next Steps

### Future Enhancements (Optional)

1. **Append-Only History**
   - `alerts_history.csv` with all alerts over time
   - Track alert duration, resolution

2. **Email/Slack Notifications**
   - Send STOP_LOSS alerts immediately
   - Daily digest for NEAR_TARGET

3. **Alert Deduplication**
   - Track when alert first triggered
   - Suppress repeated alerts for same condition

4. **Performance Metrics**
   - Alert accuracy (true positives vs false positives)
   - Time-to-resolution

---

## Troubleshooting

### No Alerts When Expected

**Check:**
1. Portfolio run exists: `SELECT * FROM portfolio_runs ORDER BY as_of_date DESC LIMIT 1`
2. Prices loaded: `SELECT MAX(date) FROM prices`
3. Config thresholds: `monitoring.near_target_pct`, `stop_loss_pct`, `min_upside_pct`

### Unexpected Alerts

**Debug:**
```python
# Run with logging
import logging
logging.getLogger('multibagger.monitor').setLevel(logging.DEBUG)
```

**Check signal computation:**
```python
from multibagger.monitor.daily import compute_signals

# positions_df has current_price, entry_price, target_price
print(positions_df[['symbol', 'current_price', 'entry_price', 'target_price', 'stop_loss_price']])

# Run signal computation
alerts_df = compute_signals(positions_df, config['monitoring'])
print(alerts_df)
```

### Performance Issues

**Optimization:**
- Ensure indexes exist: `CREATE INDEX IF NOT EXISTS ix_prices_ticker_date ON prices(ticker_id, date DESC)`
- Check query plan: `EXPLAIN QUERY PLAN SELECT ...`
- Batch size: Monitor handles portfolios up to ~100 positions efficiently

---

## Summary

The daily monitor is:
- ✅ **Batch-first**: Single query loads all data
- ✅ **Deterministic**: Same inputs → identical outputs
- ✅ **Explainable**: Clear alert reasons
- ✅ **Fast**: No network calls, vectorized computation
- ✅ **Tested**: Comprehensive test coverage
- ✅ **CLI-friendly**: Rich output, dry-run support

Ready for daily production use.
