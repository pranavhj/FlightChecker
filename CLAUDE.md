# FlightChecker

Playwright-based flight price monitor. Scrapes Google Flights and Skyscanner 3x/day, outputs a Markdown report, tracks price history, and alerts on drops.

## What was built

- **One-way and return flight support** — return routes search each leg independently (outbound + return as separate one-way searches), then rank best combinations by total cost
- **4-tier extraction pipeline** — DOM → Claude vision OCR → EasyOCR → manual review flag
- **Claude OCR via delegation** — no Anthropic API key; uses `scripts/agent-smart.py` (minimal claude CLI wrapper) to delegate vision calls through Claude Code's own auth
- **Price history + delta alerts** — persisted in `outputs/price_history.json`; alerts fire when price drops ≥5% vs previous run
- **3x/day scheduler** — 7am/1pm/7pm PT; `--once` flag for single runs

## Routes configured

`config/routes.yaml` — SJC→LAS and SJC→ORD, both return, May–June 2026 windows.

## How to run

```bash
# Validate config
python -m flightchecker --dry-run

# Single run
python -m flightchecker --once

# Scheduled (3x/day)
python -m flightchecker
```

Requires `claude` on PATH and logged in (used by OCR fallback via `scripts/agent-smart.py`).

## Key files

```
config/routes.yaml          # add/edit routes here
config/settings.yaml        # headless, schedule, scoring, alert threshold
flightchecker/scrapers/selector_registry.py   # CSS selectors — update when sites change DOM
flightchecker/extraction/ocr_claude.py        # Claude OCR via agent-smart delegation
scripts/agent-smart.py      # minimal claude CLI wrapper (--print-file → stdin pipe)
outputs/price_history.json  # persisted price history (gitignored)
outputs/reports/            # generated Markdown reports (gitignored)
```

## Dependency notes

- `easyocr` (tertiary OCR fallback) is in `requirements.txt` but optional — skip it to avoid the ~2GB PyTorch install. Pipeline works without it.
- `anthropic` SDK is NOT used — OCR goes through `scripts/agent-smart.py` instead.

## Selector maintenance

Google Flights and Skyscanner update their DOM regularly. When reports show mostly `ocr_claude` extraction method instead of `dom`, the selectors in `selector_registry.py` are stale. Run with `headless: false` in `settings.yaml` to inspect the live page and update selectors.

## Bot detection

If reports return empty results with `manual_review` confidence, the scraper is likely being blocked. First step: set `headless: false` in `config/settings.yaml` and re-run to see what the browser is receiving.

## Tests

```bash
python -m pytest tests/ -v
```

29 tests covering ranker, config loader, price history, and extraction pipeline.
