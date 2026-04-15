#!/usr/bin/env python3
"""CLI script to generate a Roost OS portfolio report.

Usage:
    python scripts/generate_report.py --period last30
    python scripts/generate_report.py --period next90 --output my_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure the project src is importable when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from roost.config import load_properties  # noqa: E402
from roost.models import GapNight, PortfolioMetrics, PricingRecommendation  # noqa: E402
from roost.reports.generator import generate_portfolio_report, save_report  # noqa: E402

logger = logging.getLogger(__name__)

COMPS_DIR = PROJECT_ROOT / "data" / "comps"
PRICELABS_DIR = PROJECT_ROOT / "data" / "pricelabs" / "normalized"
HOSPITABLE_DIR = PROJECT_ROOT / "data" / "hospitable"

PERIOD_CHOICES = ("last7", "last30", "last90", "next30", "next90")


def _resolve_date_range(period: str) -> tuple[date, date]:
    """Convert a period name into a start/end date pair."""
    today = date.today()
    if period == "last7":
        return today - timedelta(days=7), today
    if period == "last30":
        return today - timedelta(days=30), today
    if period == "last90":
        return today - timedelta(days=90), today
    if period == "next30":
        return today, today + timedelta(days=30)
    if period == "next90":
        return today, today + timedelta(days=90)
    raise ValueError(f"Unknown period: {period}")


def _load_comp_data() -> dict | None:
    """Load the most recent comp JSON files from data/comps/."""
    if not COMPS_DIR.exists():
        logger.info("No comps directory found, skipping comp data")
        return None

    json_files = sorted(COMPS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        logger.info("No comp data files found")
        return None

    comp_data: dict = {}
    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            # Use filename stem as group key if not embedded in data
            key = data.get("comp_group", jf.stem)
            if key not in comp_data:
                comp_data[key] = data
                logger.info(f"Loaded comp data from {jf.name}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping invalid comp file {jf.name}: {e}")

    return comp_data if comp_data else None


def _load_pricelabs_data() -> list | None:
    """Load normalized PriceLabs data from data/pricelabs/normalized/."""
    if not PRICELABS_DIR.exists():
        logger.info("No PriceLabs normalized directory found, skipping market data")
        return None

    json_files = sorted(PRICELABS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        logger.info("No PriceLabs data files found")
        return None

    market_data: list = []
    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            if isinstance(data, list):
                market_data.extend(data)
            else:
                market_data.append(data)
            logger.info(f"Loaded PriceLabs data from {jf.name}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping invalid PriceLabs file {jf.name}: {e}")

    return market_data if market_data else None


def _load_hospitable_data() -> tuple[list[dict], list[GapNight], list[PricingRecommendation]]:
    """Load cached Hospitable data if available.

    Returns:
        Tuple of (calendar_data, gap_nights, pricing_recommendations).
    """
    calendars: list[dict] = []
    gap_nights: list[GapNight] = []
    pricing_recs: list[PricingRecommendation] = []

    if not HOSPITABLE_DIR.exists():
        logger.info(
            "No Hospitable data directory found at data/hospitable/. "
            "Calendar and reservation data should be gathered via the Hospitable MCP tools in Claude Code."
        )
        return calendars, gap_nights, pricing_recs

    # Load calendar data
    calendar_files = sorted(HOSPITABLE_DIR.glob("calendar_*.json"))
    for cf in calendar_files:
        try:
            with open(cf) as f:
                data = json.load(f)
            if isinstance(data, list):
                calendars.extend(data)
            else:
                calendars.append(data)
            logger.info(f"Loaded Hospitable calendar from {cf.name}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping invalid Hospitable file {cf.name}: {e}")

    # Load gap nights
    gap_files = sorted(HOSPITABLE_DIR.glob("gaps_*.json"))
    for gf in gap_files:
        try:
            with open(gf) as f:
                data = json.load(f)
            for item in (data if isinstance(data, list) else [data]):
                gap_nights.append(GapNight(
                    property_name=item.get("property_name", ""),
                    property_uuid=item.get("property_uuid", ""),
                    gap_start=date.fromisoformat(item["gap_start"]),
                    gap_end=date.fromisoformat(item["gap_end"]),
                    gap_nights=item.get("gap_nights", 0),
                    before_reservation=item.get("before_reservation"),
                    after_reservation=item.get("after_reservation"),
                    current_min_stay=item.get("current_min_stay"),
                    current_price_cents=item.get("current_price_cents"),
                    recommendation=item.get("recommendation", ""),
                ))
            logger.info(f"Loaded {len(gap_nights)} gap nights from {gf.name}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping invalid gap file {gf.name}: {e}")

    # Load pricing recommendations
    rec_files = sorted(HOSPITABLE_DIR.glob("recommendations_*.json"))
    for rf in rec_files:
        try:
            with open(rf) as f:
                data = json.load(f)
            for item in (data if isinstance(data, list) else [data]):
                pricing_recs.append(PricingRecommendation(
                    property_name=item.get("property_name", ""),
                    property_uuid=item.get("property_uuid", ""),
                    date_start=date.fromisoformat(item["date_start"]),
                    date_end=date.fromisoformat(item["date_end"]),
                    current_price_cents=item.get("current_price_cents", 0),
                    recommended_price_cents=item.get("recommended_price_cents", 0),
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", "medium"),
                ))
            logger.info(f"Loaded {len(pricing_recs)} recommendations from {rf.name}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping invalid recommendation file {rf.name}: {e}")

    return calendars, gap_nights, pricing_recs


def _build_property_metrics(
    properties: list,
    gap_nights: list[GapNight],
    pricing_recs: list[PricingRecommendation],
) -> list[dict]:
    """Build per-property metric dicts from available data.

    When Hospitable data is not cached, properties are included with
    zero metrics so the report structure is still complete.
    """
    # Index gaps and recommendations by property UUID
    gaps_by_uuid: dict[str, list[GapNight]] = {}
    for g in gap_nights:
        gaps_by_uuid.setdefault(g.property_uuid, []).append(g)

    recs_by_uuid: dict[str, list[PricingRecommendation]] = {}
    for r in pricing_recs:
        recs_by_uuid.setdefault(r.property_uuid, []).append(r)

    result: list[dict] = []
    for prop in properties:
        result.append({
            "name": prop.name,
            "type": prop.type.value,
            "bedrooms": prop.bedrooms,
            "max_guests": prop.max_guests,
            "uuid": prop.uuid,
            "occupancy_pct": 0.0,
            "adr_cents": 0,
            "revpar_cents": 0,
            "revenue_cents": 0,
            "comp_position": "N/A",
            "gaps": gaps_by_uuid.get(prop.uuid, []),
            "recommendations": recs_by_uuid.get(prop.uuid, []),
        })

    return result


def main() -> None:
    """Entry point for report generation."""
    parser = argparse.ArgumentParser(
        description="Generate a Roost OS portfolio report."
    )
    parser.add_argument(
        "--period",
        choices=PERIOD_CHOICES,
        default="last30",
        help="Reporting period (default: last30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output filename (saved under data/reports/)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(f"Generating report for period: {args.period}")

    # Resolve date range
    period_start, period_end = _resolve_date_range(args.period)
    logger.info(f"Date range: {period_start} to {period_end}")

    # Load property config
    properties = load_properties()
    logger.info(f"Loaded {len(properties)} properties from config")

    # Load external data sources (graceful degradation)
    comp_data = _load_comp_data()
    market_data = _load_pricelabs_data()

    # Load Hospitable data (or print instructions)
    calendars, gap_nights, pricing_recs = _load_hospitable_data()
    if not calendars:
        print(
            "\n"
            "NOTE: No cached Hospitable data found.\n"
            "To gather calendar and reservation data, use Claude Code with the\n"
            "Hospitable MCP tools:\n"
            "  1. Use get-property-calendar for each property\n"
            "  2. Use get-reservations for each property\n"
            "  3. Save results to data/hospitable/ as JSON\n"
            "The report will be generated with placeholder metrics.\n"
        )

    # Build per-property metrics
    property_metrics = _build_property_metrics(properties, gap_nights, pricing_recs)

    # Build portfolio-level metrics
    total_gap_nights = sum(g.gap_nights for g in gap_nights)
    portfolio_metrics = PortfolioMetrics(
        period_start=period_start,
        period_end=period_end,
        properties_count=len(properties),
        gap_nights=total_gap_nights,
    )

    # Generate the report
    report = generate_portfolio_report(
        portfolio_metrics=portfolio_metrics,
        property_metrics=property_metrics,
        gap_nights=gap_nights,
        pricing_recommendations=pricing_recs,
        comp_data=comp_data,
        market_data=market_data,
    )

    # Save
    output_path = save_report(report, filename=args.output)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
