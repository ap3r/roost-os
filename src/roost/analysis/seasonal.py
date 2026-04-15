"""Traverse City seasonal demand patterns for Roost OS.

Maps dates to seasonal demand multipliers and provides pricing context
based on the Traverse City tourism calendar. The National Cherry Festival
is the single biggest demand driver, followed by summer/fall color seasons.

All financial amounts are in cents (integers).
"""

from __future__ import annotations

import logging
from datetime import date

from roost.config import load_seasons
from roost.models import CalendarDay, SeasonConfig

logger = logging.getLogger(__name__)

# National Cherry Festival dates by year.
# The festival traditionally runs from the first Saturday after July 1
# through the following Saturday (8 days).
CHERRY_FESTIVAL_DATES: dict[int, tuple[date, date]] = {
    # 2025: July 1 is a Tuesday -> first Saturday after = July 5
    2025: (date(2025, 7, 5), date(2025, 7, 12)),
    # 2026: July 1 is a Wednesday -> first Saturday after = July 4
    2026: (date(2026, 7, 4), date(2026, 7, 11)),
}


def get_season(d: date) -> SeasonConfig:
    """Determine which season a date falls in.

    Loads season definitions from the project configuration and matches
    the date's month. Falls back to a default "moderate" season if no
    match is found (should not happen with a complete config).

    Args:
        d: the date to classify

    Returns:
        SeasonConfig for the matching season.
    """
    seasons = load_seasons()

    for season in seasons:
        if d.month in season.months:
            logger.debug(f"{d} -> {season.label} (x{season.multiplier})")
            return season

    # Fallback -- should not be reached with a complete config
    logger.warning(
        f"No season config found for month {d.month}, "
        f"defaulting to moderate (1.0x)"
    )
    return SeasonConfig(
        key="unknown",
        label="Unknown",
        months=[d.month],
        multiplier=1.0,
    )


def get_season_multiplier(d: date) -> float:
    """Return the seasonal demand multiplier for a date.

    Convenience wrapper around get_season().
    """
    return get_season(d).multiplier


def seasonal_pricing_context(
    calendar: list[CalendarDay], base_adr_cents: int
) -> list[dict]:
    """Build per-day pricing context with seasonal adjustments.

    For each calendar day, returns a dict with:
        date                -- date object
        season_name         -- human-readable season label
        multiplier          -- seasonal demand multiplier
        current_price_cents -- price currently set on the calendar
        suggested_price_cents -- base_adr * multiplier (seasonally-adjusted)

    Args:
        calendar: list of CalendarDay objects
        base_adr_cents: the property's baseline ADR in cents, used as
                        the anchor for seasonal adjustments

    Returns:
        List of dicts, one per calendar day, sorted chronologically.
    """
    if not calendar:
        logger.warning("Empty calendar passed to seasonal_pricing_context")
        return []

    if base_adr_cents <= 0:
        logger.warning(
            f"Invalid base ADR ({base_adr_cents} cents), "
            f"seasonal suggestions will be zero"
        )

    sorted_cal = sorted(calendar, key=lambda d: d.date)
    results: list[dict] = []

    for day in sorted_cal:
        season = get_season(day.date)
        suggested = int(base_adr_cents * season.multiplier)

        results.append({
            "date": day.date,
            "season_name": season.label,
            "multiplier": season.multiplier,
            "current_price_cents": day.price_cents,
            "suggested_price_cents": suggested,
        })

    logger.info(
        f"Seasonal pricing context built for {len(results)} days "
        f"(base ADR ${base_adr_cents / 100:.2f})"
    )
    return results
