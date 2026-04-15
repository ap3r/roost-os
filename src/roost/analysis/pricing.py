"""Pricing analysis for Roost OS.

Compares property pricing against Airbnb comps and PriceLabs market data,
then generates adjustment recommendations.

All financial amounts are in cents (integers).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from roost.models import (
    AirbnbComp,
    CalendarDay,
    PriceLabsMarketData,
    PricingRecommendation,
)

logger = logging.getLogger(__name__)


def _median(values: list[int]) -> int:
    """Calculate the median of a list of integers.

    Returns 0 for an empty list.
    """
    if not values:
        return 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) // 2
    return sorted_vals[mid]


def _percentile_rank(value: int, values: list[int]) -> float:
    """Calculate the percentile rank (0-100) of a value within a list.

    Uses the "percentage of values below" method. Returns 0.0 for an
    empty list.
    """
    if not values:
        return 0.0
    count_below = sum(1 for v in values if v < value)
    count_equal = sum(1 for v in values if v == value)
    # Standard percentile rank formula: (B + 0.5*E) / N * 100
    rank = (count_below + 0.5 * count_equal) / len(values) * 100
    return round(rank, 1)


def compare_to_comps(
    property_price_cents: int, comps: list[AirbnbComp]
) -> dict:
    """Compare a property's price against its competitive set.

    Args:
        property_price_cents: the property's current nightly price in cents
        comps: list of AirbnbComp scraped from search results

    Returns:
        Dict with keys: your_price_cents, comp_avg_cents, comp_median_cents,
        comp_min_cents, comp_max_cents, percentile_rank, comp_count
    """
    if not comps:
        logger.warning("No comps provided for price comparison")
        return {
            "your_price_cents": property_price_cents,
            "comp_avg_cents": 0,
            "comp_median_cents": 0,
            "comp_min_cents": 0,
            "comp_max_cents": 0,
            "percentile_rank": 0.0,
            "comp_count": 0,
        }

    comp_prices = [c.nightly_price_cents for c in comps]
    comp_avg = sum(comp_prices) // len(comp_prices)
    comp_med = _median(comp_prices)
    comp_min = min(comp_prices)
    comp_max = max(comp_prices)
    pct_rank = _percentile_rank(property_price_cents, comp_prices)

    result = {
        "your_price_cents": property_price_cents,
        "comp_avg_cents": comp_avg,
        "comp_median_cents": comp_med,
        "comp_min_cents": comp_min,
        "comp_max_cents": comp_max,
        "percentile_rank": pct_rank,
        "comp_count": len(comps),
    }

    logger.debug(
        f"Comp comparison: ${property_price_cents / 100:.2f} vs "
        f"avg ${comp_avg / 100:.2f} (rank {pct_rank:.0f}th percentile, "
        f"{len(comps)} comps)"
    )
    return result


def compare_to_market(
    property_adr_cents: int, market_data: list[PriceLabsMarketData]
) -> dict:
    """Compare a property's ADR against PriceLabs market averages.

    Args:
        property_adr_cents: the property's ADR in cents
        market_data: list of PriceLabsMarketData entries

    Returns:
        Dict with keys: your_adr_cents, market_adr_cents, delta_cents, delta_pct
    """
    if not market_data:
        logger.warning("No market data provided for comparison")
        return {
            "your_adr_cents": property_adr_cents,
            "market_adr_cents": 0,
            "delta_cents": 0,
            "delta_pct": 0.0,
        }

    market_adrs = [
        m.adr_cents for m in market_data
        if m.adr_cents is not None
    ]
    if not market_adrs:
        logger.warning("Market data entries have no ADR values")
        return {
            "your_adr_cents": property_adr_cents,
            "market_adr_cents": 0,
            "delta_cents": 0,
            "delta_pct": 0.0,
        }

    market_avg = sum(market_adrs) // len(market_adrs)
    delta = property_adr_cents - market_avg
    delta_pct = (delta / market_avg * 100) if market_avg else 0.0

    result = {
        "your_adr_cents": property_adr_cents,
        "market_adr_cents": market_avg,
        "delta_cents": delta,
        "delta_pct": round(delta_pct, 2),
    }

    logger.debug(
        f"Market comparison: ${property_adr_cents / 100:.2f} vs "
        f"market ${market_avg / 100:.2f} "
        f"(delta {'+' if delta >= 0 else ''}{delta_pct:.1f}%)"
    )
    return result


def suggest_price_adjustments(
    property_name: str,
    property_uuid: str,
    calendar: list[CalendarDay],
    comps: list[AirbnbComp],
    market_data: list[PriceLabsMarketData] | None = None,
) -> list[PricingRecommendation]:
    """Analyze each available date and suggest pricing adjustments.

    Rules applied in order:
        1. Last-minute (within 7 days, still available): recommend a discount
           to fill the night.
        2. Overpriced (>20% above comp avg, 14+ days out): recommend lowering
           to close the gap.
        3. Underpriced (>15% below comp avg): recommend raising to capture
           more revenue.

    Args:
        property_name: human-readable property name
        property_uuid: property identifier
        calendar: list of CalendarDay objects for the property
        comps: list of AirbnbComp for the property's competitive set
        market_data: optional PriceLabs market data for additional context

    Returns:
        List of PricingRecommendation objects.
    """
    if not calendar:
        logger.warning(f"Empty calendar for {property_name}, skipping pricing analysis")
        return []

    if not comps:
        logger.warning(f"No comps for {property_name}, skipping pricing analysis")
        return []

    comp_prices = [c.nightly_price_cents for c in comps]
    comp_avg = sum(comp_prices) // len(comp_prices)

    if comp_avg == 0:
        logger.warning(f"Comp average is $0 for {property_name}, skipping")
        return []

    today = date.today()
    recommendations: list[PricingRecommendation] = []

    # Sort calendar for chronological processing
    sorted_cal = sorted(
        [d for d in calendar if d.available and d.price_cents is not None],
        key=lambda d: d.date,
    )

    for day in sorted_cal:
        price = day.price_cents
        assert price is not None  # filtered above
        days_out = (day.date - today).days

        # Skip past dates
        if days_out < 0:
            continue

        delta_pct = (price - comp_avg) / comp_avg * 100

        # Rule 1: Last-minute discount (within 7 days, still available)
        if days_out <= 7:
            # Suggest 15% discount from current price
            discount_price = int(price * 0.85)
            recommendations.append(PricingRecommendation(
                property_name=property_name,
                property_uuid=property_uuid,
                date_start=day.date,
                date_end=day.date,
                current_price_cents=price,
                recommended_price_cents=discount_price,
                reason=(
                    f"Last-minute availability ({days_out} days out). "
                    f"Discount 15% to fill."
                ),
                confidence="high",
            ))

        # Rule 2: Overpriced (>20% above comp avg, 14+ days out)
        elif delta_pct > 20 and days_out >= 14:
            # Recommend pricing at 5% above comp average
            target_price = int(comp_avg * 1.05)
            recommendations.append(PricingRecommendation(
                property_name=property_name,
                property_uuid=property_uuid,
                date_start=day.date,
                date_end=day.date,
                current_price_cents=price,
                recommended_price_cents=target_price,
                reason=(
                    f"Priced {delta_pct:.0f}% above comp avg "
                    f"(${comp_avg / 100:.2f}). Lower to improve bookings."
                ),
                confidence="medium",
            ))

        # Rule 3: Underpriced (>15% below comp avg)
        elif delta_pct < -15:
            # Recommend pricing at 5% below comp average
            target_price = int(comp_avg * 0.95)
            recommendations.append(PricingRecommendation(
                property_name=property_name,
                property_uuid=property_uuid,
                date_start=day.date,
                date_end=day.date,
                current_price_cents=price,
                recommended_price_cents=target_price,
                reason=(
                    f"Priced {abs(delta_pct):.0f}% below comp avg "
                    f"(${comp_avg / 100:.2f}). Raise to capture revenue."
                ),
                confidence="medium",
            ))

    logger.info(
        f"Generated {len(recommendations)} pricing recommendations "
        f"for {property_name}"
    )
    return recommendations
