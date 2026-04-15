#!/usr/bin/env python3
"""CLI script to import PriceLabs CSV exports and save normalized JSON."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))

from roost.pricelabs.importer import import_all_csvs  # noqa: E402
from roost.pricelabs.schemas import CompSetRow, MarketSummaryRow  # noqa: E402

logger = logging.getLogger(__name__)


def _serialize_rows(
    rows: list[MarketSummaryRow] | list[CompSetRow],
) -> list[dict]:
    """Convert a list of Pydantic models to JSON-serializable dicts."""
    return [row.model_dump(mode="json") for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import PriceLabs CSV exports and save normalized JSON.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/pricelabs/"),
        help="Directory containing PriceLabs CSV files (default: data/pricelabs/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/pricelabs/normalized/"),
        help="Output directory for normalized JSON files (default: data/pricelabs/normalized/)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    input_dir: Path = args.input
    output_dir: Path = args.output

    if not input_dir.is_dir():
        logger.error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Input directory: {input_dir}")
    logger.info(f"Output directory: {output_dir}")

    results = import_all_csvs(input_dir)

    if not results:
        logger.warning("No CSV files were imported")
        sys.exit(0)

    total_rows = 0
    for filename, rows in results.items():
        stem = Path(filename).stem
        output_path = output_dir / f"{stem}.json"

        serialized = _serialize_rows(rows)
        total_rows += len(serialized)

        with open(output_path, "w") as f:
            json.dump(serialized, f, indent=2, default=str)

        export_type = "market_summary" if rows and isinstance(rows[0], MarketSummaryRow) else "comp_set"
        logger.info(f"Saved {output_path} ({len(serialized)} {export_type} rows)")

    logger.info(
        f"Import complete: {len(results)} files processed, "
        f"{total_rows} total rows written to {output_dir}"
    )


if __name__ == "__main__":
    main()
