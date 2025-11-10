"""Data population orchestration for populating DB with real market data"""

import logging
import os
import time
from datetime import datetime, timedelta

import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.config import Config
from multibagger.database.models import Ticker, Price, Fundamental, Factor
from multibagger.database.schema import get_engine
from multibagger.data.cache import HttpCache

from .adapters.yfinance_adapter import YFinanceAdapter
from .adapters.alpha_vantage_adapter import AlphaVantageAdapter

logger = logging.getLogger(__name__)
console = Console()


class DataPopulator:
    """Orchestrates data population from APIs to database"""

    def __init__(self, config: Config):
        self.config = config
        self.engine = get_engine()
        self.adapter = YFinanceAdapter(batch_size=50, delay_seconds=1.0)

        # Initialize Alpha Vantage adapter if API key is available
        av_api_key = os.getenv('ALPHA_VANTAGE_KEY')
        if av_api_key:
            cache = HttpCache()  # Uses default DB path from get_engine()
            self.av_adapter = AlphaVantageAdapter(
                api_key=av_api_key,
                cache=cache,
                min_call_interval=12,  # Conservative for free tier (5 calls/min)
                ttl_days=90
            )
            logger.info("✓ Alpha Vantage adapter initialized with 90d cache TTL")
        else:
            self.av_adapter = None
            logger.warning("ALPHA_VANTAGE_KEY not set - fallback disabled")

        self.stats = {
            'prices_fetched': 0,
            'prices_inserted': 0,
            'fundamentals_fetched': 0,
            'fundamentals_inserted': 0,
            'factors_computed': 0,
            'errors': [],
            'start_time': None,
            'end_time': None,
            # Field coverage tracking for Phase 3.5
            'field_coverage': {
                field: {'yfinance': 0, 'alpha_vantage': 0, 'missing': 0}
                for field in ['receivables', 'ppe', 'depreciation', 'sga_expense',
                              'cash', 'short_term_debt', 'retained_earnings']
            }
        }

    def populate_all(self, sample_mode: bool = False, sample_size: int = 50) -> dict:
        """
        Populate all data types.

        Args:
            sample_mode: If True, only process sample_size tickers for testing
            sample_size: Number of tickers to process in sample mode

        Returns:
            Statistics dictionary
        """
        self.stats['start_time'] = datetime.utcnow()

        console.print("\n[bold blue]🚀 Starting Data Population[/bold blue]\n")

        # Step 1: Get universe of tickers
        tickers = self._get_tickers(limit=sample_size if sample_mode else None)

        if not tickers:
            console.print("[red]No tickers found in database. Run 'universe build' first.[/red]")
            return self.stats

        console.print(f"📊 Universe: {len(tickers)} tickers")

        # Step 2: Populate prices
        console.print("\n[cyan]Step 1: Fetching Prices (90 days)[/cyan]")
        self._populate_prices(tickers)

        # Step 3: Get survivors from fast screening
        # (We'll skip this for now and just use top N tickers to save time)
        # In production, this would run the screening pipeline
        survivors = tickers[:min(500, len(tickers))] if len(tickers) > 500 else tickers

        console.print(f"\n[cyan]Step 2: Fetching Fundamentals for {len(survivors)} tickers[/cyan]")
        self._populate_fundamentals(survivors)

        # Step 4: Compute factors
        console.print(f"\n[cyan]Step 3: Computing Factors[/cyan]")
        self._compute_factors(survivors)

        self.stats['end_time'] = datetime.utcnow()

        # Print summary
        self._print_summary()

        return self.stats

    def populate_from_survivors_csv(
        self,
        csv_path: str,
        stage_name: str = "Screening Stage"
    ) -> dict:
        """
        Populate fundamentals and factors for survivors from a screening CSV.

        This method enables survivors-driven data fetching, where we only
        fetch/update data for tickers that passed a screening stage.

        Args:
            csv_path: Path to screening stage CSV (e.g., snapshots/2025-11/stage_business_2025-11.csv)
            stage_name: Stage name for logging

        Returns:
            Statistics dictionary

        Example:
            >>> populator.populate_from_survivors_csv(
            ...     'snapshots/2025-11/stage_business_2025-11.csv',
            ...     stage_name='Stage 2.3 Business Filter'
            ... )
        """
        self.stats['start_time'] = datetime.utcnow()

        console.print(f"\n[bold blue]🚀 Populating Data for {stage_name} Survivors[/bold blue]\n")

        # Load survivors CSV
        try:
            survivors_df = pd.read_csv(csv_path)
            ticker_ids = survivors_df['ticker_id'].tolist()
            console.print(f"📊 Loaded {len(ticker_ids)} survivors from {csv_path}")
        except Exception as e:
            console.print(f"[red]Failed to load CSV: {e}[/red]")
            return self.stats

        # Get ticker details from database
        tickers = self._get_tickers_by_ids(ticker_ids)

        if not tickers:
            console.print("[red]No matching tickers found in database[/red]")
            return self.stats

        console.print(f"✅ Found {len(tickers)}/{len(ticker_ids)} tickers in database")

        # Populate fundamentals
        console.print(f"\n[cyan]Step 1: Fetching Fundamentals[/cyan]")
        self._populate_fundamentals(tickers)

        # Compute factors
        console.print(f"\n[cyan]Step 2: Computing Factors[/cyan]")
        self._compute_factors(tickers)

        self.stats['end_time'] = datetime.utcnow()

        # Print summary
        self._print_summary()

        return self.stats

    def _get_tickers(self, limit: int | None = None) -> list[dict]:
        """Get tickers from database"""
        with Session(self.engine) as session:
            query = text("""
                SELECT t.id, t.symbol, e.code as exchange_code
                FROM tickers t
                INNER JOIN exchanges e ON t.exchange_id = e.id
                WHERE t.active = 1
                ORDER BY t.id
            """)

            if limit:
                query = text(f"{query.text} LIMIT :limit")
                result = session.execute(query, {'limit': limit})
            else:
                result = session.execute(query)

            tickers = [
                {'id': row[0], 'symbol': row[1], 'exchange': row[2]}
                for row in result.fetchall()
            ]

            return tickers

    def _get_tickers_by_ids(self, ticker_ids: list[int]) -> list[dict]:
        """Get tickers by ID list"""
        if not ticker_ids:
            return []

        with Session(self.engine) as session:
            # Build placeholders for IN clause
            placeholders = ','.join([f":id{i}" for i in range(len(ticker_ids))])
            params = {f"id{i}": tid for i, tid in enumerate(ticker_ids)}

            query = text(f"""
                SELECT t.id, t.symbol, e.code as exchange_code
                FROM tickers t
                INNER JOIN exchanges e ON t.exchange_id = e.id
                WHERE t.id IN ({placeholders})
                ORDER BY t.id
            """)

            result = session.execute(query, params)

            tickers = [
                {'id': row[0], 'symbol': row[1], 'exchange': row[2]}
                for row in result.fetchall()
            ]

            return tickers

    def _populate_prices(self, tickers: list[dict]):
        """Fetch and insert prices for all tickers"""
        symbols = [t['symbol'] for t in tickers]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task("Fetching prices...", total=len(symbols))

            def progress_callback(current, total):
                progress.update(task, completed=current * len(symbols) // total)

            # Fetch prices in batches
            prices_data = self.adapter.fetch_prices_batch(
                symbols,
                period='90d',
                progress_callback=progress_callback,
            )

            progress.update(task, completed=len(symbols))

        # Insert into database
        inserted_count = self._insert_prices(tickers, prices_data)

        self.stats['prices_fetched'] = len(prices_data)
        self.stats['prices_inserted'] = inserted_count

        console.print(f"✅ Prices: {len(prices_data)} tickers fetched, {inserted_count} rows inserted")

    def _insert_prices(self, tickers: list[dict], prices_data: dict[str, pd.DataFrame]) -> int:
        """Insert prices into database"""
        ticker_map = {t['symbol']: t['id'] for t in tickers}
        inserted = 0

        with Session(self.engine) as session:
            for symbol, df in prices_data.items():
                if symbol not in ticker_map:
                    continue

                ticker_id = ticker_map[symbol]

                for date, row in df.iterrows():
                    try:
                        # Check if exists
                        existing = session.execute(
                            text("SELECT 1 FROM prices WHERE ticker_id = :tid AND date = :dt"),
                            {'tid': ticker_id, 'dt': date.date()}
                        ).first()

                        if existing:
                            continue

                        # Insert
                        price = Price(
                            ticker_id=ticker_id,
                            date=date.date(),
                            open_price=float(row['Open']) if pd.notna(row['Open']) else None,
                            high_price=float(row['High']) if pd.notna(row['High']) else None,
                            low_price=float(row['Low']) if pd.notna(row['Low']) else None,
                            close_price=float(row['Close']),
                            adj_close=float(row['Adj Close']) if 'Adj Close' in row else float(row['Close']),
                            volume=int(row['Volume']) if pd.notna(row['Volume']) else None,
                        )
                        session.add(price)
                        inserted += 1

                    except Exception as e:
                        logger.error(f"Failed to insert price for {symbol} on {date}: {e}")

            session.commit()

        return inserted

    def _populate_fundamentals(self, tickers: list[dict]):
        """Fetch and insert fundamentals for tickers"""
        success_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task("Fetching fundamentals...", total=len(tickers))

            for i, ticker in enumerate(tickers):
                symbol = ticker['symbol']

                try:
                    # Fetch fundamentals
                    data = self.adapter.fetch_fundamentals(symbol, years=5)

                    # Insert into database
                    if self._insert_fundamentals(ticker, data):
                        success_count += 1

                except Exception as e:
                    logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
                    self.stats['errors'].append(f"Fundamentals {symbol}: {e}")

                progress.update(task, completed=i + 1)

                # Polite delay
                if i < len(tickers) - 1:
                    time.sleep(0.1)

        self.stats['fundamentals_fetched'] = success_count

        console.print(f"✅ Fundamentals: {success_count}/{len(tickers)} tickers fetched")

    def _insert_fundamentals(self, ticker: dict, data: dict) -> bool:
        """Insert fundamentals for a single ticker with Alpha Vantage fallback"""
        if all(df.empty for df in data.values()):
            return False

        ticker_id = ticker['id']
        symbol = ticker['symbol']

        with Session(self.engine) as session:
            try:
                # Extract years from columns (dates)
                years = data['financials'].columns if not data['financials'].empty else []

                for period_end in years:
                    # Extract metrics first
                    financials = data['financials'][period_end] if not data['financials'].empty else pd.Series()
                    balance = data['balance_sheet'][period_end] if not data['balance_sheet'].empty else pd.Series()
                    cashflow = data['cashflow'][period_end] if not data['cashflow'].empty else pd.Series()

                    # Extract forensics fields from yfinance (Phase 3)
                    forensics_fields = {
                        'receivables': self._extract_field(balance, [
                            'Receivables', 'Accounts Receivable', 'Total Receivables Net'
                        ]),
                        'ppe': self._extract_field(balance, [
                            'Net PPE', 'Property Plant Equipment Net', 'Property Plant And Equipment Net'
                        ]),
                        'depreciation': self._extract_field(cashflow, [
                            'Depreciation And Amortization', 'Depreciation', 'Depreciation Amortization Depletion'
                        ]),
                        'sga_expense': self._extract_field(financials, [
                            'Selling General And Administrative', 'Operating Expense', 'Selling And Marketing Expense'
                        ]),
                        'cash': self._extract_field(balance, [
                            'Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments',
                            'Cash', 'Cash And Short Term Investments'
                        ]),
                        'short_term_debt': self._extract_field(balance, [
                            'Current Debt', 'Short Long Term Debt', 'Short Term Debt'
                        ]),
                        'retained_earnings': self._extract_field(balance, [
                            'Retained Earnings'
                        ])
                    }

                    # Phase 3.5: Try Alpha Vantage fallback for NULL fields
                    if self.av_adapter:
                        fields_with_source = self._fallback_to_alpha_vantage(
                            symbol, forensics_fields, period_end.year
                        )
                        # Track field coverage for statistics
                        self._update_field_coverage_stats(fields_with_source)
                        # Extract values only (discard source for DB insert)
                        forensics_values = {k: v[0] for k, v in fields_with_source.items()}
                    else:
                        # No AV adapter, use yfinance values as-is
                        forensics_values = forensics_fields

                    # Check if exists
                    existing = session.execute(
                        text("SELECT id FROM fundamentals WHERE ticker_id = :tid AND period_end = :pd"),
                        {'tid': ticker_id, 'pd': period_end.date()}
                    ).first()

                    if existing:
                        # Update existing record with forensics fields
                        session.execute(
                            text("""
                                UPDATE fundamentals
                                SET receivables = :receivables,
                                    ppe = :ppe,
                                    depreciation = :depreciation,
                                    sga_expense = :sga_expense,
                                    cash = :cash,
                                    short_term_debt = :short_term_debt,
                                    retained_earnings = :retained_earnings,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE ticker_id = :tid AND period_end = :pd
                            """),
                            {
                                'receivables': forensics_values['receivables'],
                                'ppe': forensics_values['ppe'],
                                'depreciation': forensics_values['depreciation'],
                                'sga_expense': forensics_values['sga_expense'],
                                'cash': forensics_values['cash'],
                                'short_term_debt': forensics_values['short_term_debt'],
                                'retained_earnings': forensics_values['retained_earnings'],
                                'tid': ticker_id,
                                'pd': period_end.date()
                            }
                        )
                        self.stats['fundamentals_inserted'] += 1
                    else:
                        # Insert new record
                        fundamental = Fundamental(
                            ticker_id=ticker_id,
                            period_end=period_end.date(),
                            report_type='A',
                            fiscal_year=period_end.year,
                            # Income statement
                            revenue=self._safe_float(financials.get('Total Revenue')),
                            gross_profit=self._safe_float(financials.get('Gross Profit')),
                            operating_income=self._safe_float(financials.get('Operating Income')),
                            net_income=self._safe_float(financials.get('Net Income')),
                            ebitda=self._safe_float(financials.get('EBITDA')),
                            # Balance sheet
                            total_assets=self._safe_float(balance.get('Total Assets')),
                            current_assets=self._safe_float(balance.get('Current Assets')),
                            total_liabilities=self._safe_float(balance.get('Total Liabilities Net Minority Interest')),
                            current_liabilities=self._safe_float(balance.get('Current Liabilities')),
                            shareholders_equity=self._safe_float(balance.get('Stockholders Equity')),
                            # Cash flow
                            operating_cash_flow=self._safe_float(cashflow.get('Operating Cash Flow')),
                            free_cash_flow=self._safe_float(cashflow.get('Free Cash Flow')),
                            # Forensics fields (Phase 3.5 with AV fallback)
                            receivables=forensics_values['receivables'],
                            ppe=forensics_values['ppe'],
                            depreciation=forensics_values['depreciation'],
                            sga_expense=forensics_values['sga_expense'],
                            cash=forensics_values['cash'],
                            short_term_debt=forensics_values['short_term_debt'],
                            retained_earnings=forensics_values['retained_earnings'],
                        )

                        session.add(fundamental)
                        self.stats['fundamentals_inserted'] += 1

                session.commit()
                return True

            except Exception as e:
                logger.error(f"Failed to insert fundamentals for {ticker['symbol']}: {e}")
                session.rollback()
                return False

    def _compute_factors(self, tickers: list[dict]):
        """Compute and insert/update factors from fundamentals"""
        success_count = 0

        with Session(self.engine) as session:
            for ticker in tickers:
                try:
                    factors = self._calculate_factors(session, ticker['id'])
                    if factors:
                        # Check if factors exist for this ticker and as_of_date
                        existing = session.execute(
                            text("SELECT id FROM factors WHERE ticker_id = :tid AND as_of_date = :date"),
                            {'tid': factors.ticker_id, 'date': factors.as_of_date}
                        ).first()

                        if existing:
                            # Update existing record
                            session.execute(
                                text("""
                                    UPDATE factors
                                    SET roce = :roce,
                                        revenue_growth_5y = :rev_growth,
                                        gross_margin = :gm,
                                        debt_to_equity = :dte,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE ticker_id = :tid AND as_of_date = :date
                                """),
                                {
                                    'roce': factors.roce,
                                    'rev_growth': factors.revenue_growth_5y,
                                    'gm': factors.gross_margin,
                                    'dte': factors.debt_to_equity,
                                    'tid': factors.ticker_id,
                                    'date': factors.as_of_date
                                }
                            )
                        else:
                            session.add(factors)

                        success_count += 1
                except Exception as e:
                    logger.error(f"Failed to compute factors for {ticker['symbol']}: {e}")

            session.commit()

        self.stats['factors_computed'] = success_count
        console.print(f"✅ Factors: {success_count} tickers computed")

    def _calculate_factors(self, session: Session, ticker_id: int) -> Factor | None:
        """Calculate factor metrics from fundamentals"""
        # Fetch fundamentals
        result = session.execute(
            text("""
                SELECT period_end, revenue, gross_profit, net_income,
                       total_assets, current_liabilities, total_liabilities,
                       shareholders_equity, free_cash_flow
                FROM fundamentals
                WHERE ticker_id = :tid
                ORDER BY period_end DESC
                LIMIT 5
            """),
            {'tid': ticker_id}
        )

        rows = result.fetchall()
        if not rows or len(rows) < 3:
            return None

        # Convert to DataFrame for easier calculations
        df = pd.DataFrame(rows, columns=[
            'period_end', 'revenue', 'gross_profit', 'net_income',
            'total_assets', 'current_liabilities', 'total_liabilities',
            'shareholders_equity', 'free_cash_flow'
        ])

        try:
            # ROCE
            latest = df.iloc[0]
            capital_employed = latest['total_assets'] - latest['current_liabilities']
            roce = (latest['net_income'] / capital_employed * 100) if capital_employed > 0 else None

            # Revenue CAGR (5-year)
            if len(df) >= 5 and df['revenue'].iloc[-1] > 0:
                revenue_cagr = ((df['revenue'].iloc[0] / df['revenue'].iloc[-1]) ** (1/len(df)) - 1) * 100
            else:
                revenue_cagr = None

            # Gross margin (average)
            df['gross_margin'] = (df['gross_profit'] / df['revenue']) * 100
            gross_margin = df['gross_margin'].mean()

            # Debt to equity
            debt_to_equity = (latest['total_liabilities'] / latest['shareholders_equity']) if latest['shareholders_equity'] > 0 else None

            # Create Factor record
            # Convert period_end to date if it's a string
            period_end = latest['period_end']
            if isinstance(period_end, str):
                period_end = datetime.fromisoformat(period_end).date()

            return Factor(
                ticker_id=ticker_id,
                as_of_date=period_end,
                roce=roce,
                revenue_growth_5y=revenue_cagr,
                gross_margin=gross_margin,
                debt_to_equity=debt_to_equity,
            )

        except Exception as e:
            logger.error(f"Factor calculation failed for ticker {ticker_id}: {e}")
            return None

    def _fallback_to_alpha_vantage(
        self,
        symbol: str,
        forensics_fields: dict[str, float | None],
        fiscal_year: int
    ) -> dict[str, tuple[float | None, str]]:
        """
        Try Alpha Vantage fallback for NULL forensics fields.

        Args:
            symbol: Stock ticker symbol
            forensics_fields: Dict of field_name -> value from yfinance
            fiscal_year: Fiscal year to extract

        Returns:
            Dict of field_name -> (value, source) where source is 'yfinance', 'alpha_vantage', or 'missing'
        """
        # Convert to provenance-tracked format
        fields_with_source = {
            field: (value, 'yfinance' if value is not None else 'missing')
            for field, value in forensics_fields.items()
        }

        # Identify which fields need fallback
        null_fields = [field for field, (value, _) in fields_with_source.items() if value is None]

        if not null_fields:
            return fields_with_source  # All fields populated by yfinance

        try:
            # Fetch fundamentals from AV (cached with 90d TTL)
            av_data = self.av_adapter.fetch_fundamentals(symbol, years=5)

            # Extract each NULL field
            for field_name in null_fields:
                field_values = self.av_adapter.extract_field(av_data, field_name, fiscal_year)

                if field_values and fiscal_year in field_values:
                    fields_with_source[field_name] = (field_values[fiscal_year], 'alpha_vantage')
                    logger.debug(f"✓ AV filled {field_name} for {symbol} FY{fiscal_year}")

        except Exception as e:
            logger.warning(f"AV fallback failed for {symbol}: {e}")
            self.av_adapter.stats['errors'] += 1

        return fields_with_source

    def _update_field_coverage_stats(self, fields_with_source: dict[str, tuple[float | None, str]]):
        """
        Update field coverage statistics with source tracking.

        Args:
            fields_with_source: Dict of field_name -> (value, source)
        """
        for field_name, (value, source) in fields_with_source.items():
            if source in ['yfinance', 'alpha_vantage', 'missing']:
                self.stats['field_coverage'][field_name][source] += 1

    def _safe_float(self, value) -> float | None:
        """Safely convert value to float"""
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _extract_field(self, df: pd.Series, keys: list[str]) -> float | None:
        """
        Extract field from pandas Series trying multiple possible key names.

        Args:
            df: Pandas Series (row from DataFrame)
            keys: List of possible key names in priority order

        Returns:
            Float value or None if not found
        """
        for key in keys:
            if key in df.index:
                value = df.get(key)
                if value is not None and pd.notna(value):
                    return self._safe_float(value)
        return None

    def _print_summary(self):
        """Print population summary with field coverage statistics"""
        runtime = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        table = Table(title="Data Population Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Runtime", f"{runtime:.1f}s")
        table.add_row("Prices Fetched", f"{self.stats['prices_fetched']} tickers")
        table.add_row("Prices Inserted", f"{self.stats['prices_inserted']} rows")
        table.add_row("Fundamentals Fetched", f"{self.stats['fundamentals_fetched']} tickers")
        table.add_row("Fundamentals Inserted", f"{self.stats['fundamentals_inserted']} rows")
        table.add_row("Factors Computed", f"{self.stats['factors_computed']} tickers")
        table.add_row("Errors", f"{len(self.stats['errors'])}")

        console.print("\n")
        console.print(table)

        # Phase 3.5: Print field coverage statistics if AV adapter was used
        if self.av_adapter:
            console.print("\n[bold cyan]📊 Forensics Field Coverage (Phase 3.5)[/bold cyan]")

            coverage_table = Table()
            coverage_table.add_column("Field", style="cyan")
            coverage_table.add_column("yfinance", style="green")
            coverage_table.add_column("Alpha Vantage", style="yellow")
            coverage_table.add_column("Missing", style="red")
            coverage_table.add_column("Coverage %", style="magenta")

            for field_name, counts in self.stats['field_coverage'].items():
                total = counts['yfinance'] + counts['alpha_vantage'] + counts['missing']
                if total > 0:
                    coverage_pct = ((counts['yfinance'] + counts['alpha_vantage']) / total) * 100
                else:
                    coverage_pct = 0.0

                coverage_table.add_row(
                    field_name,
                    str(counts['yfinance']),
                    str(counts['alpha_vantage']),
                    str(counts['missing']),
                    f"{coverage_pct:.1f}%"
                )

            console.print(coverage_table)

            # Print AV adapter statistics
            if hasattr(self.av_adapter, 'stats'):
                console.print("\n[bold cyan]🔄 Alpha Vantage API Statistics[/bold cyan]")
                av_stats_table = Table()
                av_stats_table.add_column("Metric", style="cyan")
                av_stats_table.add_column("Count", style="green")

                av_stats_table.add_row("API Calls", str(self.av_adapter.stats['api_calls']))
                av_stats_table.add_row("Cache Hits", str(self.av_adapter.stats['cache_hits']))
                av_stats_table.add_row("Rate Limit Sleeps", str(self.av_adapter.stats['rate_limit_sleeps']))
                av_stats_table.add_row("Errors", str(self.av_adapter.stats['errors']))

                console.print(av_stats_table)

        if self.stats['errors']:
            console.print(f"\n[yellow]⚠️  {len(self.stats['errors'])} errors occurred (see logs)[/yellow]")
