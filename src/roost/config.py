"""YAML configuration loader for Roost OS."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from roost.models import CompGroup, Property, PropertyType, SeasonConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parents[2] / "config" / "properties.yaml"


def load_config(path: Path | None = None) -> dict:
    """Load and return the raw YAML config."""
    config_path = path or DEFAULT_CONFIG_PATH
    logger.info(f"Loading config from {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_properties(path: Path | None = None) -> list[Property]:
    """Load properties from config."""
    config = load_config(path)
    properties = []
    for p in config["properties"]:
        properties.append(Property(
            name=p["name"],
            uuid=p["uuid"],
            type=PropertyType(p["type"]),
            bedrooms=p["bedrooms"],
            max_guests=p["max_guests"],
            comp_group=p["comp_group"],
        ))
    logger.info(f"Loaded {len(properties)} properties")
    return properties


def load_comp_groups(path: Path | None = None) -> dict[str, CompGroup]:
    """Load comp group definitions from config."""
    config = load_config(path)
    groups = {}
    for key, g in config["comp_groups"].items():
        groups[key] = CompGroup(
            key=key,
            label=g["label"],
            location=g["location"],
            min_bedrooms=g["min_bedrooms"],
            max_bedrooms=g["max_bedrooms"],
            guests=g["guests"],
            property_type=g["property_type"],
        )
    return groups


def load_seasons(path: Path | None = None) -> list[SeasonConfig]:
    """Load seasonal demand config."""
    config = load_config(path)
    seasons = []
    for key, s in config["seasons"].items():
        seasons.append(SeasonConfig(
            key=key,
            label=s["label"],
            months=s["months"],
            multiplier=s["multiplier"],
        ))
    return seasons


def get_property_by_uuid(uuid: str, path: Path | None = None) -> Property | None:
    """Find a property by UUID (prefix match supported)."""
    for p in load_properties(path):
        if p.uuid.startswith(uuid):
            return p
    return None


def get_property_by_name(name: str, path: Path | None = None) -> Property | None:
    """Find a property by name (case-insensitive substring match)."""
    name_lower = name.lower()
    for p in load_properties(path):
        if name_lower in p.name.lower():
            return p
    return None
