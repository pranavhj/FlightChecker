# FlightChecker

Playwright flight price monitor. Searches Google Flights once a day, writes a Markdown report,
keeps price history in SQLite, posts the cheapest trips to Discord #reminders, alerts on drops.

## Where it runs: the Raspberry Pi 5 (moved 2026-10-26)

- Repo: **`pi5:flightchecker`** (`~/flightchecker`, branch `claude/dc-trips-pi`), mirrored to
  GitHub `pranavhj/FlightChecker` (same branch). The Pi copy is the deployed one; the PC folder
  `C:\Users\prana\projects\flightchecker` holds only a pointer `CLAUDE.md`.
- Runtime: systemd **timer** `flightchecker.timer` (07:00 PT daily, `Persistent=true`) starts the
  oneshot `flightchecker.service` = `.venv/bin/python -m flightchecker --once --discord` (2-3 h).
- Logs: `~/flightchecker/logs/flightchecker.log` (stdout, rotated weekly) and one file per run in
  `~/flightchecker/outputs/logs/`. Reports: `outputs/reports/`, DB: `outputs/flights.db`, CSV: `outputs/csv/`.
- Browser: Debian `/usr/bin/chromium` (Playwright has no arm64 Debian build), headless, Linux UA
  (`browser.*_linux` in `config/settings.yaml`; `FLIGHTCHECKER_CHROMIUM` env overrides the path).
- Discord: `settings.discord` → `~/diary/bin/discord-send.py` with `HOME=~/diary/home` (bot token
  lives there), channel `#reminders` 1564021528419508386.
- No Claude CLI on the Pi: the Claude-OCR fallback is skipped (logs a warning); DOM extraction
  handles every card today. EasyOCR is not installed (optional, ~2 GB torch).

```bash
ssh pi5 systemctl list-timers flightchecker.timer               # next run
ssh pi5 sudo systemctl start --no-block flightchecker.service   # run now
ssh pi5 tail -f flightchecker/logs/flightchecker.log            # watch
ssh pi5 'ls -t flightchecker/outputs/reports | head -1'         # latest report
ssh pi5 'cd flightchecker && .venv/bin/python -m flightchecker --dry-run'   # validate config
```
The service is a oneshot: never `restart` it mid-run unless you mean to abort the search.

## Routes configured

`config/routes.yaml`: SFO and SJC → IAD, DCA, BWI. `trips:` = every departure day from today to
2026-12-31, return 3-7 days later. Each leg is searched one-way and filtered on its own (max 1 stop,
under 8 h 30 min), then paired by date and ranked by total price. Also supported: `weekend_trips:`
(weekday patterns) and plain `outbound_window`/`return_window`.

## Changing the code: clone → change → push (Pi + GitHub) → test → delete

```bash
cd ~/projects/flightchecker
git clone pi5:flightchecker repo && cd repo
git remote add github https://github.com/pranavhj/FlightChecker
python -m pytest tests -q                       # tests run on the PC too (venv of your choice)
# ...edit, commit, then push to BOTH so they stay in sync:
git push && git push github HEAD
ssh pi5 'cd flightchecker && .venv/bin/python -m pytest tests -q'
ssh pi5 'bash flightchecker/deploy/install_pi.sh'   # only if requirements or deploy/ changed
ssh pi5 sudo systemctl start --no-block flightchecker.service   # real run
```
Delete the clone only after `git status --short` and `git log @{u}..` both print nothing
(and `git log github/<branch>..` is empty after a fetch).

Rules: never edit files on the Pi by hand (pushes use `receive.denyCurrentBranch=updateInstead`,
which needs a clean tree); never copy code with scp/tar; don't run FlightChecker on the PC.
Background Claude sessions must `EnterWorktree` before editing inside `repo/`.

## Key files

```
config/routes.yaml          # add/edit routes here
config/settings.yaml        # browser, Discord, scoring, alert threshold, storage
deploy/                     # systemd service + timer, logrotate, install_pi.sh (idempotent)
flightchecker/scheduler.py  # search loop; _run_date_pairs = both-legs-filtered trips
flightchecker/scrapers/selector_registry.py   # CSS selectors — update when sites change DOM
templates/daily_report.md.j2                  # report layout
```

## Selector maintenance / bot detection

When reports show `ocr_claude`/`manual_review` instead of `dom`, or come back empty, Google changed
the DOM or is blocking. Look at the screenshots in `outputs/screenshots/` on the Pi; to watch a live
browser, run once with `headless: false` on the Pi desktop (VNC `pi5.local:5900`,
`DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000`).

## Tests

```bash
python -m pytest tests/ -q     # 32 tests: ranker, config loader (incl. trips), price history, extraction
```
