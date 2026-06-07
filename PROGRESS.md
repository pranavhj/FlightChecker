# FlightChecker

## State
Currently: Enhanced extraction with flight company & baggage info (2026-05-01)
Last session: 2026-05-01

## Done
- Cloned repo, fixed Playwright API, encoding, pointer events, logging
- App generates reports (tested: outputs/reports/)
- Fixed bot detection: added `--disable-blink-features=AutomationControlled` + navigator.webdriver init script
- Fixed Windows user-agent mismatch (was Linux, now Windows)
- Fixed 30s hang: changed `wait_until="domcontentloaded"` → `"commit"` (15s timeout) for both scrapers
- Replaced form-fill with URL-based navigation for Google Flights (`?q=` param) — much more reliable
- Fixed reporter UnicodeEncodeError: added `encoding="utf-8"` to `write_text`
- Skyscanner disabled: blocked by Kasada "PRESS & HOLD" CAPTCHA
- Added filtering: `nonstop_only` and `same_day_return` options in routes.yaml
- Added SFO→LAS route, ran full June search: found $28-55 outbound, $28-60 return options (50-60% cheaper than SJC)
- **Added baggage_text field to FlightResult model (new field for carrying baggage info)**
- **Added baggage selectors to selector_registry.py for Google Flights and Skyscanner**
- **Updated GoogleFlightsScraper & SkyscannerScraper to extract baggage information**
- **Updated extraction pipeline to handle baggage_text field**
- **Updated OCR (Claude & easyocr) extractors to include baggage_text**
- **Updated report template to display baggage information in all result tables**

## Latest run results (2026-04-29_2348)
SJC→LAS (May 10): $69 nonstop (best), $326 x2
LAS→SJC (May 15): $69 nonstop (best), $214 x2
Best combo: $138 total ($69 + $69)

## Routes configured
- SJC→ORD (Chicago): June 13-29 (outbound), June 14-30 (return) — nonstop only
- SFO→ORD (Chicago): June 13-29 (outbound), June 14-30 (return) — nonstop only

## Known issues
- Airline name selector picks up airport code (SJC/LAS) instead of airline — data present but selector wrong
- Depart/arrive times have extra newlines (cosmetic only)
- Price alerts fired due to comparison with stale previous-run prices

## Next
- Fix airline name selector in selector_registry.py to properly extract airline names
- Test full SJC/SFO→Chicago search with new baggage extraction

## Key decisions
- PYTHONIOENCODING=utf-8 required on Windows
- Google Flights: URL-based navigation (`?q=` param) is far more reliable than form filling
- Skyscanner: Kasada bot protection blocks headless Playwright — disabled
- Anti-bot: `--disable-blink-features=AutomationControlled` + navigator.webdriver override
- Baggage extraction is optional (no fallback to manual review if empty)
