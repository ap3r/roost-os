# Roost OS

Revenue intelligence for short-term rental hosts, built on Claude Code.

This uses Claude Code to interact with the [Hospitable MCP server](https://www.hospitable.com/mcp/) for live PMS data (calendar, reservations, financials, messaging), parses and ingests PriceLabs market reports, and uses a Playwright-based Airbnb searcher to get live competitor booking data. Claude Code orchestrates all three and does the analysis — occupancy, ADR, gap night detection, comp-based pricing — through natural conversation.

There's no separate app. You open Claude Code in this directory and ask questions like "How are we doing?" or "Any gap nights in the next 60 days?"

## Setup

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
> Find comps for July 4th week
> Any gap nights in the next 60 days?
> Generate a full portfolio report
```

## How It Works

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

The Python code handles data collection and number-crunching. Claude Code decides which tools to run, combines results, and gives you the analysis.

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
│   ├── scraper/airbnb_search.py   # Airbnb search (GraphQL + DOM fallback)
│   ├── pricelabs/                 # PriceLabs CSV/PDF import
│   ├── analysis/                  # Portfolio, gap nights, pricing, seasonal
│   └── reports/                   # Markdown report generation
├── scripts/                       # CLI entry points
└── data/                          # Results and reports (gitignored)
```

## Airbnb Search

Uses Playwright to search Airbnb with your comp group criteria (location, bedrooms, guests, dates). Intercepts `StaysSearch` GraphQL API responses for structured data, with a DOM fallback that parses listing cards directly. No API key needed.

## Built With

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — agent runtime
- [Hospitable MCP](https://www.hospitable.com/mcp/) — live PMS data
- [Playwright](https://playwright.dev/) — Airbnb search
- [Pandas](https://pandas.pydata.org/) + [Pydantic](https://docs.pydantic.dev/) — data pipeline

## License

MIT
