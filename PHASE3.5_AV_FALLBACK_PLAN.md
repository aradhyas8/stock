# Phase 3.5: Data Reliability Hardening & Alpha Vantage Fallback

**Date:** 2025-11-10
**Session:** claude/multibagger-research-system-011CUxsN8xof3LhsUBDPPcEi
**Task:** Add Alpha Vantage fallback to achieve ≥90% forensics data coverage

---

## THINK: PRD Alignment & Problem Analysis

### PRD Sections Referenced

1. **Phase 3: Red Flag Detection** - Forensics layer data requirements
2. **Data Layer Architecture** - Multi-source adapters, cache/TTL policies, provenance tracking
3. **Technical Constraints** - Batch-first, deterministic, ToS-compliant APIs, rate limiting
4. **Data Population Strategy** - Cache-first, survivors-driven fetching

### Problem Statement

**Current State:**
- yfinance returned empty DataFrames for forensics fields during Phase 3 MVP
- 0% data coverage → all forensics scores = None → no hard-stops triggered
- Pipeline architecture is complete but lacks data

**Root Cause:**
- yfinance API limitations (inconsistent field availability)
- Small-cap stocks have sparse fundamental data
- No fallback mechanism when primary source fails

**Goal:**
- Add Alpha Vantage (AV) as secondary data source
- Achieve ≥90% coverage for 7 forensics fields across Stage 2.3 survivors
- Maintain determinism and observability

---

## PLAN: Implementation Steps

### Alpha Vantage Field Mapping

| Our Field | AV Endpoint | AV JSON Path | Fallback Path |
|-----------|-------------|--------------|---------------|
| **receivables** | BALANCE_SHEET | `annualReports[].currentNetReceivables` | `netReceivables` |
| **ppe** | BALANCE_SHEET | `annualReports[].propertyPlantEquipment` | - |
| **depreciation** | CASH_FLOW | `annualReports[].depreciationAndAmortization` | `depreciation` |
| **sga_expense** | INCOME_STATEMENT | `annualReports[].sellingGeneralAdministrative` | `operatingExpenses` |
| **cash** | BALANCE_SHEET | `annualReports[].cashAndShortTermInvestments` | `cashAndCashEquivalentsAtCarryingValue` |
| **short_term_debt** | BALANCE_SHEET | `annualReports[].shortLongTermDebtTotal` | `currentDebt` |
| **retained_earnings** | BALANCE_SHEET | `annualReports[].retainedEarnings` | - |

### Alpha Vantage API Details

**Endpoints:**
- `INCOME_STATEMENT` - https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=IBM&apikey=demo
- `BALANCE_SHEET` - https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol=IBM&apikey=demo
- `CASH_FLOW` - https://www.alphavantage.co/query?function=CASH_FLOW&symbol=IBM&apikey=demo

**Rate Limits (Free Tier):**
- 5 calls per minute
- 500 calls per day
- Must throttle: 12 seconds between calls minimum

**Response Format:**
```json
{
  "symbol": "IBM",
  "annualReports": [
    {
      "fiscalDateEnding": "2023-12-31",
      "reportedCurrency": "USD",
      "currentNetReceivables": "9876000000",
      "propertyPlantEquipment": "12345000000",
      ...
    }
  ]
}
```

### Source Selection Policy (Deterministic)

**Priority Order:**
1. **yfinance** (primary) - Fast, free, no rate limits
2. **Alpha Vantage** (fallback) - Reliable but rate-limited

**Decision Tree per Field:**
```python
def get_field_value(symbol, field_name, period_end):
    # 1. Try yfinance
    yf_value = fetch_from_yfinance(symbol, field_name, period_end)
    if yf_value is not None and yf_value > 0:
        return (yf_value, 'yfinance')

    # 2. Fallback to Alpha Vantage
    av_value = fetch_from_alpha_vantage(symbol, field_name, period_end)
    if av_value is not None and av_value > 0:
        return (av_value, 'alpha_vantage')

    # 3. No data available
    return (None, 'unavailable')
```

**Determinism Guarantee:**
- Same --as-of date → same fiscal year cutoff
- Same symbol + period_end → same source selection
- TTL=90d → cache hits within 90-day window

### Implementation Tasks

#### Task 1: Alpha Vantage Adapter (2 hours)

**File:** `src/multibagger/data/adapters/alpha_vantage_adapter.py`

```python
class AlphaVantageAdapter:
    """
    Adapter for Alpha Vantage fundamental data API.

    Respects rate limits (5/min, 500/day) with exponential backoff.
    Caches responses with 90d TTL.
    """

    def __init__(self, api_key: str, cache: HttpCache):
        self.api_key = api_key
        self.cache = cache
        self.last_call_time = None
        self.MIN_CALL_INTERVAL = 12  # seconds (5 calls/min = 12s/call)

    def fetch_fundamentals(self, symbol: str, years: int = 5) -> dict:
        """
        Fetch income statement, balance sheet, and cash flow.

        Returns:
            {
                'income_statement': [annual reports...],
                'balance_sheet': [annual reports...],
                'cash_flow': [annual reports...]
            }
        """
        pass

    def _fetch_with_throttle(self, function: str, symbol: str) -> dict:
        """Fetch with rate limiting and caching"""
        # Check cache first (TTL=90d)
        # If miss, throttle then call API
        # Store in cache
        pass

    def _extract_field(self, reports: list, field_name: str, fallback_keys: list) -> dict:
        """Extract field from annual reports with fallback keys"""
        pass
```

#### Task 2: Update populate.py with Source Selection (1.5 hours)

**File:** `src/multibagger/data/populate.py`

**Changes:**
1. Add `AlphaVantageAdapter` initialization
2. Update `_populate_fundamentals()` to try both sources
3. Track provenance (which source provided each field)
4. Add field-level statistics

```python
def _populate_fundamentals_with_fallback(self, tickers: list[dict]):
    """
    Populate fundamentals with yfinance → AV fallback.

    For each ticker:
    1. Try yfinance for all fields
    2. For NULL fields, try Alpha Vantage
    3. Track which source provided each field
    4. Update fundamentals table with best-available data
    """
    success_count = 0
    field_coverage = defaultdict(lambda: {'yfinance': 0, 'alpha_vantage': 0, 'missing': 0})

    for ticker in tickers:
        symbol = ticker['symbol']

        # Try yfinance first
        yf_data = self.yfinance_adapter.fetch_fundamentals(symbol, years=5)

        # Extract fields from yfinance
        yf_fields = self._extract_forensics_fields(yf_data)

        # For NULL fields, try AV
        av_fields = {}
        for field_name, value in yf_fields.items():
            if value is None:
                av_data = self.av_adapter.fetch_fundamentals(symbol, years=5)
                av_value = self._extract_field_from_av(av_data, field_name)
                av_fields[field_name] = av_value

        # Merge and track provenance
        # UPSERT to fundamentals
        # Update coverage stats

    return field_coverage
```

#### Task 3: Backfill Command with Coverage Report (1 hour)

**File:** `src/multibagger/cli/data.py`

```python
@app.command()
def backfill_forensics(
    as_of: str = typer.Option(..., "--as-of", help="As-of month (YYYY-MM)"),
    csv_path: str | None = typer.Option(None, "--csv", help="Custom CSV path"),
    output_dir: str = typer.Option("snapshots", "--output-dir", help="Output directory")
) -> None:
    """
    Backfill forensics fields for screening survivors using yfinance + AV fallback.

    This command:
    1. Loads survivors from stage_business_<as-of>.csv
    2. Fetches fundamentals from yfinance (fast)
    3. Falls back to Alpha Vantage for missing fields (rate-limited)
    4. UPSERTs to fundamentals table
    5. Generates coverage report

    Example:
        multibagger data backfill-forensics --as-of 2025-11
    """
    # Load survivors CSV
    # Run populate with fallback
    # Generate coverage JSON
    # Print summary table
```

**Coverage Report Format:**

```json
{
  "as_of": "2025-11",
  "total_survivors": 10,
  "timestamp": "2025-11-10T12:34:56Z",
  "field_coverage": {
    "receivables": {
      "yfinance": 7,
      "alpha_vantage": 2,
      "missing": 1,
      "coverage_pct": 90.0
    },
    "ppe": {...},
    ...
  },
  "overall_coverage": {
    "all_7_fields": 8,
    "at_least_5_fields": 9,
    "coverage_pct": 80.0
  },
  "api_stats": {
    "yfinance_calls": 10,
    "alpha_vantage_calls": 15,
    "cache_hits": 5,
    "rate_limit_sleeps": 3
  }
}
```

#### Task 4: Configuration Updates (15 min)

**File:** `config.example.yml`

```yaml
data:
  sources:
    alpha_vantage:
      enabled: true
      api_key: "${ALPHA_VANTAGE_KEY}"
      rate_limit_per_minute: 5
      timeout_seconds: 30
      ttl_days: 90
```

**File:** `.env.example`

```
ALPHA_VANTAGE_KEY=your_key_here
```

#### Task 5: Quality Guardrails (30 min)

**File:** `src/multibagger/data/validators.py` (new)

```python
def validate_forensics_fields(fundamental: dict) -> dict:
    """
    Sanity checks for forensics fields.

    Returns:
        {'valid': bool, 'issues': list}
    """
    issues = []

    # Non-negative checks
    for field in ['receivables', 'ppe', 'cash', 'short_term_debt']:
        if fundamental.get(field) and fundamental[field] < 0:
            issues.append(f"{field} is negative: {fundamental[field]}")

    # Ratio checks
    if fundamental.get('receivables') and fundamental.get('total_assets'):
        if fundamental['receivables'] > fundamental['total_assets']:
            issues.append("receivables > total_assets")

    # Return validation result
    return {
        'valid': len(issues) == 0,
        'issues': issues
    }
```

---

## REVIEW: Risks & Mitigations

### Risk 1: Alpha Vantage Rate Limits
**Risk:** Free tier allows only 5 calls/min, 500/day
**Impact:** Backfill for 10 survivors × 3 endpoints = 30 calls = 6 minutes minimum
**Mitigation:**
- Intelligent throttling (12s between calls)
- Cache with 90d TTL (re-run within 90d = cache hits)
- Progress bar to show estimated time
- Support resumable backfill (skip already-populated fields)

### Risk 2: Field Name Variations
**Risk:** AV field names may differ by company/country
**Impact:** Missing data despite availability
**Mitigation:**
- Multi-key fallback list (same as yfinance)
- Normalize field names (camelCase, snake_case, etc.)
- Log unmatched field names for manual review

### Risk 3: Data Quality Issues
**Risk:** AV data may have errors (negative values, extreme ratios)
**Impact:** Bad forensics scores
**Mitigation:**
- Sanity checks before UPSERT
- Flag suspicious values in details_json
- Skip scoring if data quality is poor

### Risk 4: Cost/API Key Management
**Risk:** Free tier limitations, need paid plan?
**Impact:** Cannot complete backfill
**Mitigation:**
- Start with free tier (500/day sufficient for 10 survivors)
- Document upgrade path if needed
- Add configurable rate limits for paid tiers

---

## SIMPLIFICATIONS

### MVP Simplifications (Phase 3.5)

1. **Annual Data Only:**
   - Skip quarterly data for now
   - Annual sufficient for 5-year Beneish/Altman/Sloan
   - Quarterly adds complexity (more API calls)

2. **Single AV Account:**
   - No multi-account rotation
   - Use single API key from .env
   - Upgrade to paid if needed

3. **No Data Validation Beyond Sanity:**
   - Don't verify GAAP compliance
   - Don't reconcile across statements
   - Trust AV data integrity

4. **Sequential Processing:**
   - No parallel AV calls (rate limit constraint)
   - Process survivors one by one
   - Accept slower backfill time

### Deferred to Phase 4

1. **Multi-Source Voting:**
   - Don't average yfinance + AV values
   - Use deterministic priority (yfinance wins if available)

2. **Historical Backfill:**
   - Only backfill for current as-of month
   - Don't re-populate all historical months

3. **Quarterly Fallback:**
   - Don't use quarterly if annual missing
   - Annual-only for MVP

---

## BATCH PROCESSING PLAN

### AV API Call Strategy

**Scenario:** 10 Stage 2.3 survivors

**Required Calls:**
- 10 tickers × 3 endpoints (INCOME, BALANCE, CASH_FLOW) = **30 API calls**

**Time Estimate:**
- 30 calls × 12 seconds/call = **6 minutes minimum**
- Cache hits reduce this on re-run

**Optimization:**
- Check cache before calling AV
- Only call AV for fields that were NULL from yfinance
- Batch cache checks (single SQL query)

### Progress Reporting

```
Backfilling Forensics Fields for 2025-11
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/10] GOOGL: Fetching from yfinance... ✓ (7/7 fields)
[2/10] JPM: Fetching from yfinance... ⚠ (5/7 fields)
       → Fetching missing fields from Alpha Vantage... [12s throttle]
       → Alpha Vantage... ✓ (2/2 fields)
[3/10] WMT: Fetching from yfinance... ✓ (7/7 fields)
...

Coverage Summary:
  Total Survivors: 10
  All 7 Fields: 8 (80%)
  At Least 5 Fields: 10 (100%)

API Statistics:
  yfinance Calls: 10
  Alpha Vantage Calls: 6
  Cache Hits: 4
  Rate Limit Sleeps: 6 (72 seconds total)

Runtime: 1m 30s
```

---

## ACCEPTANCE CRITERIA

| Criterion | Target | How to Verify |
|-----------|--------|---------------|
| **Field Coverage** | ≥90% survivors have all 7 fields | JSON report + SQL query |
| **Source Mix** | yfinance primary, AV fills gaps | Coverage breakdown by source |
| **Pipeline Success** | `screen all --as-of 2025-11` completes | CLI exit code 0 |
| **Non-NULL Inputs** | ≥90% survivors have non-NULL forensics scores | risk_flags table query |
| **Determinism** | Same --as-of → same outputs (within TTL) | `diff` comparison |
| **Rate Limiting** | No 429 errors from AV | Logs clean |
| **Coverage Report** | JSON emitted to snapshots/<YYYY-MM>/ | File exists |
| **Observability** | Clear logs with coverage stats | Console output + log file |

---

## EXECUTION ORDER

1. ✅ **Think/Plan/Review:** This document
2. 🔨 **Implement:** Alpha Vantage adapter (2h)
   - Create `alpha_vantage_adapter.py`
   - Add field mapping with fallback keys
   - Implement throttling and caching
   - Unit tests for field extraction
3. 🔨 **Implement:** Source selection policy (1.5h)
   - Update `populate.py` with fallback logic
   - Track provenance per field
   - Add coverage statistics
4. 🔨 **Implement:** Backfill command (1h)
   - Add `backfill-forensics` CLI command
   - Generate coverage JSON report
   - Progress bar with ETA
5. 🔨 **Config:** Update config.example.yml + .env.example (15min)
6. 🧪 **Test:** Run backfill for 2025-11 (6min + dev time)
7. 🧪 **Validate:** Run `screen all --as-of 2025-11` (1min)
8. 📊 **Verify:** Check coverage ≥90% (SQL queries)
9. 📊 **Determinism:** Re-run and diff outputs
10. 📝 **Document:** Update READINESS.md with Phase 3.5 results
11. 🚀 **Commit:** Small, logical commits

**Total Estimated Effort:** 5-6 hours

---

## NOTES

- **AV API Key:** User must provide ALPHA_VANTAGE_KEY in .env (free key from https://www.alphavantage.co/support/#api-key)
- **Throttling:** 12s between AV calls (conservative, free tier = 5/min)
- **TTL:** 90d cache means re-running within 90 days uses cached data (deterministic)
- **Provenance:** Track which source provided each field for debugging
- **Quality:** Basic sanity checks prevent obviously bad data
- **Logging:** Detailed logs help diagnose data issues
