# FlightChecker

## State
Currently: Running in continuous mode (480 min interval) with Discord posting enabled. DC→Bay Area routes split into two windows: Jul 5-14 and Jul 16-31 (12 routes total).
Last session: 2026-05-19 (added Discord auto-posting)

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
- Added baggage_text field to FlightResult model, selectors, extraction pipeline, OCR extractors, and report template
- Added `--continuous` mode for background monitoring (runs every N minutes without scheduler)
- **Added Discord auto-posting to continuous mode** — results posted every 8h when new reports generated

## Latest run results (2026-05-02_0323)
SJC→ORD: Best combo $365 (outbound $151 + return $214)
SFO→ORD: Best combo $333 (outbound $119 + return $214)
Price Alert: SFO→ORD outbound $119 (↓42.5% from $207)

## Routes configured (active)
- SJC→ORD: June 13–30 (out), June 14–30 (ret) — nonstop only
- SFO→ORD: June 13–30 (out), June 14–30 (ret) — nonstop only
- SJC→LAS: June 13–30 (out), June 14–30 (ret) — nonstop only
- SFO→LAS: June 13–30 (out), June 14–30 (ret) — nonstop only
- IAD/BWI/DCA→SFO/SJC: Jul 5–14 one-way (Window A, after July 4th) — nonstop only
- IAD/BWI/DCA→SFO/SJC: Jul 16–31 one-way (Window B, after July 15th) — nonstop only

## Latest run results (2026-05-02_2313)
SJC→ORD: Best combo $385 (outbound $151 + return $234)
SFO→ORD: Best combo $333 (outbound $119 + return $214)

## Known issues
- Depart/arrive times have extra newlines (cosmetic only)
- Price alerts fired due to comparison with stale previous-run prices

## Next
- Monitor selector changes on Google Flights and update as needed
- Can start/stop continuous mode from Discord as needed

## Key decisions
- PYTHONIOENCODING=utf-8 required on Windows
- Google Flights: URL-based navigation (`?q=` param) is far more reliable than form filling
- Skyscanner: Kasada bot protection blocks headless Playwright — disabled
- Anti-bot: `--disable-blink-features=AutomationControlled` + navigator.webdriver override
- Baggage extraction is optional (no fallback to manual review if empty)
