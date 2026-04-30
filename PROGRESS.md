# FlightChecker

## State
Currently: Added flight filtering (nonstop, same-day returns)
Last session: 2026-04-29

## Done
- Cloned repo, fixed Playwright API, encoding, pointer events, logging
- App generates reports (tested: outputs/reports/)
- Fixed bot detection: added `--disable-blink-features=AutomationControlled` + `navigator.webdriver` init script
- Fixed Windows user-agent mismatch (was Linux, now Windows)
- Fixed 30s hang: changed `wait_until="domcontentloaded"` → `"commit"` (15s timeout) for both scrapers
- Replaced form-fill with URL-based navigation for Google Flights (`?q=` param) — much more reliable
- Fixed reporter UnicodeEncodeError: added `encoding="utf-8"` to `write_text`
- Skyscanner disabled: blocked by Kasada "PRESS & HOLD" CAPTCHA
- Added filtering: `nonstop_only` and `same_day_return` options in routes.yaml

## Latest run results (2026-04-29_2348)
SJC→LAS (May 10): $69 nonstop (best), $326 x2
LAS→SJC (May 15): $69 nonstop (best), $214 x2
Best combo: $138 total ($69 + $69)

## Known issues
- Airline name selector picks up airport code (SJC/LAS) instead of airline — data present but selector wrong
- Depart/arrive times have extra newlines (cosmetic only)
- Price alerts fired due to comparison with stale previous-run prices

## Next
- Fix airline name selector in selector_registry.py
- Consider adding a second source (Expedia/Kayak) since Skyscanner is blocked

## Key decisions
- PYTHONIOENCODING=utf-8 required on Windows
- Google Flights: URL-based navigation (`?q=` param) is far more reliable than form filling
- Skyscanner: Kasada bot protection blocks headless Playwright — disabled
- Anti-bot: `--disable-blink-features=AutomationControlled` + navigator.webdriver override
