# Phase 3: Red Flag Detection - Implementation Progress

**Date**: 2025-11-10
**Status**: 🟡 **IN PROGRESS** (Foundation Complete)
**Completion**: 35% (Design + Forensics Layer)

---

## ✅ Completed

### 1. Comprehensive Design Document (PHASE3_DESIGN.md)

**What Was Delivered**:
- **Signal Mapping**: Complete formulas for Beneish (8 components), Altman (5 components), and Sloan Accruals
- **Field Requirements**: Exact mapping from formulas → database fields → source tables
- **Country Routing**: US (EDGAR) vs. India (MCA) vs. skip logic
- **Batch Processing Plan**: 60-second pipeline for 30 survivors with breakdown
- **Scoring Weights**: Forensics 50%, Governance 30%, Sentiment 20%
- **Determinism Strategy**: Month-end aligned lookbacks, cache key design
- **Schema Design**: Complete risk_flags table with indexes and details_json structure
- **Testing Strategy**: Unit tests, integration tests, determinism tests
- **Acceptance Criteria**: Performance, compliance, quality requirements

**Key Design Decisions**:
```yaml
risk:
  weights:
    forensics: 0.50    # Local computation, no APIs
    governance: 0.30   # SEC EDGAR for US, MCA for India
    sentiment: 0.20    # NewsAPI with 30-day lookback

  thresholds:
    composite_score_max: 40
    beneish_m_score_max: -2.22
    altman_z_score_min: 1.81
    accruals_max: 0.10
```

### 2. Database Schema (models.py)

**RiskFlag Model Added**:
```python
class RiskFlag(Base):
    """Red flag detection results for ticker risk assessment"""

    # Forensics Metrics
    beneish_m_score, altman_z_score, accruals_ratio, forensics_score

    # Governance Metrics
    insider_sell_90d, promoter_pledge, governance_score

    # Sentiment Metrics
    neg_news_30d, severity_score, sentiment_score

    # Composite
    composite_score, first_fail_reason, details_json
```

**Indexes**:
- `(ticker_id, as_of_date)` UNIQUE - Prevent duplicates
- `(composite_score)` - Fast sorting by risk
- `(as_of_date)` - Deterministic queries

### 3. Forensics Module (100% Complete) ✅

**Files Created**:
- `src/multibagger/forensics/metrics.py` (450 lines)
- `src/multibagger/forensics/__init__.py`

**Functions Implemented**:

#### `compute_beneish_m_score(fundamentals_df)`
- **8 Components**: DSRI, GMI, AQI, SGI, DEPI, SGAI, TATA, LVGI
- **Threshold**: M-Score > -2.22 = High manipulation risk
- **Data Requirement**: 2+ years of annual fundamentals
- **Error Handling**: Safe division, missing field defaults, logging

#### `compute_altman_z_score(fundamentals, market_cap)`
- **5 Components**: WC/TA, RE/TA, EBIT/TA, MVE/TL, Sales/TA
- **Thresholds**: < 1.81 (high risk), 1.81-2.99 (gray), > 2.99 (safe)
- **Data Requirement**: Latest fundamentals + current market cap
- **Error Handling**: Zero denominator protection

#### `compute_sloan_accruals(fundamentals_df)`
- **Formula**: (ΔCA - ΔCash - ΔCL + ΔSTD - Depr) / Avg TA
- **Threshold**: > 0.10 (10% of assets) = Earnings quality concern
- **Data Requirement**: 2+ years for delta calculations
- **Interpretation**: High positive = concern, negative = conservative

#### `compute_forensics_score(beneish, altman, accruals)`
- **Normalization**: Converts metrics to 0-100 risk score
- **Weights**: Beneish 40%, Altman 40%, Accruals 20%
- **Output**: Higher score = higher risk
- **Bounded**: min(100, max(0, score))

**Testing Status**:
- ✅ Code complete with comprehensive docstrings
- ⚠️ Unit tests not yet implemented
- ⚠️ Validation against known examples pending

---

## 🚧 In Progress / Remaining

### 4. Governance Module (0% Complete) 🔴

**What Needs Implementation**:

#### File Structure:
```
src/multibagger/governance/
├── __init__.py
├── edgar.py          # SEC EDGAR API integration
├── mca.py            # MCA provider integration (optional)
└── scoring.py        # Governance risk scoring
```

#### Key Functions Needed:

**edgar.py**:
```python
def fetch_cik_for_ticker(symbol: str, exchange: str) -> str:
    """Lookup company CIK from SEC EDGAR"""

def fetch_insider_transactions(cik: str, lookback_days: int) -> list:
    """Fetch Form 4 transactions from SEC API"""

def calculate_insider_metrics(transactions: list) -> dict:
    """
    Returns: {
        'insider_sell_90d': float,  # % of shares
        'sell_buy_ratio': float,
        'officer_selling_pct': float
    }
    """
```

**mca.py** (optional, can be stub):
```python
def fetch_promoter_pledge(cin: str, config: dict) -> dict:
    """Fetch pledge data from MCA provider"""

def fetch_shareholding_pattern(cin: str, config: dict) -> dict:
    """Fetch promoter holding changes"""
```

**scoring.py**:
```python
def compute_governance_score(metrics: dict) -> float:
    """Normalize governance metrics to 0-100 risk score"""
```

**Estimated Effort**: 4-6 hours
**Complexity**: Medium (API integration, caching, rate limits)

### 5. Sentiment Module (0% Complete) 🔴

**What Needs Implementation**:

#### File Structure:
```
src/multibagger/sentiment/
├── __init__.py
├── news.py           # NewsAPI integration
├── keywords.py       # Adverse keyword dictionary
└── scoring.py        # Sentiment risk scoring
```

#### Key Functions Needed:

**news.py**:
```python
def fetch_news_for_ticker(
    symbol: str,
    name: str,
    lookback_days: int,
    api_key: str
) -> list:
    """Query NewsAPI for ticker mentions"""

def scan_headlines_for_keywords(headlines: list, keywords: dict) -> dict:
    """
    Returns: {
        'neg_news_30d': int,
        'adverse_keywords': list,
        'severity_score': float,
        'latest_adverse_date': datetime
    }
    """
```

**keywords.py**:
```python
ADVERSE_KEYWORDS = {
    'legal': {
        'keywords': ['fraud', 'investigation', 'lawsuit', 'indictment'],
        'weight': 10
    },
    'financial_distress': {
        'keywords': ['bankruptcy', 'insolvency', 'default'],
        'weight': 9
    },
    # ... etc
}
```

**scoring.py**:
```python
def compute_sentiment_score(metrics: dict) -> float:
    """Normalize sentiment metrics to 0-100 risk score"""
```

**Estimated Effort**: 3-4 hours
**Complexity**: Medium (API integration, keyword matching, rate limits)

### 6. Composite Scoring & Pipeline (0% Complete) 🔴

**What Needs Implementation**:

#### File Structure:
```
src/multibagger/risk/
├── __init__.py
├── scoring.py        # Composite risk score computation
└── screening.py      # Main red flag screening pipeline
```

#### Key Functions Needed:

**scoring.py**:
```python
def compute_composite_score(
    forensics_score: float,
    governance_score: float,
    sentiment_score: float,
    weights: dict
) -> float:
    """Weighted average of sub-scores"""

def determine_first_fail(metrics: dict, thresholds: dict) -> str | None:
    """Check for hard-stop conditions"""

def generate_details_json(
    forensics: dict,
    governance: dict,
    sentiment: dict,
    composite: float
) -> str:
    """Generate explainable breakdown with provenance"""
```

**screening.py**:
```python
def screen_redflags(
    config: Config,
    survivors_df: pd.DataFrame,
    as_of: str,
    output_dir: str
) -> ScreenResult:
    """
    Main red flag screening pipeline.

    Steps:
    1. Fetch fundamentals for survivors
    2. Compute forensics locally
    3. Fetch governance data (by exchange routing)
    4. Fetch sentiment data (with rate limiting)
    5. Compute composite scores
    6. Apply elimination rules
    7. Persist to database
    8. Save CSV output
    """
```

**Estimated Effort**: 3-4 hours
**Complexity**: Medium (orchestration, error handling)

### 7. CLI Integration (0% Complete) 🔴

**What Needs Implementation**:

#### Update `src/multibagger/cli/main.py`:
```python
@app.command()
def screen(
    stage: str,  # Add 'redflags' option
    as_of: str = None,
    output_dir: str = "snapshots",
    dry_run: bool = False
):
    """Run screening pipeline"""

    if stage == "redflags":
        # Load business filter output
        business_output = Path(output_dir) / as_of / f"stage_business_{as_of}.csv"
        survivors_df = pd.read_csv(business_output)

        # Run red flag detection
        result = screen_redflags(config, survivors_df, as_of, output_dir)

        # Print summary
        print_stage_summary(result)

    elif stage == "all":
        # Run stages 2.1, 2.2, 2.3, then 2.4
        screen_fast(...)
        screen_quality(...)
        screen_business(...)
        screen_redflags(...)  # NEW
```

**Estimated Effort**: 1-2 hours
**Complexity**: Low (similar to existing stages)

### 8. Testing & Validation (0% Complete) 🔴

**What Needs Implementation**:

#### Unit Tests:
```python
# tests/test_forensics.py
def test_beneish_m_score_with_manipulator_fixture()
def test_altman_z_score_with_distressed_company()
def test_sloan_accruals_calculation()

# tests/test_governance.py (mocked APIs)
def test_edgar_transaction_parsing()
def test_insider_metrics_calculation()

# tests/test_sentiment.py (mocked APIs)
def test_adverse_keyword_detection()
def test_sentiment_scoring()

# tests/test_risk_scoring.py
def test_composite_score_calculation()
def test_first_fail_logic()
```

#### Integration Tests:
```python
# tests/test_screen_redflags.py
def test_redflags_end_to_end_with_mocks()
def test_determinism_same_as_of()
def test_csv_output_format()
```

**Estimated Effort**: 4-6 hours
**Complexity**: Medium (need fixtures, mocks)

### 9. Configuration (0% Complete) 🔴

**What Needs Adding to `config.example.yml`**:

```yaml
risk:
  # Scoring weights
  weights:
    forensics: 0.50
    governance: 0.30
    sentiment: 0.20

  # Elimination thresholds
  thresholds:
    composite_score_max: 40

    forensics:
      beneish_m_score_max: -2.22
      altman_z_score_min: 1.81
      accruals_max: 0.10

    governance:
      insider_sell_90d_max: 0.02
      promoter_pledge_max: 0.50

    sentiment:
      neg_news_30d_max: 3
      severity_score_max: 50

# Governance data sources
governance:
  edgar:
    enabled: true
    rate_limit: 10  # requests per second
    user_agent: "MultiBagger/1.0 (your-email@example.com)"

  mca:
    enabled: false
    provider: "surepass"
    api_key: "${MCA_API_KEY}"
    rate_limit: 10

# Sentiment data sources
sentiment:
  newsapi:
    enabled: true
    api_key: "${NEWSAPI_KEY}"
    lookback_days: 30
    rate_limit: 5
```

**Estimated Effort**: 30 minutes
**Complexity**: Low

---

## 📊 Implementation Summary

| Component | Status | Completion | Effort Remaining |
|-----------|--------|------------|------------------|
| **Design Document** | ✅ Complete | 100% | 0h |
| **Database Schema** | ✅ Complete | 100% | 0h |
| **Forensics Module** | ✅ Complete | 100% | 0h (testing pending) |
| **Governance Module** | 🔴 Not Started | 0% | 4-6h |
| **Sentiment Module** | 🔴 Not Started | 0% | 3-4h |
| **Composite Scoring** | 🔴 Not Started | 0% | 3-4h |
| **CLI Integration** | 🔴 Not Started | 0% | 1-2h |
| **Testing** | 🔴 Not Started | 0% | 4-6h |
| **Configuration** | 🔴 Not Started | 0% | 0.5h |
| **Overall** | 🟡 In Progress | **35%** | **16-23h** |

---

## 🎯 Next Steps

### Immediate (Phase 3.2)
1. **Create Governance Stubs** (30 min)
   - `governance/__init__.py`
   - `governance/edgar.py` with placeholder functions
   - `governance/mca.py` with placeholder functions
   - `governance/scoring.py` with stub that returns 0

2. **Create Sentiment Stubs** (30 min)
   - `sentiment/__init__.py`
   - `sentiment/news.py` with placeholder functions
   - `sentiment/keywords.py` with adverse keyword dict
   - `sentiment/scoring.py` with stub that returns 0

3. **Implement Basic Screening Pipeline** (2-3 hours)
   - `risk/scoring.py` with composite score calculation
   - `risk/screening.py` with orchestration logic
   - Focus on forensics-only initially
   - Add governance/sentiment integration points

4. **CLI Integration** (1-2 hours)
   - Add `screen redflags` command
   - Update `screen all` to include Stage 2.4
   - Test with existing mock data

5. **End-to-End Testing** (2-3 hours)
   - Run pipeline on 30 business filter survivors
   - Validate forensics calculations
   - Check CSV output format
   - Verify determinism

### Short Term (Phase 3.3)
6. **Implement EDGAR Integration** (4-6 hours)
   - CIK lookup
   - Form 4 parsing
   - Insider metrics calculation
   - Caching with TTL=30d

7. **Implement NewsAPI Integration** (3-4 hours)
   - Query construction
   - Headline scanning
   - Keyword matching
   - Caching with TTL=7d

8. **Add Unit Tests** (4-6 hours)
   - Forensics tests with fixtures
   - Governance tests with mocked APIs
   - Sentiment tests with mocked APIs
   - Scoring tests

### Medium Term (Phase 3.4)
9. **Production Hardening**
   - Rate limit handling
   - Error recovery
   - Monitoring/logging
   - Performance optimization

10. **Documentation**
    - API setup guides (EDGAR, NewsAPI)
    - Configuration examples
    - Interpretation guidelines
    - Troubleshooting

---

## 🔬 Testing Strategy

### Current Approach (Recommended)
1. **Phase 3.2**: Implement with stubs, test forensics-only pipeline
2. **Phase 3.3**: Add real API integrations, test with API keys
3. **Phase 3.4**: Comprehensive testing with production data

### Alternative Approach (Faster MVP)
1. **Forensics-Only MVP**: Ship Stage 2.4 with forensics scoring only
2. **Incremental API Addition**: Add EDGAR, then NewsAPI later
3. **Progressive Enhancement**: Governance and sentiment as "nice-to-have"

**Recommendation**: Start with forensics-only MVP to unblock Phase 4, add APIs incrementally.

---

## 📚 Resources Needed

### API Accounts Required

| API | Purpose | Cost | Setup Time |
|-----|---------|------|------------|
| **SEC EDGAR** | US insider data | FREE | 10 min (no key required) |
| **NewsAPI** | News sentiment | FREE tier (100 req/day) or $449/mo | 5 min |
| **MCA Provider** | India governance | Varies by provider | 1-2 days |

### SEC EDGAR Setup
```bash
# No API key required, just set User-Agent
curl -H "User-Agent: MultiBagger/1.0 (your-email@example.com)" \
  https://data.sec.gov/submissions/CIK0000320193.json
```

### NewsAPI Setup
```bash
# Sign up at https://newsapi.org
# Free tier: 100 requests/day, 1 month history
export NEWSAPI_KEY="your-api-key"
```

---

## ✅ Acceptance Criteria (Current Status)

| Criterion | Target | Current | Status |
|-----------|--------|---------|--------|
| **Batch-first processing** | No loops | ✅ Forensics | 🟡 Partial |
| **Deterministic outputs** | Same --as-of → same results | ⚠️ Not tested | 🔴 Pending |
| **Forensics coverage** | ≥95% | ✅ 100% (local) | ✅ Met |
| **Governance coverage** | ≥80% | ⚠️ 0% (stub) | 🔴 Not met |
| **Sentiment coverage** | ≥80% | ⚠️ 0% (stub) | 🔴 Not met |
| **Composite score persisted** | DB + CSV | ⚠️ Schema only | 🔴 Pending |
| **Runtime ≤60s** | 30 survivors | ⚠️ Not tested | 🔴 Pending |
| **No scraping** | APIs only | ✅ Design compliant | ✅ Met |
| **TTLs respected** | 90d/30d/7d | ⚠️ Not impl | 🔴 Pending |

---

## 🚀 Deployment Checklist

### Before Production
- [ ] Complete governance module (EDGAR)
- [ ] Complete sentiment module (NewsAPI)
- [ ] Add comprehensive unit tests
- [ ] Test with real API keys
- [ ] Validate against known manipulators
- [ ] Performance benchmarking (30-100 survivors)
- [ ] Error handling for API failures
- [ ] Rate limit monitoring
- [ ] Documentation for API setup

### MVP Release (Forensics-Only)
- [x] Schema deployed
- [x] Forensics module complete
- [ ] Basic screening pipeline
- [ ] CLI integration
- [ ] CSV output format
- [ ] End-to-end test with mock data
- [ ] Configuration documentation

---

**Document Updated**: 2025-11-10
**Next Milestone**: Complete governance/sentiment stubs + basic pipeline (Phase 3.2)
**Estimated Time to MVP**: 6-8 hours
**Estimated Time to Full Release**: 20-25 hours
