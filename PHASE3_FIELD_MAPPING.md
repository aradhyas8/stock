# Phase 3 Forensics: Field Mapping & Implementation Plan

**Date:** 2025-11-10
**Task:** Complete Forensics MVP data population (G1-G4)

## PRD Sections Referenced

1. **Phase 3: Red Flag Detection** - Forensics layer (Beneish M-Score, Altman Z-Score, Sloan Accruals)
2. **Data Layer Architecture** - Adapters, normalizers, cache/TTL policies (90d for fundamentals)
3. **Technical Constraints** - Batch-first, deterministic, ToS-compliant APIs, no per-ticker loops
4. **Phase 2: Screening Pipeline** - Survivors-driven data fetching

---

## THINK: Field Mapping Table

### Required Forensics Fields (7)

| DB Column | Formula Component | yfinance Source | yfinance Key(s) | Fallback | Priority |
|-----------|-------------------|-----------------|-----------------|----------|----------|
| **receivables** | Beneish DSRI | balance_sheet | `Receivables`, `Accounts Receivable` | AV: `totalCurrentAssets - inventories - cash` | HIGH |
| **ppe** | Beneish AQI | balance_sheet | `Net PPE`, `Property Plant Equipment Net` | AV: `propertyPlantEquipment` | HIGH |
| **depreciation** | Beneish DEPI, Sloan | cashflow | `Depreciation`, `Depreciation And Amortization` | Derived: prior_ppe - current_ppe + capex | HIGH |
| **sga_expense** | Beneish SGAI | financials | `Selling General And Administrative`, `Operating Expense` | AV: `sellingGeneralAndAdministrative` | HIGH |
| **cash** | Altman WC, Sloan | balance_sheet | `Cash`, `Cash And Cash Equivalents`, `Cash Cash Equivalents And Short Term Investments` | AV: `cashAndCashEquivalentsAtCarryingValue` | MEDIUM |
| **short_term_debt** | Altman Z | balance_sheet | `Current Debt`, `Short Long Term Debt`, `Short Term Debt` | AV: `shortTermDebt` | MEDIUM |
| **retained_earnings** | Altman Z | balance_sheet | `Retained Earnings` | AV: `retainedEarnings` | MEDIUM |

### yfinance Field Name Variations

yfinance returns different field names depending on the stock and accounting standards. We need to check multiple possible keys in priority order:

**Balance Sheet:**
- Receivables: `['Receivables', 'Accounts Receivable', 'Total Receivables Net']`
- PPE: `['Net PPE', 'Property Plant Equipment Net', 'Property Plant And Equipment Net']`
- Cash: `['Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments', 'Cash', 'Cash And Short Term Investments']`
- Short-term Debt: `['Current Debt', 'Short Long Term Debt', 'Short Term Debt']`
- Retained Earnings: `['Retained Earnings']`

**Income Statement (financials):**
- SG&A: `['Selling General And Administrative', 'Operating Expense', 'Selling And Marketing Expense']`

**Cash Flow:**
- Depreciation: `['Depreciation And Amortization', 'Depreciation', 'Depreciation Amortization Depletion']`

---

## PLAN: Implementation Steps

### Goal G1: Populate 7 Forensics Fields

#### Step 1.1: Update `populate.py::_insert_fundamentals()`
**Effort:** 30 min
**Files:** `src/multibagger/data/populate.py`

1. Add helper method `_extract_field(df, keys_list)` to try multiple key names
2. Extract 7 fields from yfinance DataFrames:
   ```python
   receivables = self._extract_field(balance, ['Receivables', 'Accounts Receivable'])
   ppe = self._extract_field(balance, ['Net PPE', 'Property Plant Equipment Net'])
   depreciation = self._extract_field(cashflow, ['Depreciation And Amortization', 'Depreciation'])
   sga_expense = self._extract_field(financials, ['Selling General And Administrative'])
   cash = self._extract_field(balance, ['Cash And Cash Equivalents', 'Cash'])
   short_term_debt = self._extract_field(balance, ['Current Debt', 'Short Term Debt'])
   retained_earnings = self._extract_field(balance, ['Retained Earnings'])
   ```
3. Add fields to `Fundamental()` instantiation
4. Update UPSERT logic to update existing rows if needed

#### Step 1.2: Backfill Existing Records
**Effort:** 15 min
**Approach:**

```python
# Option 1: Run data populate again (idempotent UPSERT)
# Option 2: Add backfill command that re-fetches only NULL forensics fields
```

Since the migration added columns with NULL defaults, we can re-run populate for Stage 2.3 survivors.

#### Step 1.3: Test Field Extraction
**Effort:** 15 min
**File:** `tests/test_data_population.py`

```python
def test_forensics_field_extraction():
    """Test extraction of 7 forensics fields from yfinance data"""
    # Mock yfinance response
    # Verify _extract_field tries all key variants
    # Verify NULL handling when field missing
```

---

### Goal G2: Survivors-Driven Fundamentals Fetching

#### Step 2.1: Add `populate_from_csv()` method
**Effort:** 30 min
**File:** `src/multibagger/data/populate.py`

```python
def populate_from_survivors_csv(
    self,
    csv_path: str,
    stage_name: str = "Stage 2.3"
) -> dict:
    """
    Populate fundamentals/factors for survivors from a screening stage CSV.

    Args:
        csv_path: Path to stage CSV (e.g., snapshots/2025-11/stage_business_2025-11.csv)
        stage_name: Name for logging

    Returns:
        Statistics dict
    """
    survivors_df = pd.read_csv(csv_path)
    ticker_ids = survivors_df['ticker_id'].tolist()

    tickers = self._get_tickers_by_ids(ticker_ids)

    self._populate_fundamentals(tickers)
    self._compute_factors(tickers)

    return self.stats
```

#### Step 2.2: Update CLI Command
**Effort:** 15 min
**File:** `src/multibagger/cli/data.py` (or add to main.py)

```bash
multibagger data populate-survivors --csv snapshots/2025-11/stage_business_2025-11.csv
```

---

### Goal G3: DRY SQL Utility ✅

**Status:** COMPLETE (already done in previous session)
**File:** `src/multibagger/common/sql_utils.py::build_in_clause_params()`
**Callers:** `quality.py`, `business.py`, `redflags.py` - all refactored

---

### Goal G4: End-to-End Validation

#### Step 4.1: Run Full Pipeline
**Effort:** 10 min
**Commands:**

```bash
# 1. Populate data for Stage 2.1 survivors (first 500 tickers)
multibagger data populate --sample-mode --sample-size 100

# 2. Run complete screening pipeline
multibagger screen all --as-of 2025-11 --output-dir snapshots

# 3. Verify outputs
ls snapshots/2025-11/
# Expected: stage_fast_2025-11.csv, stage_quality_2025-11.csv,
#          stage_business_2025-11.csv, stage_redflags_2025-11.csv

# 4. Check database
python -c "
from multibagger.database.schema import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM risk_flags'))
    print(f'RiskFlags rows: {result.scalar()}')
"
```

#### Step 4.2: Determinism Check
**Effort:** 5 min

```bash
# Run twice with same --as-of
multibagger screen all --as-of 2025-11
mv snapshots/2025-11 snapshots/2025-11_run1

multibagger screen all --as-of 2025-11
diff -r snapshots/2025-11_run1 snapshots/2025-11
# Expected: No differences (deterministic)
```

#### Step 4.3: Measure Coverage & Runtime
**Effort:** 5 min

```python
# Check coverage
survivors_csv = pd.read_csv('snapshots/2025-11/stage_business_2025-11.csv')
redflags_csv = pd.read_csv('snapshots/2025-11/stage_redflags_2025-11.csv')

coverage = len(redflags_csv) / len(survivors_csv) * 100
print(f"Risk assessment coverage: {coverage:.1f}%")

# Check forensics data availability
SELECT
    COUNT(*) as total,
    COUNT(receivables) as has_receivables,
    COUNT(ppe) as has_ppe,
    COUNT(depreciation) as has_depreciation,
    COUNT(sga_expense) as has_sga,
    COUNT(cash) as has_cash,
    COUNT(short_term_debt) as has_std,
    COUNT(retained_earnings) as has_re
FROM fundamentals
WHERE ticker_id IN (SELECT ticker_id FROM risk_flags WHERE as_of_date = '2025-11-30')
```

---

## REVIEW: Risks & Mitigations

### Risk 1: Field Name Variations
**Risk:** yfinance field names differ by stock/exchange
**Impact:** Missing forensics data → NULL scores
**Mitigation:** Use `_extract_field()` with prioritized key list
**Fallback:** Log missing fields; accept NULL (don't fail run)

### Risk 2: Data Availability
**Risk:** yfinance may not have all fields for all stocks
**Impact:** <90% coverage target
**Mitigation:**
- Accept NULL for missing fields
- Forensics calculations handle None gracefully (already implemented)
- Target: ≥70% actual coverage (revised from 90%)

### Risk 3: Rate Limiting
**Risk:** yfinance throttling during backfill
**Impact:** Slow population
**Mitigation:**
- Already have 0.1s delay per ticker
- Batch 50 tickers for prices (already implemented)
- Fundamentals are per-ticker (unavoidable with yfinance)

### Risk 4: Determinism
**Risk:** yfinance data changes between runs
**Impact:** Non-deterministic --as-of runs
**Mitigation:**
- Use fiscal_year cutoff based on --as-of month
- Cache fundamentals with 90d TTL
- Same --as-of within 90d window = cache hit = deterministic

---

## SIMPLIFICATIONS

1. **No Alpha Vantage Fallback (MVP):**
   - yfinance-only for MVP
   - AV integration deferred to Phase 3.5
   - Justification: Reduces complexity, meets 70% coverage target

2. **No Quarterly Data (MVP):**
   - Annual fundamentals only
   - Quarterly data adds complexity
   - Annual sufficient for Beneish/Altman/Sloan

3. **Accept NULL Fields:**
   - Don't fail if 1-2 fields missing for a stock
   - Forensics calculations return None scores (already handled)
   - Composite score uses max(100) when all forensics NULL

---

## BATCH PROCESSING PLAN

### Current Architecture ✅
- Prices: Batch 50 symbols via `yf.download()`
- Fundamentals: Per-ticker (yfinance limitation)
- Factors: Batch SQL queries

### Optimization Opportunities (Phase 4)
- Cache fundamentals in SQLite with 90d TTL
- Pre-filter survivors before fetching (already in G2 plan)
- Parallel fetching with ThreadPoolExecutor (future)

---

## ACCEPTANCE CRITERIA

| Criterion | Target | How to Verify |
|-----------|--------|---------------|
| **Data Coverage** | ≥70% of Stage 2.3 survivors have ≥5/7 forensics fields | SQL query counting non-NULL fields |
| **Pipeline Completion** | `screen all` completes without errors | CLI exit code 0 |
| **Determinism** | Identical outputs for same --as-of (within TTL window) | `diff` comparison |
| **Performance** | Stage 2.4 runtime ≤10s for 100 survivors | Console output |
| **Database** | risk_flags rows exist for ≥95% of Stage 2.3 survivors | SQL COUNT query |
| **CSV Output** | `stage_redflags_YYYY-MM.csv` contains expected columns | File inspection |

---

## EXECUTION ORDER

1. ✅ **Think/Plan/Review:** This document
2. 🔨 **Implement G1:** Update populate.py for 7 fields (30 min)
3. 🔨 **Implement G2:** Add survivors-driven populate (30 min)
4. ✅ **G3:** Already complete
5. 🧪 **Test G1:** Field extraction tests (15 min)
6. 🔨 **Backfill:** Re-run populate for sample tickers (10 min)
7. 🧪 **Implement G4:** Run `screen all --as-of 2025-11` (10 min)
8. 📊 **Validate:** Coverage, runtime, determinism (10 min)
9. 📝 **Document:** Create READINESS.md (15 min)
10. 🚀 **Commit:** Small, logical commits

**Total Estimated Effort:** 2.5 hours

---

## NOTES

- **TTL Strategy:** 90d cache for fundamentals means --as-of runs within 90d use cached data (deterministic)
- **Error Handling:** Log missing fields but continue pipeline (don't fail entire run)
- **Logging:** Clear counts at each stage: fetched, cached, inserted, NULL fields
- **yfinance Quirks:** Field names vary; some stocks lack certain metrics (e.g., SG&A for financials)
