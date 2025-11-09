Product Requirements Document: Multi-Bagger Research System
A practical, no-BS approach to building a personal investment research pipeline
🎯 Purpose & Goals
What We're Building
A simple, efficient system that screens 5000 stocks monthly to find 5-10 potential multi-baggers. Not a hedge fund platform - just a reliable tool for systematic personal investing.
Success Criteria

Process 5000 stocks in < 10 minutes
Generate 10-15 deep research candidates monthly
Catch 80% of obvious red flags
Find 2-3 multi-baggers per year
Total monthly time investment: < 70 hours

Core Principles

Filter Fast, Research Deep: Eliminate 99% quickly, study 1% thoroughly
Cache Everything: Financials don't change daily
Batch Operations: One API call beats hundred calls
Simple > Complex: Working code beats perfect architecture

🛠 Tech Stack
Core Technologies
yamlLanguage: Python 3.10+
Database: SQLite (yes, SQLite - we're not Netflix)
Cache: Redis (or just pickle files if lazy)
Scheduler: cron (simple monthly job)
Reports: Markdown → PDF (via pandoc)
Deployment: Single VPS or local machine
Key Libraries
python# Data fetching
yfinance          # US market data
beautifulsoup4    # Web scraping
requests          # API calls
selenium          # When scraping needs JS

# Data processing

pandas            # Data manipulation
numpy             # Calculations
scipy             # Statistical analysis

# Storage

sqlite3           # Database
redis             # Caching (optional)
pickle            # Simple cache alternative

# Reporting

matplotlib        # Charts
jinja2            # Report templates
markdown2         # Markdown processing
reportlab         # PDF generation
Data Sources
yamlUS Markets:

- Yahoo Finance (yfinance): Free, reliable
- SEC EDGAR: Filings, insider data
- Finviz: Screening, quick metrics
- AlphaVantage: Backup fundamental data

Indian Markets:

- Screener.in: Best free Indian data
- NSE/BSE APIs: Official exchange data
- Moneycontrol: Backup source
- Trendlyne: Additional metrics

📋 Implementation Phases
Phase 1: Data Infrastructure (Week 1)
Goal
Set up efficient data fetching and caching to avoid redundant API calls.
Task 1.1: Database Setup
python# schema.sql
CREATE TABLE stocks (
    ticker TEXT PRIMARY KEY,
    exchange TEXT,
    name TEXT,
    sector TEXT,
    market_cap REAL,
    last_updated DATE
);

CREATE TABLE financials (
    ticker TEXT,
    period DATE,
    revenue REAL,
    profit REAL,
    roce REAL,
    debt_equity REAL,
    PRIMARY KEY (ticker, period)
);

CREATE TABLE cache (
    key TEXT PRIMARY KEY,
    data BLOB,
    expires_at TIMESTAMP
);
Task 1.2: API Wrapper with Caching
python# data.py
import yfinance as yf
import pickle
from datetime import datetime, timedelta

class DataFetcher:
    def __init__(self):
        self.cache = {}  # Or Redis

    def get_data(self, ticker, data_type='price', force=False):
        """Smart fetching with cache"""
        cache_key = f"{ticker}_{data_type}"
        
        # Check cache first
        if not force and cache_key in self.cache:
            data, expires = self.cache[cache_key]
            if datetime.now() < expires:
                return data
        
        # Fetch fresh data
        data = self._fetch_fresh(ticker, data_type)
        
        # Cache it
        ttl = {'price': 1, 'fundamental': 90}[data_type]
        expires = datetime.now() + timedelta(days=ttl)
        self.cache[cache_key] = (data, expires)
        
        return data
Task 1.3: Universe Builder
python# universe.py
def get_universe():
    """Get all tradable stocks"""

    # US stocks - S&P 500 + Russell 2000
    us_tickers = []
    
    # Method 1: From Wikipedia
    sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
    us_tickers.extend(sp500['Symbol'].tolist())
    
    # Method 2: From exchange files
    nasdaq_csv = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
    
    # India stocks - NSE all
    india_tickers = []
    nse_csv = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    return us_tickers + india_tickers
Deliverables

✅ SQLite database with schema
✅ Caching layer (Redis or file-based)
✅ Universe of ~5000 stocks

Phase 2: Fast Filtering Pipeline (Week 1)
Goal
Reduce 5000 stocks to 500 in under 30 seconds using basic filters.
Task 2.1: Quick Screener
python# screener.py
class QuickScreener:
    """Stage 1: 5000 → 500 stocks in 30 seconds"""

    def screen(self, universe):
        # Use bulk API for efficiency
        results = []
        
        # For US: Use Finviz screener
        us_stocks = self.screen_us_batch(universe['US'])
        
        # For India: Use Screener.in API
        india_stocks = self.screen_india_batch(universe['India'])
        
        return us_stocks + india_stocks
    
    def screen_us_batch(self, tickers):
        """Example using finvizfinance"""
        from finvizfinance.screener import Screener
        
        stock_screener = Screener()
        filters = {
            'Market Cap.': 'Small ($300mln to $2bln)',
            'P/E': 'Under 30',
            'Price': 'Over $5',
            'Volume': 'Over 100K'
        }
        stock_screener.set_filter(filters)
        return stock_screener.get_ticker()
Task 2.2: Quality Filter
python# filters.py
def quality_filter(stocks):
    """Stage 2: 500 → 100 stocks"""

    # Batch fetch fundamental data
    batch_data = yf.download(stocks, period='5y', group_by='ticker')
    
    qualified = []
    for ticker in stocks:
        try:
            metrics = calculate_metrics(batch_data[ticker])
            
            if (metrics['roce'] > 15 and 
                metrics['revenue_growth'] > 10 and
                metrics['debt_equity'] < 1):
                qualified.append(ticker)
                
        except:
            continue  # Skip if data missing
    
    return qualified
Task 2.3: Business Filter
pythondef business_filter(stocks):
    """Stage 3: 100 → 30 stocks"""

    survivors = []
    
    for ticker in stocks:
        data = get_financial_data(ticker)
        
        # Check consistency
        if has_consistent_growth(data) and \
           has_positive_cash_flow(data) and \
           has_pricing_power(data):
            survivors.append(ticker)
    
    return survivors
Example Output
python# After Stage 1 (30 seconds)
print(f"Quick Screen: 5000 → {len(stage1_results)} stocks")

# Output: Quick Screen: 5000 → 523 stocks

# After Stage 2 (5 minutes)

print(f"Quality Filter: 523 → {len(stage2_results)} stocks")

# Output: Quality Filter: 523 → 97 stocks

# After Stage 3 (30 minutes)  

print(f"Business Filter: 97 → {len(stage3_results)} stocks")

# Output: Business Filter: 97 → 28 stocks

Phase 3: Red Flag Detection (Week 2)
Goal
Identify accounting/governance red flags to eliminate risky stocks.
Task 3.1: Forensic Metrics
python# forensics.py
def calculate_mscore(ticker):
    """Beneish M-Score for manipulation detection"""

    # Get 2 years of data
    current = get_financials(ticker, year=2024)
    prior = get_financials(ticker, year=2023)
    
    # 8 variables for M-Score
    dsri = (current.receivables/current.sales) / \
           (prior.receivables/prior.sales)
    gmi = (prior.gross_margin) / (current.gross_margin)
    aqi = (current.non_current_assets/current.total_assets) / \
          (prior.non_current_assets/prior.total_assets)
    # ... other variables
    
    m_score = -4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi
    
    return m_score  # > -2.22 indicates possible manipulation
Task 3.2: Management Checks
pythondef check_management(ticker):
    """Check for management red flags"""

    flags = []
    
    # Insider selling
    insider_data = get_insider_transactions(ticker)
    if net_insider_selling(insider_data) > 25:
        flags.append("Heavy insider selling")
    
    # India specific - promoter pledging
    if is_indian_stock(ticker):
        pledge_data = get_promoter_pledge(ticker)
        if pledge_data > 25:
            flags.append("High promoter pledge")
    
    return flags
Task 3.3: News Sentiment
pythondef check_news_sentiment(ticker):
    """Scan for negative news"""

    from newsapi import NewsApiClient
    
    news = newsapi.get_everything(q=ticker, 
                                  language='en',
                                  sort_by='relevancy')
    
    negative_keywords = ['fraud', 'investigation', 'lawsuit', 
                        'bankruptcy', 'scandal', 'SEC', 'SEBI']
    
    red_flags = []
    for article in news['articles'][:10]:
        if any(word in article['title'].lower() for word in negative_keywords):
            red_flags.append(article['title'])
    
    return red_flags
Deliverable
python# After red flag filtering
print(f"Clean stocks: 28 → {len(clean_stocks)} stocks")

# Output: Clean stocks: 28 → 14 stocks

# Show eliminated stocks with reasons

for ticker, reason in eliminated.items():
    print(f"{ticker}: {reason}")

# ENRON: M-Score = -1.5 (manipulation risk)

# NIKOLA: Heavy insider selling (45%)

# DHFL: High promoter pledge (67%)

Phase 4: Deep Research Module (Week 2-3)
Goal
Generate institutional-quality research reports for final 10-15 stocks.
Task 4.1: Business Analysis
python# researcher.py
class DeepResearcher:
    def analyze_business(self, ticker):
        """Comprehensive business analysis"""

        analysis = {
            'business_model': self.extract_business_model(ticker),
            'moat': self.identify_moat(ticker),
            'competition': self.analyze_competition(ticker),
            'growth_drivers': self.find_catalysts(ticker)
        }
        
        return analysis
    
    def extract_business_model(self, ticker):
        """Parse annual report for business description"""
        
        # Get latest 10-K or annual report
        filing = get_latest_filing(ticker)
        
        # Extract business section
        business_section = extract_section(filing, "Business")
        
        # Summarize using simple keywords
        return {
            'revenue_model': detect_revenue_model(business_section),
            'customer_base': extract_customers(business_section),
            'key_products': extract_products(business_section)
        }
Task 4.2: Valuation Model
pythondef build_dcf_model(ticker):
    """Simple DCF valuation"""

    # Historical data
    historicals = get_financials(ticker, years=5)
    
    # Growth assumptions
    revenue_growth = calculate_cagr(historicals.revenue)
    margin_trend = analyze_trend(historicals.margins)
    
    # Project 5 years
    projections = []
    for year in range(1, 6):
        revenue = historicals.revenue[-1] * (1 + revenue_growth)**year
        fcf = revenue * historicals.fcf_margin
        pv = fcf / (1 + 0.10)**year  # 10% discount rate
        projections.append(pv)
    
    # Terminal value
    terminal = projections[-1] * 10  # 10x terminal multiple
    pv_terminal = terminal / (1 + 0.10)**5
    
    fair_value = sum(projections) + pv_terminal
    current_price = get_price(ticker)
    
    return {
        'fair_value': fair_value,
        'current_price': current_price,
        'upside': (fair_value/current_price - 1) * 100
    }
Task 4.3: Report Generation
python# reports.py
def generate_report(ticker, analysis):
    """Create PDF research report"""

    template = """
    # Investment Thesis: {ticker}
    
    ## Executive Summary
    - **Recommendation**: {recommendation}
    - **Target Price**: ${target_price} ({upside}% upside)
    - **Risk/Reward**: {risk_reward}
    
    ## Business Analysis
    {business_description}
    
    ## Competitive Advantages
    {moat_analysis}
    
    ## Valuation
    {dcf_analysis}
    
    ## Risks
    {risk_factors}
    
    ## Catalyst Timeline
    {catalysts}
    """
    
    # Fill template
    report = template.format(**analysis)
    
    # Convert to PDF
    save_as_pdf(report, f"{ticker}_research.pdf")

Phase 5: Portfolio Management (Week 4)
Goal
Build and monitor concentrated portfolio of 5-10 positions.
Task 5.1: Portfolio Construction
python# portfolio.py
def build_portfolio(candidates):
    """Position sizing based on conviction"""

    portfolio = []
    
    for stock in candidates:
        score = stock['conviction_score']
        
        # Position sizing rules
        if score > 90:
            weight = 0.20  # 20% for highest conviction
        elif score > 80:
            weight = 0.15  # 15% for high conviction
        else:
            weight = 0.10  # 10% for moderate conviction
        
        portfolio.append({
            'ticker': stock['ticker'],
            'weight': weight,
            'entry_price': get_price(stock['ticker']),
            'target_price': stock['fair_value'],
            'stop_loss': stock['entry_price'] * 0.75
        })
    
    return portfolio[:7]  # Max 7 positions
Task 5.2: Monitoring System
python# monitor.py
def monitor_portfolio(portfolio):
    """Daily monitoring with alerts"""

    alerts = []
    
    for position in portfolio:
        current_price = get_price(position.ticker)
        
        # Check triggers
        if current_price < position.stop_loss:
            alerts.append(f"STOP LOSS: {position.ticker}")
        
        if current_price > position.target * 0.9:
            alerts.append(f"NEAR TARGET: {position.ticker}")
        
        # Check news
        if has_negative_news(position.ticker):
            alerts.append(f"CHECK NEWS: {position.ticker}")
    
    return alerts
Task 5.3: Monthly Rebalancing
pythondef monthly_rebalance():
    """Run monthly pipeline and update portfolio"""

    # Run full pipeline
    new_candidates = run_screening_pipeline()
    
    # Compare with existing
    current_portfolio = load_portfolio()
    
    # Decisions
    actions = []
    for position in current_portfolio:
        if position.ticker not in new_candidates:
            if position.return < -20:
                actions.append(('SELL', position.ticker, 'Thesis broken'))
            else:
                actions.append(('HOLD', position.ticker, 'Monitor closely'))
    
    # Add new winners
    for candidate in new_candidates[:3]:
        if candidate not in current_portfolio:
            actions.append(('BUY', candidate, 'New opportunity'))
    
    return actions

📊 Example Monthly Run
python# run.py - The main execution script
def main():
    print("=== Monthly Multi-Bagger Hunt ===\n")

    # Stage 0: Get universe
    print("Loading universe...")
    universe = get_universe()  # 5000 stocks
    print(f"Universe: {len(universe)} stocks\n")
    
    # Stage 1: Quick filter
    print("Stage 1: Quick screening...")
    survivors = quick_screen(universe)
    print(f"→ {len(survivors)} stocks passed (10%)\n")
    
    # Stage 2: Quality filter
    print("Stage 2: Quality filter...")
    quality = quality_filter(survivors)
    print(f"→ {len(quality)} stocks passed (2%)\n")
    
    # Stage 3: Business filter
    print("Stage 3: Business analysis...")
    candidates = business_filter(quality)
    print(f"→ {len(candidates)} stocks passed (0.6%)\n")
    
    # Stage 4: Red flags
    print("Stage 4: Red flag check...")
    clean = red_flag_filter(candidates)
    print(f"→ {len(clean)} stocks passed (0.3%)\n")
    
    # Stage 5: Deep research
    print("Stage 5: Deep research...")
    for ticker in clean:
        print(f"  Researching {ticker}...")
        report = deep_research(ticker)
        save_report(report)
    
    print(f"\n✅ Generated {len(clean)} research reports")
    print("📊 Check ./reports/ folder for details")

if __name__ == "__main__":
    main()

```

### Expected Output
```

=== Monthly Multi-Bagger Hunt ===

Loading universe...
Universe: 5000 stocks

Stage 1: Quick screening...
→ 487 stocks passed (10%)

Stage 2: Quality filter...
→ 93 stocks passed (2%)

Stage 3: Business analysis...
→ 31 stocks passed (0.6%)

Stage 4: Red flag check...
→ 14 stocks passed (0.3%)

Stage 5: Deep research...
  Researching AAPL...
  Researching HDFC...
  Researching MSFT...
  [... 11 more stocks ...]

✅ Generated 14 research reports
📊 Check ./reports/ folder for details

🚀 Deployment & Operations
Setup Instructions
bash# 1. Clone and setup
git clone [repo]
cd multibagger
pip install -r requirements.txt

# 2. Configure data sources

cp config.example.yml config.yml

# Add your API keys

# 3. Initialize database

python setup.py

# 4. Run first screen

python run.py

# 5. Schedule monthly

crontab -e

# Add: 0 0 1 ** cd /path/to/multibagger && python run.py

Monthly Checklist

 Week 1: Run screening pipeline
 Week 2: Complete deep research
 Week 3: Make portfolio decisions
 Week 4: Set up monitoring alerts

Cost Structure

APIs: $0 (all free tiers)
Server: $5/month (DigitalOcean droplet)
Time: 70 hours/month
Return Target: 2-3 multi-baggers/year

✅ Success Metrics
Technical KPIs

Pipeline execution time: < 10 minutes
API calls per run: < 100
Cache hit rate: > 80%
Report generation: < 5 min/stock

Investment KPIs

Stocks screened: 5000/month
Deep research candidates: 10-15/month
Portfolio positions: 5-7
Multi-baggers found: 2-3/year

This PRD provides a practical, implementable approach to building a multi-bagger research system that actually works. Start with Phase 1, get it working, then iterate. Remember: done is better than perfect.
