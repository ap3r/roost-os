"""Formatting helpers for Roost OS reports.

All financial amounts are expected in cents.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def format_currency(cents: int) -> str:
    """Format cents as a dollar string.

    Examples:
        15000 -> "$150.00"
        0     -> "$0.00"
        -5000 -> "-$50.00"
    """
    if cents < 0:
        return f"-${abs(cents) / 100:,.2f}"
    return f"${cents / 100:,.2f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Format a percentage value.

    Examples:
        85.3  -> "85.3%"
        100.0 -> "100.0%"
    """
    return f"{value:.{decimals}f}%"


def format_date(d: date) -> str:
    """Format a date for display.

    Example:
        date(2026, 4, 14) -> "Apr 14, 2026"
    """
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def format_date_range(start: date, end: date) -> str:
    """Format a date range for display.

    Same year, same month:
        "Apr 14 \u2013 Apr 18, 2026"
    Different months or years:
        "Apr 14 \u2013 May 2, 2026"
    Different years:
        "Dec 28, 2025 \u2013 Jan 3, 2026"
    """
    start_day = start.strftime("%b %d").replace(" 0", " ")
    end_fmt = format_date(end)

    if start.year != end.year:
        return f"{format_date(start)} \u2013 {end_fmt}"

    return f"{start_day} \u2013 {end_fmt}"


def format_delta(cents: int) -> str:
    """Format cents as a signed currency string.

    Examples:
        1500  -> "+$15.00"
        -1000 -> "-$10.00"
        0     -> "+$0.00"
    """
    if cents < 0:
        return f"-${abs(cents) / 100:,.2f}"
    return f"+${cents / 100:,.2f}"


def format_nights(n: int) -> str:
    """Format a night count with proper pluralization.

    Examples:
        1 -> "1 night"
        3 -> "3 nights"
    """
    if n == 1:
        return "1 night"
    return f"{n} nights"
