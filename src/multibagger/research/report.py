"""Research report generator - Markdown rendering with Jinja2"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from jinja2 import Template

logger = logging.getLogger(__name__)

# Simple Markdown template (embedded for MVP, would move to templates/ in production)
REPORT_TEMPLATE = """
# Investment Research Report: {{ company.symbol }}

**Company:** {{ company.name }}  
**Sector:** {{ company.sector }} | **Exchange:** {{ company.exchange }}  
**Report Date:** {{ report_date }}  
**As of:** {{ as_of }}

---

## Executive Summary

{% if valuation.status == 'success' %}
**Fair Value Range:** ${{ "%.2f"|format(valuation.bear_fair_value) }} - ${{ "%.2f"|format(valuation.bull_fair_value) }}  
**Base Case Fair Value:** ${{ "%.2f"|format(valuation.base_fair_value) }}  
**Current Price:** ${{ "%.2f"|format(valuation.current_price) }}  
**Upside Potential:** {{ "%.1f"|format(valuation.upside_pct) }}%

{% if valuation.upside_pct > 30 %}
**Thesis:** {{ company.symbol }} appears **undervalued** based on DCF analysis with {{ "%.1f"|format(valuation.upside_pct) }}% upside to base case. 
{% elif valuation.upside_pct > 10 %}
**Thesis:** {{ company.symbol }} shows **moderate upside** with {{ "%.1f"|format(valuation.upside_pct) }}% potential return.
{% else %}
**Thesis:** {{ company.symbol }} is **fairly valued** with limited upside ({{ "%.1f"|format(valuation.upside_pct) }}%).
{% endif %}

{% else %}
**Status:** Valuation unavailable ({{ valuation.status }})
{% endif %}

---

## Business Model & Competitive Moat

**Business Model:** {{ business.business_model }}

**Competitive Moat:** {{ business.moat }}
{% if business.moat == 'network_effects' %}
- Benefits from network effects where value increases with user base
{% elif business.moat == 'switching_costs' %}
- High switching costs create customer lock-in
{% elif business.moat == 'scale' %}
- Scale advantages in production, distribution, or operations
{% elif business.moat == 'ip_brand' %}
- Protected by intellectual property, patents, or strong brand
{% elif business.moat == 'cost_advantage' %}
- Structural cost advantages vs competitors
{% else %}
- Moat characteristics require further analysis
{% endif %}

**Growth Drivers:** {{ business.growth_drivers }}

---

## Financial Quality Snapshot

{% if quality %}
| Metric | Value | Interpretation |
|--------|-------|----------------|
| ROCE | {{ "%.1f"|format(quality.roce) }}% | {% if quality.roce > 20 %}Excellent{% elif quality.roce > 15 %}Good{% else %}Adequate{% endif %} |
| Gross Margin | {{ "%.1f"|format(quality.gross_margin) }}% | {% if quality.gross_margin > 40 %}High{% elif quality.gross_margin > 20 %}Moderate{% else %}Low{% endif %} |
| Positive FCF Years | {{ quality.positive_fcf_years }}/5 | {% if quality.positive_fcf_years >= 4 %}Consistent{% elif quality.positive_fcf_years >= 3 %}Moderate{% else %}Inconsistent{% endif %} |
| Debt-to-Equity | {{ "%.2f"|format(quality.debt_to_equity) }}x | {% if quality.debt_to_equity < 0.5 %}Conservative{% elif quality.debt_to_equity < 1.0 %}Moderate{% else %}Elevated{% endif %} |

{% else %}
*Financial quality metrics unavailable*
{% endif %}

---

## Valuation Analysis

{% if valuation.status == 'success' %}

### DCF Scenario Analysis

| Scenario | Fair Value | Upside/(Downside) |
|----------|-----------|-------------------|
| Bear Case | ${{ "%.2f"|format(valuation.bear_fair_value) }} | {{ "%.1f"|format((valuation.bear_fair_value - valuation.current_price) / valuation.current_price * 100) }}% |
| **Base Case** | **${{ "%.2f"|format(valuation.base_fair_value) }}** | **{{ "%.1f"|format(valuation.upside_pct) }}%** |
| Bull Case | ${{ "%.2f"|format(valuation.bull_fair_value) }} | {{ "%.1f"|format((valuation.bull_fair_value - valuation.current_price) / valuation.current_price * 100) }}% |

### Key Assumptions

- **Discount Rate:** {{ "%.1f"|format(assumptions.discount_rate * 100) }}%
- **Terminal Growth:** {{ "%.1f"|format(assumptions.terminal_g * 100) }}%
- **Projection Period:** {{ assumptions.projection_years }} years
- **Historical Revenue CAGR:** {{ "%.1f"|format(valuation.historical_cagr * 100) }}%
- **Operating Margin:** {{ "%.1f"|format(valuation.avg_margin * 100) }}%

{% if comparables and comparables.peers %}
### Peer Comparables

**Peer Set ({{ comparables.peers|length }}):** {{ comparables.peers|join(", ") }}

*Note: Full peer multiples analysis available in production version*
{% endif %}

{% else %}
**Valuation Status:** {{ valuation.status }}

{% if valuation.status == 'insufficient_data' %}
Insufficient historical fundamentals for DCF analysis (requires minimum 3 years).
{% elif valuation.status == 'insufficient_fcf' %}
Insufficient positive FCF history (requires 3+ years of positive FCF).
{% endif %}
{% endif %}

---

## Risk Assessment

{% if risk_flags %}
### Forensic Accounting Red Flags

**Composite Risk Score:** {{ "%.1f"|format(risk_flags.composite_score) }}/100 
{% if risk_flags.composite_score > 40 %}⚠️ High Risk{% elif risk_flags.composite_score > 25 %}⚠️ Moderate Risk{% else %}✓ Low Risk{% endif %}

{% if risk_flags.first_fail_reason %}
**Hard Stop Triggered:** {{ risk_flags.first_fail_reason }}
{% endif %}

**Forensic Metrics:**
- Beneish M-Score: {{ "%.2f"|format(risk_flags.beneish_m_score) }} {% if risk_flags.beneish_m_score > -2.22 %}⚠️{% else %}✓{% endif %}
- Altman Z-Score: {{ "%.2f"|format(risk_flags.altman_z_score) }} {% if risk_flags.altman_z_score < 1.81 %}⚠️{% else %}✓{% endif %}
- Sloan Accruals: {{ "%.3f"|format(risk_flags.accruals_ratio) }} {% if risk_flags.accruals_ratio > 0.10 %}⚠️{% else %}✓{% endif %}

{% endif %}

### Business & Market Risks

{{ business.top_risks }}

---

## Investment Catalysts

*Catalyst analysis requires earnings calendar and news monitoring (Phase 5)*

**Potential Catalysts:**
- Quarterly earnings releases
- Product launches or market expansions
- Regulatory approvals or changes
- Industry tailwinds

---

## Data Sources & Provenance

{% for source in sources %}
- **{{ source.type }}**: {{ source.table if source.table else source.ticker }}
  {% if source.fiscal_years %}(Fiscal Years: {{ source.fiscal_years|join(", ") }}){% endif %}
{% endfor %}

---

## Disclaimer

*This report is generated for research purposes only. It does not constitute investment advice. 
Past performance is not indicative of future results. All investments carry risk of loss.*

**Model Limitations:**
- DCF assumes perpetuity and may not reflect business lifecycle
- Comparables analysis is sector-based (not detailed peer selection)
- Business analysis relies on heuristics (full NLP parsing in production)

---

*Generated by Multi-Bagger Research System v1.0*
"""


def generate_report(
    context: Dict[str, Any],
    output_path: Path,
    config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate Markdown research report from context.
    
    Args:
        context: Report data (company, valuation, quality, business, etc.)
        output_path: Path to write Markdown file
        config: Optional configuration dict
        
    Returns:
        Path to generated Markdown file
    """
    # Add report metadata
    context['report_date'] = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Render template
    template = Template(REPORT_TEMPLATE)
    markdown = template.render(**context)
    
    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(markdown)
    
    logger.info(f"Generated report: {output_path}")
    
    return str(output_path)


def generate_pdf(
    markdown_path: Path,
    pdf_path: Path,
    config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Convert Markdown report to PDF.
    
    Args:
        markdown_path: Path to Markdown file
        pdf_path: Path to write PDF
        config: Optional configuration dict
        
    Returns:
        Path to generated PDF or None if disabled/failed
    """
    # MVP: PDF generation deferred (requires pandoc or similar)
    # In production, would use:
    # - pandoc: subprocess.run(['pandoc', markdown_path, '-o', pdf_path])
    # - weasyprint: HTML → PDF
    # - reportlab: Direct PDF generation
    
    logger.info(f"PDF generation not implemented in MVP (would create {pdf_path})")
    return None
