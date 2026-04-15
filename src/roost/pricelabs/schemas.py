"""Pydantic v2 models for PriceLabs CSV data."""

from __future__ import annotations

import logging
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)


def _dollars_to_cents(value: float | int | None) -> int | None:
    """Convert a dollar amount to integer cents, returning None for missing data."""
    if value is None:
        return None
    return round(float(value) * 100)


class MarketSummaryRow(BaseModel):
    """A single row from a PriceLabs Market Summary export."""

    model_config = ConfigDict(strict=False, populate_by_name=True)

    date: date
    market: str
    occupancy_pct: float | None = None
    adr_cents: int | None = None
    revpar_cents: int | None = None
    avg_lead_time_days: int | None = None
    supply: int | None = None
    demand: int | None = None

    @field_validator("occupancy_pct", mode="before")
    @classmethod
    def parse_occupancy(cls, v: str | float | None) -> float | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().rstrip("%")
            if not v:
                return None
            v = float(v)
        # If the value looks like a whole-number percentage (> 1), normalize to 0-1
        if v > 1:
            return round(v / 100, 4)
        return round(float(v), 4)

    @field_validator("adr_cents", mode="before")
    @classmethod
    def parse_adr(cls, v: str | float | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().lstrip("$").replace(",", "")
            if not v:
                return None
        return _dollars_to_cents(float(v))

    @field_validator("revpar_cents", mode="before")
    @classmethod
    def parse_revpar(cls, v: str | float | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().lstrip("$").replace(",", "")
            if not v:
                return None
        return _dollars_to_cents(float(v))

    @field_validator("avg_lead_time_days", mode="before")
    @classmethod
    def parse_lead_time(cls, v: str | int | float | None) -> int | None:
        if v is None or v == "":
            return None
        return int(float(v))

    @field_validator("supply", "demand", mode="before")
    @classmethod
    def parse_int_field(cls, v: str | int | float | None) -> int | None:
        if v is None or v == "":
            return None
        return int(float(v))

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v: str | date) -> date:
        if isinstance(v, date):
            return v
        return date.fromisoformat(v.strip())


class CompSetRow(BaseModel):
    """A single row from a PriceLabs Comp Set export."""

    model_config = ConfigDict(strict=False, populate_by_name=True)

    date: date
    listing_name: str
    listing_id: str | None = None
    occupancy_pct: float | None = None
    adr_cents: int | None = None
    revpar_cents: int | None = None
    rating: float | None = None
    review_count: int | None = None

    @field_validator("occupancy_pct", mode="before")
    @classmethod
    def parse_occupancy(cls, v: str | float | None) -> float | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().rstrip("%")
            if not v:
                return None
            v = float(v)
        if v > 1:
            return round(v / 100, 4)
        return round(float(v), 4)

    @field_validator("adr_cents", mode="before")
    @classmethod
    def parse_adr(cls, v: str | float | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().lstrip("$").replace(",", "")
            if not v:
                return None
        return _dollars_to_cents(float(v))

    @field_validator("revpar_cents", mode="before")
    @classmethod
    def parse_revpar(cls, v: str | float | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.strip().lstrip("$").replace(",", "")
            if not v:
                return None
        return _dollars_to_cents(float(v))

    @field_validator("rating", mode="before")
    @classmethod
    def parse_rating(cls, v: str | float | None) -> float | None:
        if v is None or v == "":
            return None
        return round(float(v), 2)

    @field_validator("review_count", mode="before")
    @classmethod
    def parse_review_count(cls, v: str | int | float | None) -> int | None:
        if v is None or v == "":
            return None
        return int(float(v))

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v: str | date) -> date:
        if isinstance(v, date):
            return v
        return date.fromisoformat(v.strip())

    @field_validator("listing_id", mode="before")
    @classmethod
    def parse_listing_id(cls, v: str | int | None) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()
