# FlightChecker

## State
Currently: Weekend search live: SFO/OAK/SJC -> IAD/DCA/BWI, 4-day Fri->Mon and Thu->Sun trips, every weekend through 2026-12-31. Each leg searched one-way and filtered separately (max_stops: 1, under 8.5 h), cheapest qualifying leg per date, paired by weekend and ranked by total. Report has an overall cheapest table across all 9 routes.
Last session: 2026-10-12

## Done
- Fixed Discord update: dep_time newlines cleaned (was "11:15 PM\n–\n9:35 AM"), best_pairings now shows times/duration/stops/baggage per leg
- Cloned repo, fixed Playwright API, encoding, pointer events, logging
- App generates reports (tested: outputs/reports/)
- Fixed bot detection: added `--disable-blink-features=AutomationControlled` + navigator.webdriver init script
- Fixed Windows user-agent mismatch (was Linux, now Windows)
- Fixed 30s hang: changed `wait_until="domcontentloaded"` → `"commit"` (15s timeout) for both scrapers
- Replaced form-fill with URL-based navigation for Google Flights (`?q=` param) — much more reliable
- Fixed reporter UnicodeEncodeError: added `encoding="utf-8"` to `write_text`
- Skyscanner disabled: blocked by Kasada "PRESS & HOLD" CAPTCHA
- Added filtering: `nonstop_only` and `same_day_return` options in routes.yaml
- Added baggage_text field to FlightResult model, selectors, extraction pipeline, OCR extractors, and report template
- Added `--continuous` mode for background monitoring (runs every N minutes without scheduler)
- Added Discord auto-posting to continuous mode — results posted every 8h when new reports generated
- **Reconfigured for SFO→BOM** — added max_duration_hours, checked_bag_required, same_airline_only filters
- Fixed config_loader to actually read nonstop_only/same_day_return from YAML (was always using defaults)
- Fixed DURATION_RE to handle "28 hr 30 min" format (Google Flights uses "hr"/"min" not just "h"/"m")

## Test run results (2026-06-10, 2-date narrow window)
- SFO→BOM Jul 5: Lufthansa, 21h 50min, 1 stop, $1,049 (passes all filters)
- BOM→SFO Jul 25: British Airways, 28h 30min, 1 stop, $1,045 (filtered by 28h limit after regex fix)
- Best combo: $2,094 (2 dates only; full window run pending)

## Routes configured (active)
- SFO → Mumbai (BOM)
  - Outbound: Jul 25 – Aug 2, 2026
  - Return: Aug 15 – Aug 30, 2026 (3.5–4 weeks after each departure)
  - max_duration_hours: 26 (each leg)
  - nonstop_only: false
  - top_n_results: 5
- Last one-time run: 2026-06-30 (--once, manual request)
- Continuous mode previously ran at PID 2840 (2026-06-25); may need restart if still running

## Known issues
- Baggage extraction often empty for international flights — checked_bag_required filter passes through on empty baggage_text (conservative)

## Next
- Monitor first round-trip sweep results (one-way sweep + up to 25 RT combos)
- Round-trip prices appear in report as "Round-trip Fares" section, sorted by combined fare

## Key decisions
- PYTHONIOENCODING=utf-8 required on Windows
- Google Flights: URL-based navigation (`?q=` param) is far more reliable than form filling
- Skyscanner: Kasada bot protection blocks headless Playwright — disabled
- Anti-bot: `--disable-blink-features=AutomationControlled` + navigator.webdriver override
- Baggage extraction is optional (no fallback to manual review if empty)
- Duration regex must handle "28 hr 30 min" format and hours-only "3h" (regex made minutes group optional)
- Round-trip sweep: after one-way sweep, pick top-5 out dates × top-5 ret dates → up to 25 RT searches → report shows combined fares
- RT results stored as FlightResult with leg="roundtrip" and return_date field
- `weekend_trips` route spec (routes.yaml): `origins`/`destinations` lists expand to all pairs; `patterns` = [out_weekday, ret_weekday]; pairs with return after `end` or before today are dropped
- Weekend (date_pairs) routes use one-way searches per leg, not round-trip pages: a round-trip results page only describes the outbound flight, so the return leg could not be verified. Legs with unreadable price/stops/duration are rejected
