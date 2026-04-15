"""Report generation orchestrator for Roost OS."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from roost.models import GapNight, PortfolioMetrics, PricingRecommendation
from roost.reports.formatters import (
    format_currency,
    format_date_range,
    format_delta,
    format_nights,
    format_pct,
)
from roost.reports.templates import (
    EXECUTIVE_SUMMARY_TEMPLATE,
    GAP_NIGHTS_TABLE_TEMPLATE,
    PROPERTY_CARD_TEMPLATE,
    RECOMMENDATIONS_TEMPLATE,
    render_template,
)

logger = logging.getLogger(__name__)

# Project root is three levels up from this file: src/roost/reports/generator.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"


def _build_gap_nights_section(gaps: list[GapNight]) -> str:
    """Build the gap nights markdown table for a property."""
    if not gaps:
        return ""

    rows: list[str] = []
    for gap in gaps:
        date_range = format_date_range(gap.gap_start, gap.gap_end)
        nights = format_nights(gap.gap_nights)
        price = format_currency(gap.current_price_cents) if gap.current_price_cents is not None else "N/A"
        recommendation = gap.recommendation or "N/A"
        rows.append(f"| {date_range} | {nights} | {price} | {recommendation} |")

    rows_str = "\n".join(rows)
    return render_template(GAP_NIGHTS_TABLE_TEMPLATE, rows=rows_str)


def _build_pricing_notes(recommendations: list[PricingRecommendation]) -> str:
    """Build pricing recommendation notes for a property."""
    if not recommendations:
        return ""

    lines: list[str] = []
    for rec in recommendations:
        date_range = format_date_range(rec.date_start, rec.date_end)
        current = format_currency(rec.current_price_cents)
        recommended = format_currency(rec.recommended_price_cents)
        delta = format_delta(rec.recommended_price_cents - rec.current_price_cents)
        lines.append(
            f"- **{date_range}**: {current} -> {recommended} ({delta}) \u2014 {rec.reason} [{rec.confidence}]"
        )

    return "\n".join(lines)


def _build_recommendations_section(recommendations: list[PricingRecommendation]) -> str:
    """Build the top-level pricing recommendations section."""
    if not recommendations:
        return ""

    lines: list[str] = []
    for rec in recommendations:
        date_range = format_date_range(rec.date_start, rec.date_end)
        current = format_currency(rec.current_price_cents)
        recommended = format_currency(rec.recommended_price_cents)
        delta = format_delta(rec.recommended_price_cents - rec.current_price_cents)
        lines.append(
            f"- **{rec.property_name}** {date_range}: "
            f"{current} -> {recommended} ({delta}) \u2014 {rec.reason} [{rec.confidence}]"
        )

    recs_text = "\n".join(lines)
    return render_template(RECOMMENDATIONS_TEMPLATE, recommendations=recs_text)


def generate_portfolio_report(
    portfolio_metrics: PortfolioMetrics,
    property_metrics: list[dict],
    gap_nights: list[GapNight],
    pricing_recommendations: list[PricingRecommendation],
    comp_data: dict | None = None,
    market_data: list | None = None,
) -> str:
    """Generate a complete markdown portfolio report.

    Args:
        portfolio_metrics: Aggregated portfolio-level metrics.
        property_metrics: Per-property metric dicts with keys:
            name, type, bedrooms, max_guests, uuid, occupancy_pct,
            adr_cents, revpar_cents, revenue_cents, comp_position,
            gaps (list[GapNight]), recommendations (list[PricingRecommendation]).
        gap_nights: All gap night opportunities across the portfolio.
        pricing_recommendations: All pricing recommendations.
        comp_data: Optional dict of comp snapshot data keyed by comp_group.
        market_data: Optional list of PriceLabs market data records.

    Returns:
        Complete markdown report string.
    """
    logger.info(
        f"Generating portfolio report for {portfolio_metrics.period_start} "
        f"to {portfolio_metrics.period_end}"
    )

    sections: list[str] = []

    # Executive summary
    period_str = format_date_range(portfolio_metrics.period_start, portfolio_metrics.period_end)
    summary = render_template(
        EXECUTIVE_SUMMARY_TEMPLATE,
        period=period_str,
        properties_count=str(portfolio_metrics.properties_count),
        occupancy=format_pct(portfolio_metrics.occupancy_pct),
        adr=format_currency(portfolio_metrics.adr_cents),
        revpar=format_currency(portfolio_metrics.revpar_cents),
        revenue=format_currency(portfolio_metrics.total_revenue_cents),
        gap_nights=str(portfolio_metrics.gap_nights),
    )
    sections.append(summary)

    # Property cards
    if property_metrics:
        sections.append("## Property Details\n")
        for pm in property_metrics:
            prop_gaps: list[GapNight] = pm.get("gaps", [])
            prop_recs: list[PricingRecommendation] = pm.get("recommendations", [])

            gap_section = _build_gap_nights_section(prop_gaps)
            pricing_notes = _build_pricing_notes(prop_recs)

            card = render_template(
                PROPERTY_CARD_TEMPLATE,
                name=pm.get("name", "Unknown"),
                type=pm.get("type", ""),
                bedrooms=str(pm.get("bedrooms", "")),
                max_guests=str(pm.get("max_guests", "")),
                occupancy=format_pct(pm.get("occupancy_pct", 0.0)),
                adr=format_currency(pm.get("adr_cents", 0)),
                revpar=format_currency(pm.get("revpar_cents", 0)),
                revenue=format_currency(pm.get("revenue_cents", 0)),
                comp_position=pm.get("comp_position", "N/A"),
                gap_nights_section=gap_section,
                pricing_notes=pricing_notes,
            )
            sections.append(card)

    # Market data summary (if available)
    if market_data:
        sections.append("## Market Data\n")
        sections.append("_PriceLabs market data is available for this period._\n")

    # Comp data summary (if available)
    if comp_data:
        sections.append("## Competitive Data\n")
        sections.append(f"_Comp data available for {len(comp_data)} group(s)._\n")

    # Recommendations section
    recs_section = _build_recommendations_section(pricing_recommendations)
    if recs_section:
        sections.append(recs_section)

    report = "\n".join(sections)
    logger.info(f"Report generated: {len(report)} characters, {len(property_metrics)} properties")
    return report


def save_report(content: str, filename: str | None = None) -> Path:
    """Save a report to the data/reports directory.

    Args:
        content: Markdown report content.
        filename: Optional custom filename. Defaults to report_YYYY-MM-DD.md.

    Returns:
        Path to the saved report file.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"report_{date.today().isoformat()}.md"

    filepath = REPORTS_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Report saved to {filepath}")
    return filepath
