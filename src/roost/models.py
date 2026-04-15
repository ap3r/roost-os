"""Shared data models for Roost OS."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

logger = logging.getLogger(__name__)


class PropertyType(str, Enum):
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    COTTAGE = "cottage"
    HOUSE = "house"


class Season(str, Enum):
    PEAK = "peak"
    HIGH = "high"
    SHOULDER_FALL = "shoulder_fall"
    MODERATE = "moderate"
    SHOULDER_SPRING = "shoulder_spring"
    LOW = "low"


@dataclass
class Property:
    """A property in the portfolio."""
    name: str
    uuid: str
    type: PropertyType
    bedrooms: int
    max_guests: int
    comp_group: str


@dataclass
class CompGroup:
    """Search criteria for a competitive set."""
    key: str
    label: str
    location: str
    min_bedrooms: int
    max_bedrooms: int
    guests: int
    property_type: str


@dataclass
class SeasonConfig:
    """Seasonal demand configuration."""
    key: str
    label: str
    months: list[int]
    multiplier: float


@dataclass
class CalendarDay:
    """A single day on a property's calendar."""
    date: date
    available: bool
    price_cents: int | None = None
    min_stay: int | None = None
    reservation_id: str | None = None


@dataclass
class Reservation:
    """A reservation on a property."""
    uuid: str
    property_uuid: str
    checkin: date
    checkout: date
    status: str
    guest_name: str = ""
    platform: str = ""
    accommodation_cents: int = 0
    total_cents: int = 0
    nights: int = 0


@dataclass
class AirbnbComp:
    """A competitor listing scraped from Airbnb search results."""
    listing_id: str
    title: str
    property_type: str
    bedrooms: int
    capacity: int
    nightly_price_cents: int
    total_price_cents: int
    rating: float | None = None
    review_count: int = 0
    superhost: bool = False
    latitude: float | None = None
    longitude: float | None = None
    amenities: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class CompSnapshot:
    """A point-in-time snapshot of comps for a group."""
    comp_group: str
    scraped_date: date
    checkin: date
    checkout: date
    comps: list[AirbnbComp] = field(default_factory=list)


@dataclass
class PriceLabsMarketData:
    """Aggregated market data from PriceLabs export."""
    date: date
    market: str
    occupancy_pct: float | None = None
    adr_cents: int | None = None
    revpar_cents: int | None = None
    avg_lead_time_days: int | None = None
    supply: int | None = None
    demand: int | None = None


@dataclass
class GapNight:
    """An orphan/gap night opportunity."""
    property_name: str
    property_uuid: str
    gap_start: date
    gap_end: date
    gap_nights: int
    before_reservation: str | None = None
    after_reservation: str | None = None
    current_min_stay: int | None = None
    current_price_cents: int | None = None
    recommendation: str = ""


@dataclass
class PricingRecommendation:
    """A pricing adjustment recommendation."""
    property_name: str
    property_uuid: str
    date_start: date
    date_end: date
    current_price_cents: int
    recommended_price_cents: int
    reason: str
    confidence: str = "medium"  # low, medium, high


@dataclass
class PortfolioMetrics:
    """Aggregated portfolio performance metrics."""
    period_start: date
    period_end: date
    total_nights: int = 0
    occupied_nights: int = 0
    occupancy_pct: float = 0.0
    total_revenue_cents: int = 0
    adr_cents: int = 0
    revpar_cents: int = 0
    gap_nights: int = 0
    properties_count: int = 0
