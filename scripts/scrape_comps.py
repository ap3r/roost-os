#!/usr/bin/env python3
"""CLI script to scrape Airbnb comps for configured comp groups.

Usage:
    python scripts/scrape_comps.py --group downtown_small
    python scripts/scrape_comps.py --group all --checkin 2026-07-10 --checkout 2026-07-12
    python scripts/scrape_comps.py --group rural_cabin --max-pages 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure the project src is importable when running as a script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from roost.config import load_comp_groups
from roost.scraper.airbnb_search import comps_to_dicts, scrape_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "comps"


def _next_weekday(start: date, weekday: int) -> date:
    """Return the next date on or after `start` that falls on `weekday` (0=Mon, 4=Fri, 6=Sun)."""
    days_ahead = weekday - start.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return start + timedelta(days=days_ahead)


def _default_checkin() -> str:
    """Next Friday from today."""
    return _next_weekday(date.today(), weekday=4).isoformat()


def _default_checkout() -> str:
    """Next Sunday from today (the Sunday after next Friday)."""
    next_friday = _next_weekday(date.today(), weekday=4)
    return (next_friday + timedelta(days=2)).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Airbnb search results for comp groups defined in properties.yaml",
    )
    parser.add_argument(
        "--group",
        required=True,
        help='Comp group key (e.g. "downtown_small") or "all" to scrape every group',
    )
    parser.add_argument(
        "--checkin",
        default=_default_checkin(),
        help="Check-in date YYYY-MM-DD (default: next Friday)",
    )
    parser.add_argument(
        "--checkout",
        default=_default_checkout(),
        help="Checkout date YYYY-MM-DD (default: next Sunday)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum search result pages to scrape per group (default: 3)",
    )
    return parser.parse_args()


async def scrape_group(
    group_key: str,
    location: str,
    checkin: str,
    checkout: str,
    guests: int,
    min_bedrooms: int,
    max_pages: int,
) -> Path:
    """Scrape a single comp group and save results to JSON. Returns output path."""
    logger.info(f"Scraping group '{group_key}': {location} | {checkin} -> {checkout} | {guests} guests, {min_bedrooms}+ BR")

    comps = await scrape_search(
        location=location,
        checkin=checkin,
        checkout=checkout,
        guests=guests,
        min_bedrooms=min_bedrooms,
        max_pages=max_pages,
    )

    # Write output
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    output_path = DATA_DIR / f"{group_key}_{checkin}_to_{checkout}.json"

    output_data = {
        "comp_group": group_key,
        "scraped_date": today_str,
        "checkin": checkin,
        "checkout": checkout,
        "total_comps": len(comps),
        "comps": comps_to_dicts(comps),
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    logger.info(f"Saved {len(comps)} comps to {output_path}")

    return output_path


async def main() -> None:
    args = parse_args()

    comp_groups = load_comp_groups()
    logger.info(f"Loaded {len(comp_groups)} comp groups from config")

    if args.group == "all":
        group_keys = list(comp_groups.keys())
    else:
        if args.group not in comp_groups:
            logger.error(f"Unknown comp group '{args.group}'. Available: {', '.join(comp_groups.keys())}")
            sys.exit(1)
        group_keys = [args.group]

    logger.info(f"Scraping {len(group_keys)} group(s): {', '.join(group_keys)}")
    logger.info(f"Dates: {args.checkin} -> {args.checkout}, max pages: {args.max_pages}")

    for key in group_keys:
        group = comp_groups[key]
        output_path = await scrape_group(
            group_key=key,
            location=group.location,
            checkin=args.checkin,
            checkout=args.checkout,
            guests=group.guests,
            min_bedrooms=group.min_bedrooms,
            max_pages=args.max_pages,
        )
        logger.info(f"Finished group '{key}' -> {output_path}")

    logger.info("All groups complete")


if __name__ == "__main__":
    asyncio.run(main())
