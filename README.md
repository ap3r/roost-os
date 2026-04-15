# Roost OS

A revenue intelligence agent for short-term rental hosts. Combines **Hospitable** (your PMS), **Airbnb comp scraping**, and **PriceLabs market data** into actionable pricing and occupancy insights — all powered by Claude Code.

There's no separate app to run. Claude Code *is* the agent. The Python scripts are data collection tools that Claude orchestrates through natural conversation.

## What It Does

**Ask Claude Code questions like:**
- "How are we doing?" — portfolio health check with occupancy, ADR, RevPAR
- "How's my pricing for July 4th week?" — pulls your calendar, scrapes Airbnb comps, compares to market data
- "Find gap nights" — detects orphan nights between bookings, recommends min-stay and price adjustments
- "Full report" — generates a comprehensive markdown report combining all three data sources

**Three data sources, one conversation:**

| Source | Method | What You Get |
|---|---|---|
| Hospitable | MCP (live API) | Calendar, reservations, pricing, reviews, financials |
| Airbnb | Playwright scraper | Competitor pricing, ratings, supply for your market |
| PriceLabs | PDF/CSV import | Market-wide ADR, occupancy, RevPAR, seasonal trends |

## Quick Start

### Prerequisites
- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with [Hospitable MCP](https://www.hospitable.com/mcp/) connected
- A Hospitable account with properties

### Install

```bash
git clone https://github.com/YOUR_USERNAME/roost-os.git
cd roost-os
uv venv .venv && source .venv/bin/activate
uv pip install -e .
playwright install chromium
```

### Configure

```bash
cp config/properties.example.yaml config/properties.yaml
```

Edit `config/properties.yaml` with your properties. To find your Hospitable UUIDs, ask Claude Code:

> "List my Hospitable properties"

Then fill in UUIDs, property types, bedroom counts, and define comp groups for your market.

### Use

Open Claude Code in the `roost-os` directory and start asking questions:

```
> How does my pricing compare to the market for next weekend?
> Scrape comps for July 4th week
> Any gap nights in the next 60 days?
> Generate a full portfolio report
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code                        │
│              (the "agent" — you talk to this)        │
├──────────┬──────────────┬───────────────────────────┤
│ Hospitable MCP │ Python Scripts    │ Analysis Engine      │
│ (live PMS data)│ (data collection) │ (portfolio metrics)  │
│                │                   │                      │
│ • Calendar     │ • scrape_comps.py │ • Occupancy/ADR/     │
│ • Reservations │   (Playwright)    │   RevPAR calc        │
│ • Reviews      │ • import_         │ • Gap night detect   │
│ • Financials   │   pricelabs.py    │ • Comp comparison    │
│ • Messaging    │ • generate_       │ • Price suggestions  │
│                │   report.py       │ • Seasonal context   │
└────────────────┴───────────────────┴──────────────────────┘
```

The Python code handles data collection and number-crunching. Claude Code handles orchestration, interpretation, and conversation — deciding which tools to run, combining results, and generating insights in plain English.

## Project Structure

```
roost-os/
├── CLAUDE.md                      # Agent instructions (Claude reads this)
├── config/
│   ├── properties.example.yaml    # Template — copy and fill in your data
│   └── properties.yaml            # Your config (gitignored)
├── src/roost/
│   ├── models.py                  # Shared dataclasses
│   ├── config.py                  # YAML config loader
│   ├── scraper/airbnb_search.py   # Airbnb scraper (GraphQL + DOM fallback)
│   ├── pricelabs/                 # PriceLabs CSV/PDF import
│   ├── analysis/                  # Portfolio, gap nights, pricing, seasonal
│   └── reports/                   # Markdown report generation
├── scripts/                       # CLI entry points
└── data/                          # Scrape results, reports (gitignored)
```

## How the Scraper Works

The Airbnb scraper uses Playwright to search Airbnb with your comp group criteria (location, bedrooms, guests, dates). It attempts to intercept `StaysSearch` GraphQL API responses for structured data, with a DOM fallback that parses listing cards directly. No API key needed — it works like a browser.

## Built With

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — the agent runtime
- [Hospitable MCP](https://www.hospitable.com/mcp/) — live PMS data
- [Playwright](https://playwright.dev/) — headless browser for Airbnb scraping
- [Pandas](https://pandas.pydata.org/) + [Pydantic](https://docs.pydantic.dev/) — data import and validation

## License

MIT
