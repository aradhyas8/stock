"""Data population orchestration for populating DB with real market data"""

import logging
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

from .adapters.yfinance_adapter import YFinanceAdapter

logger = logging.getLogger(__name__)
console = Console()


class DataPopulator:
    """Orchestrates data population from APIs to database"""

    def __init__(self, config: Config):
        self.config = config
        self.engine = get_engine()
        self.adapter = YFinanceAdapter(batch_size=50, delay_seconds=1.0)

        self.stats = {
            'prices_fetched': 0,
            'prices_inserted': 0,
            'fundamentals_fetched': 0,
            'fundamentals_inserted': 0,
            'factors_computed': 0,
            'errors': [],
            'start_time': None,
            'end_time': None,
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
        """Insert fundamentals for a single ticker"""
        if all(df.empty for df in data.values()):
            return False

        ticker_id = ticker['id']

        with Session(self.engine) as session:
            try:
                # Extract years from columns (dates)
                years = data['financials'].columns if not data['financials'].empty else []

                for period_end in years:
                    # Check if exists
                    existing = session.execute(
                        text("SELECT 1 FROM fundamentals WHERE ticker_id = :tid AND period_end = :pd"),
                        {'tid': ticker_id, 'pd': period_end.date()}
                    ).first()

                    if existing:
                        continue

                    # Extract metrics
                    financials = data['financials'][period_end] if not data['financials'].empty else pd.Series()
                    balance = data['balance_sheet'][period_end] if not data['balance_sheet'].empty else pd.Series()
                    cashflow = data['cashflow'][period_end] if not data['cashflow'].empty else pd.Series()

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
        """Compute and insert factors from fundamentals"""
        success_count = 0

        with Session(self.engine) as session:
            for ticker in tickers:
                try:
                    factors = self._calculate_factors(session, ticker['id'])
                    if factors:
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
            return Factor(
                ticker_id=ticker_id,
                as_of_date=latest['period_end'],
                roce=roce,
                revenue_growth_5y=revenue_cagr,
                gross_margin=gross_margin,
                debt_to_equity=debt_to_equity,
            )

        except Exception as e:
            logger.error(f"Factor calculation failed for ticker {ticker_id}: {e}")
            return None

    def _safe_float(self, value) -> float | None:
        """Safely convert value to float"""
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _print_summary(self):
        """Print population summary"""
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

        if self.stats['errors']:
            console.print(f"\n[yellow]⚠️  {len(self.stats['errors'])} errors occurred (see logs)[/yellow]")
