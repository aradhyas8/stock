# Phase 3: Red Flag Detection System - Design Document

**Date**: 2025-11-10
**Phase**: 3 - Stage 2.4: Red Flag Filter
**Goal**: Multi-layered risk assessment for final candidate validation

---

## 🎯 Objectives

Implement a comprehensive red flag detection system with three risk layers:

1. **Accounting/Forensics**: Detect earnings manipulation, financial distress
2. **Governance/Insiders**: Monitor insider activity, ownership concentration
3. **News/Sentiment**: Identify adverse events and negative publicity

**Output**: Composite risk score (0-100) with explainable component breakdowns

---

## 📊 Think First: Signal Mapping

### Layer 1: Accounting/Forensics (Derived Locally)

#### Beneish M-Score (Earnings Manipulation Detection)

**Formula**:
```
M-Score = -4.84 + 0.92×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI + 0.115×DEPI
          - 0.172×SGAI + 4.679×TATA - 0.327×LVGI
```

**Component Formulas**:

| Component | Formula | Required Fields | Source Table |
|-----------|---------|-----------------|--------------|
| **DSRI** (Days Sales in Receivables Index) | (AR_t / Sales_t) / (AR_t-1 / Sales_t-1) | receivables, revenue | fundamentals |
| **GMI** (Gross Margin Index) | GM_t-1 / GM_t | gross_profit, revenue | fundamentals |
| **AQI** (Asset Quality Index) | (1 - (CA_t + PPE_t)/TA_t) / (1 - (CA_t-1 + PPE_t-1)/TA_t-1) | current_assets, ppe, total_assets | fundamentals |
| **SGI** (Sales Growth Index) | Sales_t / Sales_t-1 | revenue | fundamentals |
| **DEPI** (Depreciation Index) | (Depr_t-1 / (Depr_t-1 + PPE_t-1)) / (Depr_t / (Depr_t + PPE_t)) | depreciation, ppe | fundamentals |
| **SGAI** (SG&A Index) | (SGA_t / Sales_t) / (SGA_t-1 / Sales_t-1) | sga_expense, revenue | fundamentals |
| **TATA** (Total Accruals to Total Assets) | (ΔWC - Depr) / TA | working_capital, depreciation, total_assets | fundamentals |
| **LVGI** (Leverage Index) | ((LTD_t + CL_t)/TA_t) / ((LTD_t-1 + CL_t-1)/TA_t-1) | long_term_debt, current_liabilities, total_assets | fundamentals |

**Interpretation**:
- M-Score > -2.22: High probability of manipulation (RED FLAG)
- M-Score ≤ -2.22: Lower probability (PASS)

**Data Requirements**:
- **Minimum**: 2 years of annual fundamentals (current + prior)
- **Optimal**: 3+ years for trend validation
- **Fields needed**: See component formulas above

#### Altman Z-Score (Bankruptcy Risk)

**Formula** (for publicly traded manufacturing):
```
Z = 1.2×(WC/TA) + 1.4×(RE/TA) + 3.3×(EBIT/TA) + 0.6×(MVE/TL) + 1.0×(Sales/TA)
```

**Component Formulas**:

| Component | Formula | Required Fields | Source Table |
|-----------|---------|-----------------|--------------|
| **WC/TA** | (Current Assets - Current Liabilities) / Total Assets | current_assets, current_liabilities, total_assets | fundamentals |
| **RE/TA** | Retained Earnings / Total Assets | retained_earnings, total_assets | fundamentals |
| **EBIT/TA** | EBIT / Total Assets | ebit, total_assets | fundamentals |
| **MVE/TL** | Market Cap / Total Liabilities | market_cap (tickers), total_liabilities | tickers, fundamentals |
| **Sales/TA** | Revenue / Total Assets | revenue, total_assets | fundamentals |

**Interpretation**:
- Z < 1.81: High risk of bankruptcy (RED FLAG)
- 1.81 ≤ Z ≤ 2.99: Gray zone (CAUTION)
- Z > 2.99: Safe zone (PASS)

**Data Requirements**:
- Latest annual fundamentals
- Current market cap from tickers table
- **Fields needed**: See component formulas above

#### Sloan Accruals (Earnings Quality)

**Formula**:
```
Accruals = (ΔCA - ΔCash - ΔCL + ΔSTD - Depreciation) / Average Total Assets
```

**Component Formulas**:

| Component | Formula | Required Fields | Source Table |
|-----------|---------|-----------------|--------------|
| **ΔCA** | Current Assets_t - Current Assets_t-1 | current_assets | fundamentals |
| **ΔCash** | Cash_t - Cash_t-1 | cash | fundamentals |
| **ΔCL** | Current Liabilities_t - Current Liabilities_t-1 | current_liabilities | fundamentals |
| **ΔSTD** | Short-term Debt_t - Short-term Debt_t-1 | short_term_debt | fundamentals |
| **Depreciation** | Depreciation Expense | depreciation | fundamentals |
| **Avg TA** | (Total Assets_t + Total Assets_t-1) / 2 | total_assets | fundamentals |

**Interpretation**:
- High positive accruals (> 10% of assets): Earnings quality concern (RED FLAG)
- Negative accruals: Conservative accounting (PASS)

**Data Requirements**:
- 2 years of annual fundamentals
- **Fields needed**: See component formulas above

---

### Layer 2: Governance/Insiders (External APIs)

#### US Insiders (SEC EDGAR)

**Data Source**: SEC EDGAR API (JSON format, no scraping)

**Endpoints**:
```
# Company CIK lookup
GET https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&output=json

# Recent Form 4 filings (insider transactions)
GET https://data.sec.gov/submissions/CIK{cik_padded}.json

# Ownership data
GET https://www.sec.gov/cgi-bin/own-disp?action=getissuer&CIK={cik}
```

**Metrics to Extract**:

| Metric | Formula | Data Source | Interpretation |
|--------|---------|-------------|----------------|
| **Net Insider Selling (90d)** | (Total Shares Sold - Total Shares Bought) / Total Shares Outstanding | Form 4 transactions | > 2% in 90 days = RED FLAG |
| **Insider Sell/Buy Ratio** | Sell Transactions / Buy Transactions | Form 4 transactions | > 3:1 = CAUTION |
| **Officer/Director Selling** | % of officers/directors with net sells | Form 4 transactions | > 50% = RED FLAG |

**Cache Strategy**:
- TTL: 30 days
- Batch by CIK
- Store JSON payloads
- Extract transaction summaries

**Required Fields** (from SEC JSON):
- `transactions.transactionAmounts.transactionShares`
- `transactions.transactionCoding.transactionCode` (P=Buy, S=Sell)
- `transactions.transactionDate.value`
- `reportingOwner.reportingOwnerRelationship.isOfficer/isDirector`

#### India Insiders (MCA, Optional)

**Data Source**: MCA providers (Surepass, Zyla, etc.) - config toggle

**Endpoints** (example):
```
# Company master data
GET https://api.surepass.io/v1/mca/company-master

# Shareholding pattern
GET https://api.surepass.io/v1/mca/shareholding

# Pledge data
GET https://api.surepass.io/v1/mca/pledge-status
```

**Metrics to Extract**:

| Metric | Formula | Data Source | Interpretation |
|--------|---------|-------------|----------------|
| **Promoter Pledge %** | Pledged Shares / Total Promoter Holding | Pledge API | > 50% = RED FLAG, > 25% = CAUTION |
| **Promoter Selling** | Change in promoter holding (YoY) | Shareholding API | < -5% = RED FLAG |

**Cache Strategy**:
- TTL: 30 days
- Batch by CIN
- Store JSON payloads
- Graceful fallback if disabled/rate-limited

**Configuration**:
```yaml
governance:
  mca:
    enabled: false  # Toggle for India companies
    provider: "surepass"
    api_key: "${MCA_API_KEY}"
    rate_limit: 10  # requests per minute
```

---

### Layer 3: News/Sentiment (External APIs)

#### NewsAPI Integration

**Data Source**: NewsAPI (https://newsapi.org)

**Endpoint**:
```
GET https://newsapi.org/v2/everything?q={query}&from={date}&sortBy=publishedAt
```

**Query Construction**:
```python
query = f'"{ticker.symbol}" AND ("{ticker.name}" OR "{exchange.code}")'
```

**Adverse Keywords** (weighted):

| Category | Keywords | Weight | Interpretation |
|----------|----------|--------|----------------|
| **Legal** | fraud, investigation, lawsuit, indictment, SEC probe | 10 | Critical |
| **Financial Distress** | bankruptcy, insolvency, default, restructuring | 9 | Critical |
| **Governance** | resignation, departed, scandal, misconduct | 7 | High |
| **Market Action** | downgrade, suspended, delisted, halted | 6 | High |
| **Risk Events** | pledge, margin call, liquidity crisis | 5 | Medium |

**Metrics to Extract**:

| Metric | Formula | Data Source | Interpretation |
|--------|---------|-------------|----------------|
| **Negative News Count (30d)** | Count of articles with adverse keywords | NewsAPI | ≥ 3 critical keywords = RED FLAG |
| **Severity Score** | Σ(keyword_weight × frequency) / total_articles | NewsAPI | > 50 = RED FLAG |
| **Latest Adverse Date** | Most recent article with adverse keyword | NewsAPI | < 7 days = CAUTION |

**Cache Strategy**:
- TTL: 7 days
- Lookback: 30 days (aligned to month-end)
- Store headline + date + source only (no full text)
- Batch queries with 1-second delay

**Configuration**:
```yaml
sentiment:
  news:
    enabled: true
    provider: "newsapi"
    api_key: "${NEWSAPI_KEY}"
    lookback_days: 30
    rate_limit: 5  # requests per second
```

---

## 🏗️ Architecture Design

### Country/Exchange Routing Logic

```python
def route_governance_source(ticker: dict, config: dict) -> str:
    """
    Determine governance data source based on exchange.

    Returns: 'edgar' | 'mca' | 'skip'
    """
    exchange_code = ticker['exchange_code']

    # US exchanges → SEC EDGAR
    if exchange_code in ['NYSE', 'NASDAQ', 'AMEX']:
        return 'edgar'

    # India exchanges → MCA (if enabled)
    if exchange_code in ['NSE', 'BSE']:
        if config.get('governance', {}).get('mca', {}).get('enabled', False):
            return 'mca'
        else:
            logger.info(f"MCA disabled for {ticker['symbol']}, skipping governance")
            return 'skip'

    # Other exchanges → skip gracefully
    logger.info(f"No governance source for exchange {exchange_code}")
    return 'skip'
```

### Batch Processing Plan

**Input**: Stage 2.3 survivors (~30 tickers)

**Processing Flow**:

```
Stage 2.3 Survivors (30 tickers)
          ↓
┌─────────────────────────────────────────┐
│  1. Forensics (Local Computation)       │
│     - Fetch fundamentals (2-3 years)    │
│     - Vectorized pandas computation     │
│     - Beneish M-Score                   │
│     - Altman Z-Score                    │
│     - Sloan Accruals                    │
│     Runtime: ~0.1s                      │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│  2. Governance (External APIs)          │
│     - Route by exchange (US/India/skip) │
│     - EDGAR: Batch by CIK (5/batch)     │
│     - MCA: Batch by CIN (if enabled)    │
│     - Cache with TTL=30d                │
│     - Rate limit: 1 req/sec             │
│     Runtime: ~30s (30 tickers)          │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│  3. Sentiment (External APIs)           │
│     - NewsAPI: Query per ticker         │
│     - Lookback: 30 days                 │
│     - Cache with TTL=7d                 │
│     - Rate limit: 1 req/sec             │
│     Runtime: ~30s (30 tickers)          │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│  4. Composite Scoring                   │
│     - Normalize sub-scores (0-100)      │
│     - Apply weights from config         │
│     - Generate explainable details      │
│     - Record first-fail reason          │
│     Runtime: ~0.1s                      │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│  5. Persistence                         │
│     - Insert into risk_flags table      │
│     - Save stage_redflags_YYYY-MM.csv   │
│     Runtime: ~0.1s                      │
└─────────────────────────────────────────┘
          ↓
    Final Candidates (15-20 tickers)
```

**Total Runtime Estimate**: ~60s for 30 tickers (dominated by API calls)

### Scoring & Weights

**Default Weights** (configurable):

```yaml
risk:
  weights:
    forensics: 0.50    # 50%
    governance: 0.30   # 30%
    sentiment: 0.20    # 20%

  thresholds:
    composite_score_max: 40  # Eliminate if > 40

    forensics:
      beneish_m_score_max: -2.22
      altman_z_score_min: 1.81
      accruals_max: 0.10  # 10% of assets

    governance:
      insider_sell_90d_max: 0.02  # 2% of shares
      promoter_pledge_max: 0.50   # 50%

    sentiment:
      neg_news_30d_max: 3  # articles with critical keywords
      severity_score_max: 50
```

**Sub-Score Normalization**:

```python
def normalize_forensics_score(m_score, z_score, accruals) -> float:
    """
    Convert forensics metrics to 0-100 risk score.

    Higher score = higher risk
    """
    # Beneish M-Score (invert: higher M-Score = higher risk)
    beneish_risk = 0
    if m_score > -2.22:
        # Above threshold: scale 0-40 based on severity
        beneish_risk = min(40, (m_score + 2.22) * 20)

    # Altman Z-Score (invert: lower Z = higher risk)
    altman_risk = 0
    if z_score < 2.99:
        if z_score < 1.81:
            altman_risk = 40  # High risk
        else:
            # Gray zone: scale 20-40
            altman_risk = 20 + (2.99 - z_score) / (2.99 - 1.81) * 20

    # Accruals (higher accruals = higher risk)
    accruals_risk = 0
    if accruals > 0.10:
        accruals_risk = min(20, accruals * 100)

    # Combined (max 100)
    return min(100, beneish_risk + altman_risk + accruals_risk)
```

**Composite Score Calculation**:

```python
def compute_composite_score(
    forensics_score: float,
    governance_score: float,
    sentiment_score: float,
    weights: dict
) -> float:
    """
    Weighted average of sub-scores.

    Returns: 0-100 (higher = higher risk)
    """
    composite = (
        forensics_score * weights['forensics'] +
        governance_score * weights['governance'] +
        sentiment_score * weights['sentiment']
    )

    return min(100, max(0, composite))
```

**First-Fail Logic** (Hard Stops):

```python
def determine_first_fail(metrics: dict, thresholds: dict) -> str | None:
    """
    Check for hard-stop conditions.

    Returns: Failure reason or None if all pass
    """
    # Critical forensics
    if metrics['beneish_m_score'] > -2.22 and metrics['beneish_trend'] == 'rising':
        return "beneish_m_score_critical"

    if metrics['altman_z_score'] < 1.81:
        return "altman_z_bankruptcy_risk"

    # Critical governance
    if metrics['promoter_pledge'] > 0.50:
        return "promoter_pledge_excessive"

    if metrics['insider_sell_90d'] > 0.05:  # 5% threshold for hard stop
        return "insider_selling_critical"

    # Critical sentiment
    if 'bankruptcy' in metrics['neg_keywords'] or 'fraud' in metrics['neg_keywords']:
        return "critical_adverse_news"

    return None
```

---

## 🗄️ Schema Design

### risk_flags Table

```sql
CREATE TABLE risk_flags (
    id INTEGER PRIMARY KEY,
    ticker_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,

    -- Forensics Metrics
    beneish_m_score NUMERIC(8, 4),
    altman_z_score NUMERIC(8, 4),
    accruals_ratio NUMERIC(8, 4),
    forensics_score NUMERIC(5, 2),  -- 0-100

    -- Governance Metrics
    insider_sell_90d NUMERIC(8, 4),  -- % of shares
    promoter_pledge NUMERIC(8, 4),   -- % of promoter holding
    governance_score NUMERIC(5, 2),  -- 0-100

    -- Sentiment Metrics
    neg_news_30d INTEGER,            -- count of adverse articles
    severity_score NUMERIC(5, 2),    -- weighted severity
    sentiment_score NUMERIC(5, 2),   -- 0-100

    -- Composite
    composite_score NUMERIC(5, 2),   -- 0-100 (weighted average)
    first_fail_reason VARCHAR(100),  -- null if no hard stop

    -- Explainability
    details_json TEXT,               -- full breakdown with provenance

    -- Metadata
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (ticker_id) REFERENCES tickers(id),
    UNIQUE (ticker_id, as_of_date)
);

-- Indexes
CREATE INDEX ix_risk_flags_ticker_date ON risk_flags(ticker_id, as_of_date);
CREATE INDEX ix_risk_flags_composite ON risk_flags(composite_score);
CREATE INDEX ix_risk_flags_date ON risk_flags(as_of_date);
```

**details_json Structure**:

```json
{
  "forensics": {
    "beneish": {
      "m_score": -2.45,
      "components": {
        "DSRI": 1.12,
        "GMI": 0.98,
        "AQI": 1.05,
        "SGI": 1.15,
        "DEPI": 0.92,
        "SGAI": 1.03,
        "TATA": 0.08,
        "LVGI": 1.01
      },
      "interpretation": "Low risk of manipulation"
    },
    "altman": {
      "z_score": 3.25,
      "components": {
        "WC_TA": 0.25,
        "RE_TA": 0.18,
        "EBIT_TA": 0.12,
        "MVE_TL": 2.50,
        "Sales_TA": 0.85
      },
      "interpretation": "Safe zone"
    },
    "accruals": {
      "ratio": 0.05,
      "interpretation": "Moderate accruals"
    }
  },
  "governance": {
    "source": "edgar",
    "insider_transactions": {
      "sell_count": 3,
      "buy_count": 1,
      "net_change": -0.015
    },
    "last_updated": "2025-11-01"
  },
  "sentiment": {
    "source": "newsapi",
    "articles_scanned": 12,
    "adverse_keywords": ["downgrade"],
    "latest_adverse_date": "2025-10-28",
    "severity": 15
  },
  "provenance": {
    "forensics_date": "2024-12-31",
    "governance_lookback": "2025-08-01 to 2025-11-01",
    "sentiment_lookback": "2025-10-01 to 2025-11-01"
  }
}
```

---

## 🔄 Determinism Strategy

### Month-End Alignment

**Problem**: News and insider data are continuously updated, making exact reproducibility difficult.

**Solution**: Align lookbacks to month-end boundaries relative to `--as-of`:

```python
def get_lookback_dates(as_of: datetime) -> dict:
    """
    Calculate deterministic lookback windows aligned to month-end.

    Args:
        as_of: YYYY-MM format, interpreted as end of month

    Returns:
        Dict with start/end dates for each data source
    """
    # Parse as_of to month-end
    as_of_date = datetime.strptime(as_of, "%Y-%m")
    month_end = (as_of_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    return {
        'forensics': {
            'latest_fiscal_year_end': month_end.year - 1,  # Prior fiscal year
        },
        'governance': {
            'start': month_end - timedelta(days=90),  # 90 days back
            'end': month_end,
        },
        'sentiment': {
            'start': month_end - timedelta(days=30),  # 30 days back
            'end': month_end,
        }
    }
```

**Example**:
- `--as-of 2025-11`: Lookbacks end at 2025-11-30
  - Forensics: Use fiscal year 2024 data
  - Governance: Transactions from 2025-09-01 to 2025-11-30
  - Sentiment: News from 2025-11-01 to 2025-11-30

### Cache Key Design

**Include as_of in cache keys** to ensure determinism:

```python
def generate_cache_key(url: str, as_of: str) -> str:
    """
    Generate cache key that includes as_of date.

    This ensures queries with different as_of dates don't collide.
    """
    return hashlib.md5(f"{url}|as_of={as_of}".encode()).hexdigest()
```

**Example**:
- Query: NewsAPI for AAPL, lookback 2025-10-01 to 2025-11-30
- Cache key: `md5("newsapi.org/v2/everything?q=AAPL&from=2025-10-01|as_of=2025-11")`
- TTL: 7 days
- Deterministic: Same query with same as_of always returns same cached result

---

## 📝 Implementation Checklist

### Phase 3.1: Schema & Infrastructure
- [ ] Create `risk_flags` table migration
- [ ] Add indexes for performance
- [ ] Create `forensics/` module directory
- [ ] Create `governance/` module directory
- [ ] Create `sentiment/` module directory
- [ ] Create `risk/` module directory
- [ ] Update config.example.yml with risk section

### Phase 3.2: Forensics Layer
- [ ] Implement Beneish M-Score calculation
- [ ] Implement Altman Z-Score calculation
- [ ] Implement Sloan Accruals calculation
- [ ] Add forensics scoring function
- [ ] Add unit tests with fixtures
- [ ] Validate against known examples

### Phase 3.3: Governance Layer
- [ ] Implement EDGAR adapter (SEC API)
- [ ] Implement CIK lookup
- [ ] Parse Form 4 transactions
- [ ] Calculate insider metrics
- [ ] Implement MCA adapter (optional, stub)
- [ ] Add governance scoring function
- [ ] Add caching with TTL=30d

### Phase 3.4: Sentiment Layer
- [ ] Implement NewsAPI adapter
- [ ] Define adverse keyword dictionary
- [ ] Parse and score headlines
- [ ] Calculate sentiment metrics
- [ ] Add sentiment scoring function
- [ ] Add caching with TTL=7d

### Phase 3.5: Scoring & Integration
- [ ] Implement composite scoring
- [ ] Implement first-fail logic
- [ ] Generate explainable details_json
- [ ] Normalize sub-scores (0-100)
- [ ] Apply configurable weights

### Phase 3.6: CLI & Pipeline
- [ ] Add `screen redflags` command
- [ ] Integrate into `screen all`
- [ ] Output stage_redflags_YYYY-MM.csv
- [ ] Update summary tables
- [ ] Add determinism tests
- [ ] Document API requirements

---

## 🧪 Testing Strategy

### Unit Tests

**Forensics** (`tests/test_forensics.py`):
```python
def test_beneish_m_score_calculation():
    """Test Beneish M-Score with known fixture"""
    fundamentals = create_manipulator_fixture()  # Known M-Score > -2.22
    m_score = compute_beneish_m_score(fundamentals)
    assert m_score > -2.22

def test_altman_z_score_bankruptcy():
    """Test Altman Z-Score for distressed company"""
    fundamentals = create_distressed_fixture()  # Known Z < 1.81
    z_score = compute_altman_z_score(fundamentals)
    assert z_score < 1.81
```

**Governance** (`tests/test_governance.py`):
```python
def test_edgar_insider_selling():
    """Test insider selling calculation from Form 4 data"""
    transactions = load_fixture('edgar_form4_sample.json')
    metrics = parse_insider_transactions(transactions)
    assert 'insider_sell_90d' in metrics
    assert 0 <= metrics['insider_sell_90d'] <= 1
```

**Sentiment** (`tests/test_sentiment.py`):
```python
def test_adverse_keyword_detection():
    """Test adverse keyword detection in headlines"""
    headlines = [
        "Company announces fraud investigation",
        "Positive earnings beat expectations"
    ]
    scores = score_headlines(headlines)
    assert scores['neg_news_30d'] == 1
    assert 'fraud' in scores['adverse_keywords']
```

### Integration Tests

**End-to-End** (`tests/test_screen_redflags.py`):
```python
def test_redflags_end_to_end(mock_api_responses):
    """Test complete red flag pipeline"""
    survivors = load_business_filter_survivors()

    with mock_edgar_api(), mock_newsapi():
        result = screen_redflags(
            config=config,
            survivors=survivors,
            as_of="2025-11"
        )

    assert len(result.survivors) > 0
    assert all(ticker['composite_score'] <= 40 for ticker in result.survivors)
    assert 'details_json' in result.survivors[0]
```

### Determinism Tests

```python
def test_determinism_same_as_of():
    """Verify identical outputs with same --as-of"""
    result1 = screen_redflags(config, survivors, as_of="2025-11")
    result2 = screen_redflags(config, survivors, as_of="2025-11")

    assert result1.survivors == result2.survivors
    assert result1.removed_by_rule == result2.removed_by_rule
```

---

## 📊 Expected Outputs

### CSV Output (stage_redflags_2025-11.csv)

```csv
ticker_id,symbol,name,composite_score,forensics_score,governance_score,sentiment_score,beneish_m_score,altman_z_score,accruals_ratio,insider_sell_90d,promoter_pledge,neg_news_30d,severity_score,first_fail_reason
1,AAPL,Apple Inc.,12.5,8.0,15.0,18.0,-3.45,5.2,0.03,0.005,,0,0,
3,GOOGL,Alphabet Inc.,25.3,20.0,28.0,32.0,-2.15,3.8,0.08,0.012,,1,15,
8,JPM,JPMorgan Chase,18.7,15.0,22.0,20.0,-2.89,4.1,0.05,0.008,,0,0,
```

### Summary Report

```
Red Flag Detection (Stage 2.4) Results
┏━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric        ┃ Value  ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Input Count   │ 30     │
│ Survivors     │ 18     │
│ Survival Rate │ 60.0%  │
│ Runtime       │ 62.5s  │
└───────────────┴────────┘

Risk Score Distribution
┏━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Score Range   ┃ Count ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 0-20 (Low)    │ 12    │
│ 20-40 (Med)   │ 6     │
│ 40-60 (High)  │ 8     │
│ 60+ (Critical)│ 4     │
└───────────────┴───────┘

Eliminated by Rule
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Rule                     ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ composite_score_max      │ 8     │
│ beneish_m_score_critical │ 2     │
│ promoter_pledge_max      │ 1     │
│ critical_adverse_news    │ 1     │
└──────────────────────────┴───────┘

Data Coverage
┏━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Source       ┃ Coverage┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Forensics    │ 100%    │
│ Governance   │ 87%     │
│ Sentiment    │ 93%     │
└──────────────┴─────────┘

API Rate Limit Stats
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ API          ┃ Calls / Limit┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ SEC EDGAR    │ 15 / 100     │
│ NewsAPI      │ 28 / 1000    │
└──────────────┴──────────────┘
```

---

## 🎯 Acceptance Criteria

### ✅ Functional Requirements
- [ ] Batch-first processing (no per-ticker loops)
- [ ] Deterministic outputs with same `--as-of`
- [ ] ≥95% coverage for forensics (derived locally)
- [ ] Graceful degradation if APIs disabled/rate-limited
- [ ] Composite score + explainable flags persisted
- [ ] CSV output generated in snapshots/

### ⚡ Performance Requirements
- [ ] Stage 2.4 adds ≤ 60s for 30 survivors on dev hardware
- [ ] API calls respect rate limits (no 429 errors)
- [ ] Cache hit rate > 80% on second run (same day)

### 🔒 Compliance Requirements
- [ ] No web scraping (APIs only)
- [ ] ToS-compliant API usage
- [ ] TTLs respected (forensics 90d, insiders 30d, news 7d)
- [ ] User-Agent headers set correctly

### 📊 Quality Requirements
- [ ] Unit tests for all metric calculations
- [ ] Integration tests with mocked APIs
- [ ] Determinism tests pass
- [ ] Error handling for missing data
- [ ] Logging at appropriate levels

---

## 📚 References

### Academic Papers
- **Beneish (1999)**: "The Detection of Earnings Manipulation"
- **Altman (1968)**: "Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy"
- **Sloan (1996)**: "Do Stock Prices Fully Reflect Information in Accruals?"

### API Documentation
- **SEC EDGAR**: https://www.sec.gov/edgar/sec-api-documentation
- **NewsAPI**: https://newsapi.org/docs
- **MCA Providers**: Surepass, Zyla (vendor-specific)

### Internal Documents
- **PHASE2_DESIGN.md**: Screening pipeline architecture
- **ARCHITECTURE_REVIEW.md**: Phase 2 review and patterns

---

**Document Status**: Ready for Implementation
**Next Step**: Begin Phase 3.1 (Schema & Infrastructure)
**Estimated Timeline**: 8-12 hours for complete implementation
