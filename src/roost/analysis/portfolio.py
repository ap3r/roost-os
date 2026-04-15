"""Portfolio-level performance analysis for Roost OS.

Calculates occupancy, ADR, RevPAR, and monthly breakdowns across
one or more properties. All financial amounts are in cents (integers).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from roost.models import CalendarDay, PortfolioMetrics, Reservation

logger = logging.getLogger(__name__)


def calculate_occupancy(calendar: list[CalendarDay]) -> float:
    """Calculate occupancy percentage (0-100) from a calendar.

    A day counts as occupied when it is not available (i.e., booked or blocked
    with a reservation).  Days with no reservation_id that are marked unavailable
    are still counted as occupied to reflect calendar blocking behaviour.
    """
    if not calendar:
        logger.warning("Empty calendar passed to calculate_occupancy")
        return 0.0

    total_days = len(calendar)
    occupied_days = sum(1 for day in calendar if not day.available)

    occupancy = (occupied_days / total_days) * 100
    logger.debug(
        f"Occupancy: {occupied_days}/{total_days} days = {occupancy:.1f}%"
    )
    return round(occupancy, 2)


def calculate_adr(reservations: list[Reservation]) -> int:
    """Calculate average daily rate in cents.

    ADR = total accommodation revenue / total booked nights.
    Only counts reservations with status 'accepted' or 'checkpoint'.
    """
    if not reservations:
        logger.warning("No reservations passed to calculate_adr")
        return 0

    active_reservations = [
        r for r in reservations if r.status in ("accepted", "checkpoint")
    ]
    if not active_reservations:
        logger.info("No active reservations for ADR calculation")
        return 0

    total_revenue = sum(r.accommodation_cents for r in active_reservations)
    total_nights = sum(r.nights for r in active_reservations)

    if total_nights == 0:
        logger.warning("Active reservations have zero total nights")
        return 0

    adr = total_revenue // total_nights
    logger.debug(
        f"ADR: {total_revenue} cents / {total_nights} nights = {adr} cents"
    )
    return adr


def calculate_revpar(
    calendar: list[CalendarDay], reservations: list[Reservation]
) -> int:
    """Calculate Revenue Per Available Room-night (RevPAR) in cents.

    RevPAR = total accommodation revenue / total available nights in period.
    """
    if not calendar:
        logger.warning("Empty calendar passed to calculate_revpar")
        return 0

    total_nights = len(calendar)

    active_reservations = [
        r for r in reservations if r.status in ("accepted", "checkpoint")
    ]
    total_revenue = sum(r.accommodation_cents for r in active_reservations)

    if total_nights == 0:
        return 0

    revpar = total_revenue // total_nights
    logger.debug(
        f"RevPAR: {total_revenue} cents / {total_nights} nights = {revpar} cents"
    )
    return revpar


def monthly_breakdown(
    calendar: list[CalendarDay], reservations: list[Reservation]
) -> list[dict]:
    """Break down performance metrics by month.

    Returns a list of dicts sorted by month, each containing:
        month           -- "YYYY-MM"
        occupancy_pct   -- float 0-100
        adr_cents       -- int
        revpar_cents    -- int
        revenue_cents   -- int
        nights_occupied -- int
        nights_available -- int
    """
    if not calendar:
        logger.warning("Empty calendar passed to monthly_breakdown")
        return []

    # Bucket calendar days by month
    month_days: dict[str, list[CalendarDay]] = defaultdict(list)
    for day in calendar:
        month_key = day.date.strftime("%Y-%m")
        month_days[month_key].append(day)

    # Build a set of calendar dates for quick lookups
    calendar_dates = {day.date for day in calendar}

    # Distribute reservation revenue across months proportionally by night
    month_revenue: dict[str, int] = defaultdict(int)

    active_reservations = [
        r for r in reservations if r.status in ("accepted", "checkpoint")
    ]

    for res in active_reservations:
        if res.nights == 0:
            continue
        nightly_rate = res.accommodation_cents // res.nights
        current = res.checkin
        while current < res.checkout:
            if current in calendar_dates:
                month_key = current.strftime("%Y-%m")
                month_revenue[month_key] += nightly_rate
            current += timedelta(days=1)

    # Count occupied nights per month from calendar (unavailable days)
    month_occupied: dict[str, int] = defaultdict(int)
    for day in calendar:
        if not day.available:
            month_key = day.date.strftime("%Y-%m")
            month_occupied[month_key] += 1

    results = []
    for month_key in sorted(month_days.keys()):
        days = month_days[month_key]
        nights_available = len(days)
        nights_occ = month_occupied.get(month_key, 0)
        revenue = month_revenue.get(month_key, 0)

        occ_pct = (nights_occ / nights_available * 100) if nights_available else 0.0
        adr = revenue // nights_occ if nights_occ > 0 else 0
        revpar = revenue // nights_available if nights_available > 0 else 0

        results.append({
            "month": month_key,
            "occupancy_pct": round(occ_pct, 2),
            "adr_cents": adr,
            "revpar_cents": revpar,
            "revenue_cents": revenue,
            "nights_occupied": nights_occ,
            "nights_available": nights_available,
        })

    logger.info(f"Monthly breakdown computed for {len(results)} months")
    return results


def portfolio_summary(
    calendars: dict[str, list[CalendarDay]],
    reservations: dict[str, list[Reservation]],
    period_start: date,
    period_end: date,
) -> PortfolioMetrics:
    """Aggregate metrics across all properties in the portfolio.

    Args:
        calendars: dict keyed by property UUID -> list of CalendarDay
        reservations: dict keyed by property UUID -> list of Reservation
        period_start: inclusive start date of analysis period
        period_end: inclusive end date of analysis period

    Returns:
        PortfolioMetrics with aggregated totals.
    """
    total_nights = 0
    occupied_nights = 0
    total_revenue = 0

    for prop_uuid, calendar in calendars.items():
        # Filter calendar to period
        period_days = [
            day for day in calendar
            if period_start <= day.date <= period_end
        ]
        total_nights += len(period_days)
        occupied_nights += sum(1 for d in period_days if not d.available)

    for prop_uuid, res_list in reservations.items():
        active = [
            r for r in res_list if r.status in ("accepted", "checkpoint")
        ]
        total_revenue += sum(r.accommodation_cents for r in active)

    occ_pct = (occupied_nights / total_nights * 100) if total_nights else 0.0
    adr = total_revenue // occupied_nights if occupied_nights else 0
    revpar = total_revenue // total_nights if total_nights else 0

    metrics = PortfolioMetrics(
        period_start=period_start,
        period_end=period_end,
        total_nights=total_nights,
        occupied_nights=occupied_nights,
        occupancy_pct=round(occ_pct, 2),
        total_revenue_cents=total_revenue,
        adr_cents=adr,
        revpar_cents=revpar,
        properties_count=len(calendars),
    )

    logger.info(
        f"Portfolio summary: {metrics.properties_count} properties, "
        f"{metrics.occupancy_pct}% occupancy, "
        f"ADR ${metrics.adr_cents / 100:.2f}, "
        f"RevPAR ${metrics.revpar_cents / 100:.2f}"
    )
    return metrics
