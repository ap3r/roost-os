"""Gap/orphan night detection for Roost OS.

Identifies short available blocks between reservations that are unlikely
to get booked at current minimum-stay settings, and generates actionable
recommendations to capture that lost revenue.

All financial amounts are in cents (integers).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from roost.models import CalendarDay, GapNight

logger = logging.getLogger(__name__)


def find_gap_nights(
    property_name: str,
    property_uuid: str,
    calendar: list[CalendarDay],
    min_stay: int = 2,
) -> list[GapNight]:
    """Walk the calendar chronologically and find orphan night gaps.

    A gap is a contiguous block of available nights shorter than *min_stay*
    that sits between booked/unavailable days. These nights are effectively
    unsellable at the current minimum-stay setting.

    Args:
        property_name: human-readable property name for reports
        property_uuid: property identifier
        calendar: sorted list of CalendarDay objects
        min_stay: minimum stay threshold -- available blocks shorter than
                  this are flagged as gaps

    Returns:
        List of GapNight objects, one per detected gap.
    """
    if not calendar:
        logger.warning(f"Empty calendar for {property_name}, skipping gap detection")
        return []

    # Sort calendar by date to ensure chronological order
    sorted_cal = sorted(calendar, key=lambda d: d.date)

    gaps: list[GapNight] = []
    available_block: list[CalendarDay] = []

    # Track the reservation ID of the day immediately before the current block
    before_reservation: str | None = None

    for i, day in enumerate(sorted_cal):
        if day.available:
            # Starting a new available block -- record what came before
            if not available_block and i > 0:
                prev = sorted_cal[i - 1]
                before_reservation = prev.reservation_id
            available_block.append(day)
        else:
            # Day is booked/unavailable -- flush the available block if any
            if available_block:
                block_len = len(available_block)
                effective_min_stay = _effective_min_stay(available_block, min_stay)

                if block_len < effective_min_stay:
                    after_reservation = day.reservation_id

                    # Average price across the gap nights for revenue estimation
                    prices = [
                        d.price_cents for d in available_block
                        if d.price_cents is not None
                    ]
                    avg_price = sum(prices) // len(prices) if prices else None

                    gap = GapNight(
                        property_name=property_name,
                        property_uuid=property_uuid,
                        gap_start=available_block[0].date,
                        gap_end=available_block[-1].date,
                        gap_nights=block_len,
                        before_reservation=before_reservation,
                        after_reservation=after_reservation,
                        current_min_stay=effective_min_stay,
                        current_price_cents=avg_price,
                    )
                    gaps.append(gap)
                    logger.debug(
                        f"Gap found: {property_name} "
                        f"{gap.gap_start} - {gap.gap_end} ({block_len} nights)"
                    )

                available_block = []
                before_reservation = None

            # Update before_reservation for the next potential block
            before_reservation = day.reservation_id

    # Handle trailing available block at end of calendar
    if available_block:
        block_len = len(available_block)
        effective_min_stay = _effective_min_stay(available_block, min_stay)

        if block_len < effective_min_stay:
            prices = [
                d.price_cents for d in available_block
                if d.price_cents is not None
            ]
            avg_price = sum(prices) // len(prices) if prices else None

            gap = GapNight(
                property_name=property_name,
                property_uuid=property_uuid,
                gap_start=available_block[0].date,
                gap_end=available_block[-1].date,
                gap_nights=block_len,
                before_reservation=before_reservation,
                after_reservation=None,
                current_min_stay=effective_min_stay,
                current_price_cents=avg_price,
            )
            gaps.append(gap)

    logger.info(
        f"Found {len(gaps)} gap(s) for {property_name} "
        f"({sum(g.gap_nights for g in gaps)} total orphan nights)"
    )
    return gaps


def _effective_min_stay(block: list[CalendarDay], default: int) -> int:
    """Determine the effective minimum stay for a block.

    Uses the max min_stay value set on any day in the block, falling back
    to the provided default.
    """
    min_stays = [
        d.min_stay for d in block
        if d.min_stay is not None
    ]
    if min_stays:
        return max(min_stays)
    return default


def generate_recommendations(gaps: list[GapNight]) -> list[GapNight]:
    """Attach actionable recommendation strings to each gap.

    Recommendations vary by gap length and urgency (how soon the gap is):
        - 1-night gap: suggest lowering min stay to 1, discount 10-15%
        - 2-night gap: suggest lowering min stay to 2, discount 5-10%
        - Gaps within 7 days of today: prefix with "URGENT"

    Args:
        gaps: list of GapNight objects (modified in place and returned)

    Returns:
        The same list with recommendation fields populated.
    """
    today = date.today()

    for gap in gaps:
        days_until = (gap.gap_start - today).days
        urgent = days_until <= 7 and days_until >= 0
        prefix = "URGENT: " if urgent else ""

        if gap.gap_nights == 1:
            gap.recommendation = (
                f"{prefix}Lower min stay to 1 for {gap.gap_start}, "
                f"discount 10-15%"
            )
        elif gap.gap_nights == 2:
            gap.recommendation = (
                f"{prefix}Lower min stay to 2 for "
                f"{gap.gap_start}-{gap.gap_end}, discount 5-10%"
            )
        else:
            # Gaps of 3+ nights that are still below min_stay
            gap.recommendation = (
                f"{prefix}Lower min stay to {gap.gap_nights} for "
                f"{gap.gap_start}-{gap.gap_end}, consider 5% discount"
            )

        logger.debug(f"Recommendation: {gap.recommendation}")

    return gaps


def summarize_gaps(gaps: list[GapNight]) -> dict:
    """Produce a summary of all detected gaps.

    Returns a dict with:
        total_gap_nights      -- int, sum of all orphan nights
        gaps_by_property      -- dict mapping property name to count of gaps
        potential_revenue_cents -- int, estimated recoverable revenue
                                  (current price * 0.85 for each gap night)
    """
    total_gap_nights = sum(g.gap_nights for g in gaps)

    gaps_by_property: dict[str, int] = defaultdict(int)
    for g in gaps:
        gaps_by_property[g.property_name] += g.gap_nights

    # Estimate potential revenue at a 15% discount from current pricing
    potential_revenue = 0
    for g in gaps:
        if g.current_price_cents is not None:
            discounted = int(g.current_price_cents * 0.85)
            potential_revenue += discounted * g.gap_nights

    summary = {
        "total_gap_nights": total_gap_nights,
        "gaps_by_property": dict(gaps_by_property),
        "potential_revenue_cents": potential_revenue,
    }

    logger.info(
        f"Gap summary: {total_gap_nights} total orphan nights across "
        f"{len(gaps_by_property)} properties, "
        f"potential revenue ${potential_revenue / 100:.2f}"
    )
    return summary
