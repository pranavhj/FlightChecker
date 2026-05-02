# FlightChecker

## State
Currently: DOM selectors refined for Google Flights — airline names & baggage info now extracted correctly (2026-05-02)
Last session: 2026-05-02

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

## Latest run results (2026-05-02_0323)
SJC→ORD: Best combo $365 (outbound $151 + return $214)
SFO→ORD: Best combo $333 (outbound $119 + return $214)
Price Alert: SFO→ORD outbound $119 (↓42.5% from $207)

## Routes configured (active)
- SJC→ORD: June 13 (out), June 14 (ret) — nonstop only
- SFO→ORD: June 13 (out), June 14 (ret) — nonstop only

## Latest run results (2026-05-02_2313)
SJC→ORD: Best combo $385 (outbound $151 + return $234)
SFO→ORD: Best combo $333 (outbound $119 + return $214)

## Known issues
- Depart/arrive times have extra newlines (cosmetic only)
- Price alerts fired due to comparison with stale previous-run prices

## Next
- Consider OCR fallback for baggage extraction if DOM selectors miss data (fallback available)
- Monitor selector changes on Google Flights and update as needed

## Key decisions
- PYTHONIOENCODING=utf-8 required on Windows
- Google Flights: URL-based navigation (`?q=` param) is far more reliable than form filling
- Skyscanner: Kasada bot protection blocks headless Playwright — disabled
- Anti-bot: `--disable-blink-features=AutomationControlled` + navigator.webdriver override
- Baggage extraction is optional (no fallback to manual review if empty)
