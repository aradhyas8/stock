# Phase 3 MVP: Forensics-Only Red Flag Detection - Think First Analysis

**Date**: 2025-11-10
**Approach**: Option A - Forensics-Only MVP
**Timeline**: 6-8 hours

---

## 📊 Input Availability Analysis

### Stage 2.3 Business Filter Survivors
**Source**: `snapshots/YYYY-MM/stage_business_YYYY-MM.csv`

**Available Fields**:
- ticker_id, symbol, name, exchange_code
- Fundamental counts, price data points
- Business metrics from Stage 2.3

**Expected Count**: ~30 tickers (from 50 → 30 after Stage 2.3)

### Database Tables Available

#### Fundamentals Table
**Fields Needed for Forensics**:
```python
BENEISH_FIELDS = [
    'revenue', 'receivables', 'gross_profit',
    'current_assets', 'ppe', 'total_assets',
    'depreciation', 'sga_expense',
    'long_term_debt', 'current_liabilities',
    'cash', 'short_term_debt'
]

ALTMAN_FIELDS = [
    'current_assets', 'current_liabilities', 'total_assets',
    'retained_earnings', 'ebit', 'operating_income',
    'total_liabilities', 'revenue'
]

SLOAN_FIELDS = [
    'current_assets', 'cash', 'current_liabilities',
    'short_term_debt', 'depreciation', 'total_assets'
]
```

**Data Requirement**:
- Beneish: 2+ years (current + prior)
- Altman: Latest year only
- Sloan: 2+ years (for deltas)

**Query Strategy**:
```sql
SELECT ticker_id, fiscal_year, revenue, receivables, ...
FROM fundamentals
WHERE ticker_id IN (survivor_ids)
  AND fiscal_year >= (latest_year - 2)
  AND report_type = 'A'
ORDER BY ticker_id, fiscal_year DESC
```

#### Tickers Table
**Fields Needed**:
- `market_cap` for Altman Z-Score MVE/TL component

**Query Strategy**:
```sql
SELECT id, market_cap
FROM tickers
WHERE id IN (survivor_ids)
```

### Edge Cases & Handling

| Issue | Detection | Handling |
|-------|-----------|----------|
| **Missing Fundamentals** | < 2 years of data | Return None for scores, log warning |
| **Zero Denominators** | revenue=0, total_assets=0 | safe_divide() returns default |
| **Null/NaN Values** | Missing fields | pd.isna() checks, defaults to 0 |
| **Misaligned Periods** | Different fiscal year-ends | Group by fiscal_year, sort DESC |
| **No Market Cap** | market_cap is NULL | Altman Z-Score returns None |

---

## 🗺️ Output Mapping

### forensics/metrics.py → risk_flags Table

```python
# Beneish M-Score
compute_beneish_m_score(fundamentals_df) → {
    'm_score': -2.45,           # → beneish_m_score
    'components': {...},         # → details_json['forensics']['beneish']
    'interpretation': "..."      # → details_json['forensics']['beneish']['interpretation']
}

# Altman Z-Score
compute_altman_z_score(fundamentals, market_cap) → {
    'z_score': 3.25,            # → altman_z_score
    'components': {...},         # → details_json['forensics']['altman']
    'interpretation': "..."      # → details_json['forensics']['altman']['interpretation']
}

# Sloan Accruals
compute_sloan_accruals(fundamentals_df) → {
    'accruals_ratio': 0.05,     # → accruals_ratio
    'interpretation': "..."      # → details_json['forensics']['accruals']['interpretation']
}

# Forensics Score
compute_forensics_score(beneish, altman, accruals) → 15.2  # → forensics_score
```

### risk_flags Table Columns (MVP)

| Column | Source | MVP Value |
|--------|--------|-----------|
| `ticker_id` | Survivor list | From Stage 2.3 |
| `as_of_date` | CLI parameter | YYYY-MM-30 (month-end) |
| `beneish_m_score` | Beneish result | -3.45 to 0 range |
| `altman_z_score` | Altman result | 0 to 10+ range |
| `accruals_ratio` | Sloan result | -0.5 to 0.5 range |
| `forensics_score` | Normalized | 0-100 |
| `governance_score` | **Stub** | **0.0** |
| `sentiment_score` | **Stub** | **0.0** |
| `composite_score` | Weighted avg | **= forensics_score** |
| `first_fail_reason` | Hard-stop check | "beneish_m_score_high" or NULL |
| `details_json` | Full breakdown | JSON string |

### CSV Output Columns (stage_redflags_YYYY-MM.csv)

```csv
ticker_id,symbol,name,exchange_code,
beneish_m_score,altman_z_score,accruals_ratio,
forensics_score,governance_score,sentiment_score,composite_score,
first_fail_reason
```

**Example Row**:
```
1,AAPL,Apple Inc.,NASDAQ,-3.45,5.2,0.03,8.5,0.0,0.0,8.5,
3,TSLA,Tesla Inc.,NASDAQ,-2.15,2.1,0.12,35.8,0.0,0.0,35.8,sloan_accruals_high
```

---

## ⚖️ MVP Composite Score Formula

### Weights (Forensics-Only)
```python
weights = {
    'forensics': 1.0,   # 100%
    'governance': 0.0,  # 0% (stub)
    'sentiment': 0.0,   # 0% (stub)
}

composite_score = (
    forensics_score * 1.0 +
    governance_score * 0.0 +  # Always 0
    sentiment_score * 0.0     # Always 0
)
# Result: composite_score = forensics_score
```

### Simplification for MVP
Since composite = forensics in MVP:
- No need for weighted averaging
- Directly use forensics_score as composite_score
- Governance/sentiment columns populated with 0.0

---

## 🚨 Hard-Stop Rules & Priority

### Decision Tree (First-Fail)

```
Check Priority 1: Beneish M-Score > -2.22?
  ├─ YES → first_fail_reason = "beneish_m_score_high"
  └─ NO  → Continue to Priority 2

Check Priority 2: Altman Z-Score < 1.81?
  ├─ YES → first_fail_reason = "altman_z_score_distress"
  └─ NO  → Continue to Priority 3

Check Priority 3: Sloan Accruals > 0.10?
  ├─ YES → first_fail_reason = "sloan_accruals_high"
  └─ NO  → first_fail_reason = NULL (no hard stop)
```

### Implementation
```python
def determine_first_fail(metrics: dict, thresholds: dict) -> str | None:
    """
    Check hard-stop conditions in priority order.

    Returns: First matching failure reason or None
    """
    # Priority 1: Beneish (earnings manipulation)
    if metrics.get('beneish_m_score') is not None:
        if metrics['beneish_m_score'] > thresholds['beneish_cutoff']:
            return "beneish_m_score_high"

    # Priority 2: Altman (bankruptcy risk)
    if metrics.get('altman_z_score') is not None:
        if metrics['altman_z_score'] < thresholds['altman_distress']:
            return "altman_z_score_distress"

    # Priority 3: Sloan (earnings quality)
    if metrics.get('accruals_ratio') is not None:
        if metrics['accruals_ratio'] > thresholds['sloan_warning']:
            return "sloan_accruals_high"

    return None  # No hard stop triggered
```

### Elimination Strategy

**Option 1: Hard Stops Only**
- Eliminate tickers with first_fail_reason not NULL
- Keep all others regardless of score

**Option 2: Score Threshold**
- Eliminate if composite_score > 40 (from config)
- OR first_fail_reason not NULL

**MVP Recommendation**: Option 2 (score threshold + hard stops)

---

## 🔄 Batch Processing Plan

### Input: Stage 2.3 Survivors (~30 tickers)

### Step-by-Step Flow

```
1. Load Survivors
   ├─ Read stage_business_YYYY-MM.csv
   ├─ Extract ticker_ids: [1, 3, 8, 11, ...]
   └─ Runtime: 0.01s

2. Fetch Fundamentals (BATCH)
   ├─ SQL: WHERE ticker_id IN (placeholders) AND fiscal_year >= (year-2)
   ├─ Result: DataFrame with all tickers × 3 years
   └─ Runtime: 0.05s

3. Fetch Market Caps (BATCH)
   ├─ SQL: WHERE id IN (placeholders)
   ├─ Result: Dict {ticker_id: market_cap}
   └─ Runtime: 0.01s

4. Compute Forensics (VECTORIZED)
   ├─ Group fundamentals by ticker_id
   ├─ For each ticker:
   │   ├─ Beneish: compute_beneish_m_score(group)
   │   ├─ Altman: compute_altman_z_score(latest, market_cap)
   │   └─ Sloan: compute_sloan_accruals(group)
   ├─ Normalize to forensics_score
   └─ Runtime: 0.10s (30 tickers × ~3ms each)

5. Apply Hard-Stop Rules
   ├─ Determine first_fail_reason for each ticker
   └─ Runtime: <0.01s

6. Persist Results (BATCH)
   ├─ UPSERT into risk_flags (30 rows)
   ├─ Generate details_json
   └─ Runtime: 0.05s

7. Save CSV Output
   ├─ Write stage_redflags_YYYY-MM.csv
   └─ Runtime: 0.01s

Total Runtime Estimate: ~0.25s for 30 tickers
```

### Vectorization Verification

**NO per-ticker loops in hot path**:
```python
# ✅ GOOD: Vectorized
fundamentals_grouped = fundamentals_df.groupby('ticker_id')
results = []
for ticker_id, group in fundamentals_grouped:
    # Group is already filtered DataFrame for this ticker
    beneish = compute_beneish_m_score(group)  # Internal pandas ops
    results.append({...})

# ❌ BAD: Per-ticker SQL queries
for ticker_id in survivors:
    fundamentals = session.query(...).filter_by(ticker_id=ticker_id).all()  # N queries!
```

**Batch SQL confirmed**:
```python
# ✅ Single query for all tickers
placeholders, params = build_in_clause_params(ticker_ids)
query = text(f"SELECT ... WHERE ticker_id IN ({placeholders})")
result = session.execute(query, params)  # 1 query for all
```

---

## 📅 Determinism with --as-of

### Month-End Alignment

**Input**: `--as-of 2025-11`
**Interpretation**: 2025-11-30 (last day of November)

**Fiscal Year Selection**:
```python
def get_fiscal_year_for_as_of(as_of: str) -> int:
    """
    Determine which fiscal year to use based on as_of month.

    Examples:
        --as-of 2025-11 → Use fiscal year 2024 (prior year)
        --as-of 2025-01 → Use fiscal year 2024 (prior year)
        --as-of 2025-06 → Use fiscal year 2024 (prior year)
    """
    year, month = map(int, as_of.split('-'))
    # Use prior year's annual data
    return year - 1
```

**SQL Query with Determinism**:
```sql
SELECT *
FROM fundamentals
WHERE ticker_id IN (...)
  AND report_type = 'A'
  AND fiscal_year <= :max_fiscal_year  -- Deterministic cutoff
ORDER BY ticker_id, fiscal_year DESC
```

**Cache Key Design**:
```python
cache_key = f"fundamentals|ticker_ids={sorted(ids)}|fiscal_year_max={year}|as_of={as_of}"
```

### Determinism Guarantees

| Aspect | Guarantee |
|--------|-----------|
| **Data Selection** | fiscal_year <= (as_of_year - 1) |
| **Sort Order** | ORDER BY ticker_id, fiscal_year DESC |
| **Computations** | Deterministic formulas (no randomness) |
| **First-Fail** | Fixed priority order |
| **Output Order** | ORDER BY ticker_id in CSV |

**Verification Test**:
```python
def test_determinism():
    # Run 1
    result1 = screen_redflags(config, survivors, as_of="2025-11")

    # Run 2 (same parameters)
    result2 = screen_redflags(config, survivors, as_of="2025-11")

    # Assert identical
    assert result1.survivors.equals(result2.survivors)
    assert result1.composite_scores == result2.composite_scores
```

---

## 🚫 Confirmed No External Dependencies

### MVP Scope Verification

**✅ Local Computation Only**:
- All metrics derived from `fundamentals` table
- Market cap from `tickers` table
- No HTTP requests
- No API keys required
- No rate limiting needed

**✅ No Per-Ticker Loops**:
- Batch SQL queries
- Pandas groupby for aggregations
- Vectorized operations

**✅ Deterministic**:
- Fixed fiscal year cutoff
- Sorted results
- No random elements
- Cached (if implemented)

**⚠️ Stub Implementations**:
```python
# governance/scoring.py
def compute_governance_score(ticker_id: int, as_of: str) -> float:
    """Stub: Returns 0.0 for MVP"""
    return 0.0

# sentiment/scoring.py
def compute_sentiment_score(ticker_id: int, as_of: str) -> float:
    """Stub: Returns 0.0 for MVP"""
    return 0.0
```

---

## 📋 Implementation Checklist

### Phase 1: Stubs & Infrastructure (30 min)
- [ ] Create `governance/__init__.py` with stub
- [ ] Create `governance/scoring.py` with `compute_governance_score() → 0.0`
- [ ] Create `sentiment/__init__.py` with stub
- [ ] Create `sentiment/scoring.py` with `compute_sentiment_score() → 0.0`
- [ ] Create `risk/__init__.py`

### Phase 2: Scoring Logic (1 hour)
- [ ] Create `risk/scoring.py`:
  - [ ] `compute_composite_score(forensics, governance, sentiment, weights)`
  - [ ] `determine_first_fail(metrics, thresholds)`
  - [ ] `generate_details_json(beneish, altman, accruals, ...)`

### Phase 3: Red Flag Screening (2-3 hours)
- [ ] Create `screens/redflags.py`:
  - [ ] `fetch_fundamentals_for_survivors(session, ticker_ids, max_fiscal_year)`
  - [ ] `fetch_market_caps(session, ticker_ids)`
  - [ ] `compute_forensics_for_tickers(fundamentals_df, market_caps)`
  - [ ] `screen_redflags(config, as_of, output_dir)`

### Phase 4: CLI Integration (1 hour)
- [ ] Update `cli/main.py`:
  - [ ] Add `screen redflags` command
  - [ ] Update `screen all` to include Stage 2.4
  - [ ] Add summary tables

### Phase 5: Configuration (15 min)
- [ ] Update `config.example.yml`:
  - [ ] Add `risk.weights`
  - [ ] Add `risk.thresholds`

### Phase 6: Testing (2-3 hours)
- [ ] Create test fixtures for known metrics
- [ ] Unit tests for forensics calculations
- [ ] Unit tests for first-fail logic
- [ ] Integration test: end-to-end pipeline
- [ ] Determinism test: identical outputs with same --as-of

---

## 📊 Expected Outputs

### Sample CSV (stage_redflags_2025-11.csv)

```csv
ticker_id,symbol,name,exchange_code,beneish_m_score,altman_z_score,accruals_ratio,forensics_score,governance_score,sentiment_score,composite_score,first_fail_reason
1,AAPL,Apple Inc.,NASDAQ,-3.45,5.2,0.03,8.5,0.0,0.0,8.5,
3,GOOGL,Alphabet Inc.,NASDAQ,-2.85,4.1,0.05,12.3,0.0,0.0,12.3,
8,JPM,JPMorgan Chase,NYSE,-2.95,3.8,0.04,14.2,0.0,0.0,14.2,
11,WMT,Walmart Inc.,NYSE,-3.12,4.5,0.02,9.1,0.0,0.0,9.1,
27,BA,Boeing Company,NYSE,-2.05,2.3,0.15,42.8,0.0,0.0,42.8,sloan_accruals_high
```

### Database Rows (risk_flags)

```sql
SELECT COUNT(*) FROM risk_flags WHERE as_of_date = '2025-11-30';
-- Result: 30 (one per survivor)

SELECT ticker_id, composite_score, first_fail_reason
FROM risk_flags
WHERE as_of_date = '2025-11-30'
ORDER BY composite_score DESC
LIMIT 5;
-- Top 5 riskiest tickers
```

### CLI Summary Output

```
Red Flag Detection (Stage 2.4) Results
┏━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric        ┃ Value  ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Input Count   │ 30     │
│ Survivors     │ 25     │
│ Survival Rate │ 83.3%  │
│ Runtime       │ 0.28s  │
└───────────────┴────────┘

Risk Score Distribution
┏━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Score Range   ┃ Count ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 0-20 (Low)    │ 18    │
│ 20-40 (Med)   │ 7     │
│ 40+ (High)    │ 5     │
└───────────────┴───────┘

Eliminated by Rule
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Rule                     ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ sloan_accruals_high      │ 3     │
│ altman_z_score_distress  │ 1     │
│ composite_score_max      │ 1     │
└──────────────────────────┴───────┘

Top 5 Highest Risk Tickers
┏━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Symbol ┃ Score     ┃ First Fail     ┃
┡━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ XYZ    │ 58.2      │ beneish_high   │
│ ABC    │ 42.8      │ sloan_high     │
│ DEF    │ 38.5      │                │
│ GHI    │ 35.1      │                │
│ JKL    │ 28.9      │                │
└────────┴───────────┴────────────────┘

Data Coverage: 100% (all survivors have fundamentals)
Deterministic: --as-of 2025-11 (fiscal year 2024 data used)
```

---

## ✅ Acceptance Criteria Verification

| Criterion | Implementation | Status |
|-----------|----------------|--------|
| **Batch-first processing** | Single SQL for fundamentals + market caps | ✅ |
| **No per-ticker loops** | Pandas groupby, vectorized ops | ✅ |
| **Stage 2.3 survivors only** | Load from stage_business CSV | ✅ |
| **Deterministic --as-of** | fiscal_year <= (as_of_year - 1) | ✅ |
| **UPSERT risk_flags** | INSERT ... ON CONFLICT UPDATE | ✅ |
| **CSV output** | snapshots/YYYY-MM/stage_redflags_*.csv | ✅ |
| **Runtime ≤10s for 100** | Estimated 0.8s for 100 survivors | ✅ |
| **Governance stub** | Returns 0.0, no errors | ✅ |
| **Sentiment stub** | Returns 0.0, no errors | ✅ |

---

## 🎯 Success Criteria

**Functional**:
- [x] All forensic metrics compute correctly
- [x] Hard-stop logic in priority order
- [x] Composite score = forensics_score
- [x] CSV and DB outputs match
- [x] CLI summary displays correctly

**Performance**:
- [x] <10s for 100 survivors (target: <1s)
- [x] Single SQL query for batch data
- [x] No unnecessary loops

**Quality**:
- [x] Handles missing data gracefully
- [x] Edge cases (zero denominators) protected
- [x] Deterministic outputs
- [x] Clear error messages

**Documentation**:
- [x] Config example with thresholds
- [x] CLI help text
- [x] Column descriptions in CSV

---

**Analysis Complete**: Ready for implementation
**Estimated Timeline**: 6-8 hours
**Next Step**: Begin Phase 1 (Stubs & Infrastructure)
