"""Stage 2.5: Research & Valuation - DCF modeling and report generation"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.orm import Session

from multibagger.common.sql_utils import build_in_clause_params
from multibagger.config import Config
from multibagger.database.models import Research
from multibagger.database.schema import get_engine
from multibagger.data.cache import HttpCache
from multibagger.data.promotion import batch_promote_finalists
from multibagger.research.business import extract_business_profile
from multibagger.research.edgar import EDGARFetcher
from multibagger.research.valuation import compute_dcf_valuation, compute_comparables
from multibagger.research.report import generate_report, generate_pdf

from .common import ScreenResult, save_stage_output

logger = logging.getLogger(__name__)
console = Console()


def screen_research(
    config: Config,
    as_of: str | None = None,
    output_dir: str = "snapshots"
) -> ScreenResult:
    """
    Stage 2.5: Research & Valuation screening.
    
    Generates detailed research reports with DCF valuation for survivors.
    
    Args:
        config: Configuration object
        as_of: YYYY-MM format date (defaults to current month)
        output_dir: Output directory for reports and CSV
        
    Returns:
        ScreenResult with research statistics
    """
    start_time = time.time()
    
    # Default as_of to current month
    if as_of is None:
        as_of = datetime.utcnow().strftime("%Y-%m")
    
    logger.info(f"Starting Research & Valuation for {as_of}")
    console.print(f"\n[bold blue]🔬 Stage 2.5: Research & Valuation ({as_of})[/bold blue]\n")
    
    # Load Stage 2.4 survivors (redflags output)
    redflags_output = Path(output_dir) / as_of / f"stage_redflags_{as_of}.csv"
    
    if not redflags_output.exists():
        logger.error(f"Redflags output not found: {redflags_output}")
        console.print(f"[red]❌ Input CSV not found: {redflags_output}[/red]")
        console.print(f"[yellow]Run 'screen redflags --as-of {as_of}' first[/yellow]")
        
        return ScreenResult(
            survivors=pd.DataFrame(),
            eliminated_by_rule={},
            input_count=0,
            survivor_count=0,
            runtime_seconds=time.time() - start_time
        )
    
    survivors_df = pd.read_csv(redflags_output)
    ticker_ids = survivors_df['ticker_id'].tolist()
    
    # Get config
    research_config = config.get('research', {}) if hasattr(config, 'get') else {}
    max_reports = research_config.get('limits', {}).get('max_reports', 15)
    
    # Limit to max_reports
    if len(ticker_ids) > max_reports:
        console.print(f"[yellow]⚠️  Limiting to {max_reports} reports (config: research.limits.max_reports)[/yellow]")
        ticker_ids = ticker_ids[:max_reports]
        survivors_df = survivors_df.iloc[:max_reports]

    logger.info(f"Processing {len(ticker_ids)} survivors for research")
    console.print(f"📊 Processing {len(ticker_ids)} survivors\n")

    # Promotion hook: Promote finalists from staging to canonical (Phase A)
    storage_config = config.get('storage', {}) if hasattr(config, 'get') else {}
    persist_finalists_only = storage_config.get('persist_finalists_only', False)

    if persist_finalists_only and ticker_ids:
        console.print("[yellow]📊 Promoting finalists from staging to canonical...[/yellow]")
        logger.info(f"Promoting {len(ticker_ids)} finalists (storage policy: finalists-only)")

        engine = get_engine()
        as_of_date = datetime.strptime(f"{as_of}-01", "%Y-%m-%d").date()

        try:
            with Session(engine) as session:
                promotion_results = batch_promote_finalists(
                    session=session,
                    ticker_ids=ticker_ids,
                    as_of_date=as_of_date,
                    commit=True
                )

                # Log promotion results
                total_fundamentals = sum(r.fundamentals_rows for r in promotion_results)
                total_factors = sum(r.factors_rows for r in promotion_results)

                logger.info(
                    f"✓ Promoted {len(promotion_results)} finalists: "
                    f"{total_fundamentals} fundamentals, {total_factors} factors"
                )
                console.print(
                    f"[green]✓ Promoted {len(promotion_results)} finalists "
                    f"({total_fundamentals} fundamentals, {total_factors} factors)[/green]\n"
                )
        except Exception as e:
            logger.error(f"Promotion failed: {e}")
            console.print(f"[red]⚠️  Promotion failed: {e}[/red]\n")
    
    # Initialize EDGAR fetcher
    edgar_enabled = research_config.get('filings', {}).get('us_edgar_enabled', True)
    edgar_fetcher = None
    if edgar_enabled:
        cache = HttpCache()
        edgar_fetcher = EDGARFetcher(
            cache=cache,
            request_delay_ms=research_config.get('filings', {}).get('request_delay_ms', 200),
            cache_ttl_days=research_config.get('filings', {}).get('cache_ttl_days', 90)
        )
    
    # Batch fetch metadata
    metadata = _fetch_batch_metadata(ticker_ids)
    
    # Process each survivor
    results = []
    reports_generated = 0
    errors = []
    
    for idx, row in survivors_df.iterrows():
        ticker_id = row['ticker_id']
        symbol = row['symbol']
        
        try:
            console.print(f"[cyan]Processing {symbol} ({idx+1}/{len(survivors_df)})...[/cyan]")
            
            # Get ticker metadata
            ticker_meta = metadata.get(ticker_id, {})
            if not ticker_meta:
                logger.warning(f"No metadata found for ticker_id {ticker_id}")
                continue
            
            # Extract business profile
            business_profile = extract_business_profile(
                ticker_id=ticker_id,
                ticker_symbol=symbol,
                as_of=as_of,
                edgar_fetcher=edgar_fetcher
            )
            
            # Compute DCF valuation
            current_price = float(row.get('last_close', 0))
            config_dict = config._config if hasattr(config, '_config') else (config if isinstance(config, dict) else {})
            
            valuation_result = compute_dcf_valuation(
                ticker_id=ticker_id,
                current_price=current_price,
                as_of=as_of,
                config=config_dict
            )
            
            # Compute comparables
            sector_id = ticker_meta.get('sector_id')
            comparables = compute_comparables(
                ticker_id=ticker_id,
                sector_id=sector_id,
                config=config_dict
            )
            
            # Build report context
            context = _build_report_context(
                ticker_meta=ticker_meta,
                business_profile=business_profile,
                valuation_result=valuation_result,
                comparables=comparables,
                survivor_row=row,
                as_of=as_of
            )
            
            # Generate report
            report_dir = Path(output_dir) / as_of / "reports"
            md_path = report_dir / f"{symbol}.md"
            
            generate_report(context, md_path, config_dict)
            reports_generated += 1
            
            # Optional PDF
            pdf_path = None
            if research_config.get('outputs', {}).get('pdf', False):
                pdf_path = report_dir / f"{symbol}.pdf"
                generate_pdf(md_path, pdf_path, config_dict)
            
            # UPSERT to database
            _upsert_research_row(
                ticker_id=ticker_id,
                as_of=as_of,
                business_profile=business_profile,
                valuation_result=valuation_result,
                comparables=comparables,
                md_path=str(md_path),
                pdf_path=str(pdf_path) if pdf_path else None
            )
            
            # Collect for summary CSV
            results.append({
                'ticker_id': ticker_id,
                'symbol': symbol,
                'name': ticker_meta.get('name', 'Unknown'),
                'exchange': ticker_meta.get('exchange_code', 'Unknown'),
                'sector': ticker_meta.get('sector', 'Unknown'),
                'current_price': current_price,
                'base_fair_value': valuation_result.get('base_fair_value'),
                'upside_pct': valuation_result.get('upside_pct'),
                'moat': business_profile.get('moat'),
                'composite_risk_score': row.get('composite_score'),
                'valuation_status': valuation_result.get('status'),
                'report_path': str(md_path)
            })
            
        except Exception as e:
            logger.error(f"Failed to process {symbol}: {e}")
            errors.append(f"{symbol}: {e}")
            console.print(f"[red]❌ Error processing {symbol}: {e}[/red]")
    
    # Generate summary CSV
    results_df = pd.DataFrame(results)
    if not results_df.empty:
        # Sort by upside DESC
        results_df = results_df.sort_values('upside_pct', ascending=False, na_position='last')
    
    output_csv = Path(output_dir) / as_of / f"stage_research_{as_of}.csv"
    save_stage_output(results_df, output_csv, "Research")
    
    # Print summary
    runtime = time.time() - start_time
    _print_summary(results_df, reports_generated, errors, runtime)
    
    # Generate metrics JSON
    _generate_metrics_json(output_dir, as_of, results_df, reports_generated, runtime, edgar_fetcher)
    
    return ScreenResult(
        survivors=results_df,
        eliminated_by_rule={},
        input_count=len(survivors_df),
        survivor_count=len(results_df),
        runtime_seconds=runtime
    )


def _fetch_batch_metadata(ticker_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Fetch ticker metadata in batch"""
    if not ticker_ids:
        return {}
    
    engine = get_engine()
    with Session(engine) as session:
        placeholders, params = build_in_clause_params(ticker_ids, param_prefix='ticker')
        
        query = text(f"""
            SELECT 
                t.id, t.symbol, t.name, t.market_cap, t.sector_id,
                e.code as exchange_code,
                s.name as sector
            FROM tickers t
            LEFT JOIN exchanges e ON t.exchange_id = e.id
            LEFT JOIN sectors s ON t.sector_id = s.id
            WHERE t.id IN ({placeholders})
        """)
        
        result = session.execute(query, params).fetchall()
        
        metadata = {}
        for row in result:
            metadata[row.id] = {
                'ticker_id': row.id,
                'symbol': row.symbol,
                'name': row.name,
                'market_cap': float(row.market_cap) if row.market_cap else 0,
                'sector_id': row.sector_id,
                'exchange_code': row.exchange_code,
                'sector': row.sector
            }
        
        return metadata


def _build_report_context(
    ticker_meta: Dict[str, Any],
    business_profile: Dict[str, Any],
    valuation_result: Dict[str, Any],
    comparables: Dict[str, Any],
    survivor_row: pd.Series,
    as_of: str
) -> Dict[str, Any]:
    """Build context dict for report template"""
    
    # Parse valuation JSON
    valuation_json = json.loads(valuation_result.get('valuation_json', '{}'))
    assumptions_json = json.loads(valuation_result.get('assumptions_json', '{}'))
    
    context = {
        'as_of': as_of,
        'company': {
            'ticker_id': ticker_meta['ticker_id'],
            'symbol': ticker_meta['symbol'],
            'name': ticker_meta['name'],
            'sector': ticker_meta.get('sector', 'Unknown'),
            'exchange': ticker_meta.get('exchange_code', 'Unknown')
        },
        'valuation': {
            'status': valuation_result.get('status', 'unknown'),
            'current_price': float(survivor_row.get('last_close', 0)),
            'base_fair_value': valuation_result.get('base_fair_value'),
            'bear_fair_value': valuation_result.get('bear_fair_value'),
            'bull_fair_value': valuation_result.get('bull_fair_value'),
            'upside_pct': valuation_result.get('upside_pct'),
            'historical_cagr': valuation_json.get('historical_cagr', 0),
            'avg_margin': valuation_json.get('avg_margin', 0),
            'positive_fcf_years': valuation_json.get('positive_fcf_years', 0)
        },
        'quality': {
            'roce': float(survivor_row.get('roce', 0)),
            'gross_margin': float(survivor_row.get('gross_margin', 0)),
            'positive_fcf_years': int(survivor_row.get('positive_fcf_years', 0)),
            'debt_to_equity': float(survivor_row.get('debt_to_equity', 0)),
            'fcf_yield': float(survivor_row.get('fcf_yield', 0)) if 'fcf_yield' in survivor_row else 0
        },
        'business': business_profile,
        'risk_flags': {
            'composite_score': float(survivor_row.get('composite_score', 0)),
            'first_fail_reason': survivor_row.get('first_fail_reason', 'none'),
            'beneish_m_score': float(survivor_row.get('beneish_m_score', 0)),
            'altman_z_score': float(survivor_row.get('altman_z_score', 0)),
            'accruals_ratio': float(survivor_row.get('accruals_ratio', 0))
        },
        'assumptions': assumptions_json,
        'comparables': comparables,
        'sources': business_profile.get('sources', []) + [
            {'type': 'fundamentals', 'fiscal_years': assumptions_json.get('fiscal_years_used', [])}
        ]
    }
    
    return context


def _upsert_research_row(
    ticker_id: int,
    as_of: str,
    business_profile: Dict[str, Any],
    valuation_result: Dict[str, Any],
    comparables: Dict[str, Any],
    md_path: str,
    pdf_path: Optional[str]
):
    """UPSERT research row to database"""
    engine = get_engine()
    with Session(engine) as session:
        # Convert as_of to date
        as_of_date = datetime.strptime(as_of, "%Y-%m").date()
        
        # Check if exists
        existing = session.execute(
            text("SELECT id FROM research WHERE ticker_id = :tid AND as_of_date = :date"),
            {'tid': ticker_id, 'date': as_of_date}
        ).first()
        
        if existing:
            # Update
            session.execute(
                text("""
                    UPDATE research
                    SET thesis = :thesis,
                        moat = :moat,
                        business_model = :business_model,
                        growth_drivers = :growth_drivers,
                        top_risks = :top_risks,
                        base_fair_value = :base_fv,
                        bear_fair_value = :bear_fv,
                        bull_fair_value = :bull_fv,
                        upside_pct = :upside,
                        valuation_json = :val_json,
                        comps_json = :comps_json,
                        assumptions_json = :assumptions_json,
                        sources_json = :sources_json,
                        report_md_path = :md_path,
                        report_pdf_path = :pdf_path,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ticker_id = :tid AND as_of_date = :date
                """),
                {
                    'thesis': _generate_thesis(valuation_result),
                    'moat': business_profile.get('moat'),
                    'business_model': business_profile.get('business_model'),
                    'growth_drivers': business_profile.get('growth_drivers'),
                    'top_risks': business_profile.get('top_risks'),
                    'base_fv': valuation_result.get('base_fair_value'),
                    'bear_fv': valuation_result.get('bear_fair_value'),
                    'bull_fv': valuation_result.get('bull_fair_value'),
                    'upside': valuation_result.get('upside_pct'),
                    'val_json': valuation_result.get('valuation_json'),
                    'comps_json': comparables.get('comps_json', '{}'),
                    'assumptions_json': valuation_result.get('assumptions_json'),
                    'sources_json': json.dumps(business_profile.get('sources', [])),
                    'md_path': md_path,
                    'pdf_path': pdf_path,
                    'tid': ticker_id,
                    'date': as_of_date
                }
            )
        else:
            # Insert
            research = Research(
                ticker_id=ticker_id,
                as_of_date=as_of_date,
                thesis=_generate_thesis(valuation_result),
                moat=business_profile.get('moat'),
                business_model=business_profile.get('business_model'),
                growth_drivers=business_profile.get('growth_drivers'),
                top_risks=business_profile.get('top_risks'),
                base_fair_value=valuation_result.get('base_fair_value'),
                bear_fair_value=valuation_result.get('bear_fair_value'),
                bull_fair_value=valuation_result.get('bull_fair_value'),
                upside_pct=valuation_result.get('upside_pct'),
                valuation_json=valuation_result.get('valuation_json'),
                comps_json=comparables.get('comps_json', '{}'),
                assumptions_json=valuation_result.get('assumptions_json'),
                sources_json=json.dumps(business_profile.get('sources', [])),
                report_md_path=md_path,
                report_pdf_path=pdf_path
            )
            session.add(research)
        
        session.commit()


def _generate_thesis(valuation_result: Dict[str, Any]) -> str:
    """Generate brief thesis statement"""
    status = valuation_result.get('status')
    if status != 'success':
        return f"Valuation unavailable ({status})"
    
    upside = valuation_result.get('upside_pct', 0)
    if upside > 30:
        return f"Appears undervalued with {upside:.1f}% upside potential"
    elif upside > 10:
        return f"Moderate upside opportunity ({upside:.1f}%)"
    elif upside > 0:
        return f"Fairly valued with limited upside ({upside:.1f}%)"
    else:
        return f"Currently overvalued ({upside:.1f}% downside)"


def _print_summary(results_df: pd.DataFrame, reports_generated: int, errors: List[str], runtime: float):
    """Print research summary to console"""
    console.print("\n[bold cyan]📊 Research Summary[/bold cyan]\n")
    
    table = Table(title="Research Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Input Survivors", str(len(results_df)))
    table.add_row("Reports Generated", str(reports_generated))
    table.add_row("Errors", str(len(errors)))
    table.add_row("Runtime", f"{runtime:.1f}s")
    
    if not results_df.empty:
        successful_valuations = results_df[results_df['valuation_status'] == 'success'].shape[0]
        table.add_row("Successful Valuations", f"{successful_valuations}/{len(results_df)}")
        
        if successful_valuations > 0:
            avg_upside = results_df[results_df['valuation_status'] == 'success']['upside_pct'].mean()
            table.add_row("Avg Upside", f"{avg_upside:.1f}%")
    
    console.print(table)
    
    # Top opportunities
    if not results_df.empty and 'upside_pct' in results_df.columns:
        top_df = results_df[results_df['valuation_status'] == 'success'].head(10)
        if not top_df.empty:
            console.print("\n[bold cyan]🎯 Top Opportunities (by Upside)[/bold cyan]\n")
            
            top_table = Table()
            top_table.add_column("Rank", style="cyan")
            top_table.add_column("Symbol", style="yellow")
            top_table.add_column("Upside", style="green")
            top_table.add_column("Moat", style="magenta")
            
            for idx, row in enumerate(top_df.itertuples(), 1):
                top_table.add_row(
                    str(idx),
                    row.symbol,
                    f"{row.upside_pct:.1f}%",
                    row.moat
                )
            
            console.print(top_table)


def _generate_metrics_json(output_dir: str, as_of: str, results_df: pd.DataFrame, 
                           reports_generated: int, runtime: float, edgar_fetcher):
    """Generate research_metrics.json"""
    metrics = {
        'as_of': as_of,
        'timestamp': datetime.utcnow().isoformat(),
        'input_count': len(results_df),
        'reports_generated': reports_generated,
        'runtime_seconds': round(runtime, 2),
        'avg_time_per_report': round(runtime / reports_generated, 2) if reports_generated > 0 else 0
    }
    
    if not results_df.empty:
        successful = results_df[results_df['valuation_status'] == 'success']
        metrics['valuation_coverage_pct'] = round(len(successful) / len(results_df) * 100, 1)
        
        if len(successful) > 0:
            metrics['avg_upside_pct'] = round(successful['upside_pct'].mean(), 1)
            metrics['median_upside_pct'] = round(successful['upside_pct'].median(), 1)
    
    if edgar_fetcher:
        metrics['edgar_stats'] = edgar_fetcher.get_stats()
    
    metrics_path = Path(output_dir) / as_of / "research_metrics.json"
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    logger.info(f"Metrics saved to {metrics_path}")
