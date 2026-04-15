"""CSV import with fuzzy column matching for PriceLabs exports."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from roost.pricelabs.schemas import CompSetRow, MarketSummaryRow

logger = logging.getLogger(__name__)

# Maps each canonical column name to a list of known aliases (case-insensitive).
# Order matters: the first match wins when multiple aliases appear.
COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["Date", "date", "Report Date"],
    "market": ["Market", "market", "Market Name"],
    "occupancy_pct": [
        "Occupancy", "Occ", "occupancy_pct", "Occ %",
        "Occupancy %", "Occupancy Rate",
    ],
    "adr_cents": [
        "ADR", "adr", "Avg Daily Rate", "adr_usd", "Average Daily Rate",
    ],
    "revpar_cents": ["RevPAR", "revpar", "revpar_usd", "Rev PAR"],
    "supply": ["Supply", "supply", "Total Supply", "Active Listings"],
    "demand": ["Demand", "demand", "Booked Nights", "Occupied"],
    "avg_lead_time_days": ["Avg Lead Time", "Lead Time", "avg_lead_time_days"],
    "listing_name": ["Listing Name", "listing_name", "Property", "Name"],
    "listing_id": ["Listing ID", "listing_id", "Airbnb ID"],
    "rating": ["Rating", "rating", "Avg Rating"],
    "review_count": ["Reviews", "review_count", "Review Count", "Num Reviews"],
}

# Column sets that distinguish the two export types
MARKET_SUMMARY_REQUIRED = {"date", "market"}
COMP_SET_REQUIRED = {"date", "listing_name"}

# All canonical columns for each type
MARKET_SUMMARY_COLUMNS = {
    "date", "market", "occupancy_pct", "adr_cents", "revpar_cents",
    "avg_lead_time_days", "supply", "demand",
}
COMP_SET_COLUMNS = {
    "date", "listing_name", "listing_id", "occupancy_pct",
    "adr_cents", "revpar_cents", "rating", "review_count",
}


def _build_reverse_alias_map() -> dict[str, str]:
    """Build a lowercase alias -> canonical name lookup."""
    reverse: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lower = alias.lower().strip()
            if lower not in reverse:
                reverse[lower] = canonical
    return reverse


_REVERSE_ALIASES = _build_reverse_alias_map()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-match raw CSV column names to canonical names via the alias map.

    Columns that do not match any alias are dropped with a debug log.
    """
    rename_map: dict[str, str] = {}
    used_canonical: set[str] = set()

    for raw_col in df.columns:
        lookup = raw_col.strip().lower()
        canonical = _REVERSE_ALIASES.get(lookup)
        if canonical and canonical not in used_canonical:
            rename_map[raw_col] = canonical
            used_canonical.add(canonical)
            logger.debug(f"Column '{raw_col}' -> '{canonical}'")
        elif canonical and canonical in used_canonical:
            logger.debug(f"Skipping duplicate mapping for '{raw_col}' -> '{canonical}'")
        else:
            logger.debug(f"Column '{raw_col}' has no alias match, dropping")

    df = df.rename(columns=rename_map)
    # Keep only columns that were successfully mapped
    mapped_cols = [c for c in df.columns if c in set(COLUMN_ALIASES.keys())]
    return df[mapped_cols]


def detect_export_type(columns: list[str]) -> str:
    """Determine whether a set of columns represents a market summary or comp set.

    Args:
        columns: List of *canonical* column names (post-normalization).

    Returns:
        "market_summary" or "comp_set".

    Raises:
        ValueError: If the columns do not match either known export type.
    """
    col_set = set(columns)

    has_market = MARKET_SUMMARY_REQUIRED.issubset(col_set)
    has_comp = COMP_SET_REQUIRED.issubset(col_set)

    if has_market and not has_comp:
        return "market_summary"
    if has_comp and not has_market:
        return "comp_set"
    if has_market and has_comp:
        # Both match -- comp_set exports have listing_name but not market
        if "listing_name" in col_set and "market" not in col_set:
            return "comp_set"
        if "market" in col_set and "listing_name" not in col_set:
            return "market_summary"
        # If both present, check for comp-set-specific columns
        if "rating" in col_set or "review_count" in col_set:
            return "comp_set"
        return "market_summary"

    raise ValueError(
        f"Cannot determine export type from columns: {columns}. "
        f"Expected {MARKET_SUMMARY_REQUIRED} for market_summary or "
        f"{COMP_SET_REQUIRED} for comp_set."
    )


def import_pricelabs_csv(
    filepath: Path,
) -> list[MarketSummaryRow] | list[CompSetRow]:
    """Read a PriceLabs CSV, detect its type, normalize columns, and validate rows.

    Bad rows are skipped with a warning rather than aborting the entire import.

    Args:
        filepath: Path to the CSV file.

    Returns:
        A list of validated Pydantic model instances.
    """
    filepath = Path(filepath)
    logger.info(f"Importing PriceLabs CSV: {filepath}")

    df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
    logger.info(f"Read {len(df)} rows with columns: {list(df.columns)}")

    df = normalize_columns(df)
    canonical_cols = list(df.columns)
    logger.info(f"Normalized columns: {canonical_cols}")

    export_type = detect_export_type(canonical_cols)
    logger.info(f"Detected export type: {export_type}")

    model_cls = MarketSummaryRow if export_type == "market_summary" else CompSetRow
    valid_rows: list[MarketSummaryRow] | list[CompSetRow] = []
    error_count = 0

    for idx, row in df.iterrows():
        row_dict = {k: (v if v != "" else None) for k, v in row.to_dict().items()}
        try:
            validated = model_cls.model_validate(row_dict)
            valid_rows.append(validated)  # type: ignore[arg-type]
        except (ValidationError, ValueError) as exc:
            error_count += 1
            logger.warning(f"Skipping row {idx} in {filepath.name}: {exc}")

    logger.info(
        f"Imported {len(valid_rows)} valid rows from {filepath.name} "
        f"({error_count} skipped)"
    )
    return valid_rows


def import_all_csvs(
    directory: Path,
) -> dict[str, list[MarketSummaryRow] | list[CompSetRow]]:
    """Batch-import all CSV files in a directory.

    Args:
        directory: Path to the directory containing CSV files.

    Returns:
        Dict keyed by filename, values are lists of validated rows.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    # Warn about non-CSV files that might need manual conversion
    pdf_files = sorted(directory.glob("*.pdf"))
    if pdf_files:
        logger.warning(
            f"Found {len(pdf_files)} PDF file(s) in {directory} — these cannot be imported automatically. "
            "PriceLabs PDF market dashboards should be extracted manually or via Claude Code. "
            f"Files: {', '.join(f.name for f in pdf_files)}"
        )

    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files found in {directory}")
        return {}

    logger.info(f"Found {len(csv_files)} CSV files in {directory}")
    results: dict[str, list[MarketSummaryRow] | list[CompSetRow]] = {}

    for csv_path in csv_files:
        try:
            rows = import_pricelabs_csv(csv_path)
            results[csv_path.name] = rows
        except Exception as exc:
            logger.error(f"Failed to import {csv_path.name}: {exc}")

    logger.info(f"Batch import complete: {len(results)}/{len(csv_files)} files imported")
    return results
