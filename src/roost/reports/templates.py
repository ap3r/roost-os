"""Markdown report templates for Roost OS."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


EXECUTIVE_SUMMARY_TEMPLATE = """\
# Portfolio Report \u2014 {period}

## Executive Summary
| Metric | Value |
|---|---|
| Properties | {properties_count} |
| Occupancy | {occupancy} |
| ADR | {adr} |
| RevPAR | {revpar} |
| Revenue | {revenue} |
| Gap Nights | {gap_nights} |
"""


PROPERTY_CARD_TEMPLATE = """\
### {name}
**{type} \u00b7 {bedrooms}BR \u00b7 Up to {max_guests} guests**

| Metric | Value |
|---|---|
| Occupancy | {occupancy} |
| ADR | {adr} |
| RevPAR | {revpar} |
| Revenue | {revenue} |
| vs. Comps | {comp_position} |

{gap_nights_section}
{pricing_notes}
"""


GAP_NIGHTS_TABLE_TEMPLATE = """\
#### Gap Nights
| Dates | Nights | Current Price | Recommendation |
|---|---|---|---|
{rows}
"""


RECOMMENDATIONS_TEMPLATE = """\
## Pricing Recommendations
{recommendations}
"""


def render_template(template: str, **kwargs: str) -> str:
    """Render a template with safe substitution.

    Missing keys are replaced with "N/A" instead of raising KeyError.
    """

    class SafeDict(dict):  # type: ignore[type-arg]
        def __missing__(self, key: str) -> str:
            logger.debug(f"Template key missing, using default: {key}")
            return "N/A"

    return template.format_map(SafeDict(**kwargs))
