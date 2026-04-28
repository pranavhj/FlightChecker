"""Entry point: python -m flightchecker"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import schedule
import time as _time

logger = logging.getLogger(__name__)


def _run_once(config_dir: Path, date_override: str | None = None) -> None:
    from flightchecker.config_loader import load_routes, load_settings
    from flightchecker.scheduler import DailyRunner
    from flightchecker.reporter import Reporter
    from flightchecker import price_history as ph
    from flightchecker.utils.logging_config import setup_logging

    settings = load_settings(config_dir / "settings.yaml")
    routes, top_n = load_routes(config_dir / "routes.yaml")

    now_utc = datetime.now(timezone.utc)
    run_date = date_override or now_utc.strftime("%Y-%m-%d")
    run_time = now_utc.strftime("%H:%M")
    run_tag = f"{run_date}_{run_time.replace(':', '')}"

    log_dir = Path("outputs/logs")
    setup_logging(log_dir, run_tag)

    output_cfg = settings.get("output", {})
    screenshots_dir = output_cfg.get("screenshots_dir", "outputs/screenshots")
    reports_dir = output_cfg.get("reports_dir", "outputs/reports")
    history_file = Path(output_cfg.get("price_history_file", "outputs/price_history.json"))

    Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
    Path(reports_dir).mkdir(parents=True, exist_ok=True)

    history = ph.load(history_file)

    runner = DailyRunner(routes, settings, top_n=top_n)
    route_results = asyncio.run(runner.run())

    # Flatten all FlightResults for history recording
    all_flight_results = []
    for rr in route_results:
        all_flight_results.extend(rr.outbound_results)
        all_flight_results.extend(rr.return_results)

    min_drop = settings.get("price_alerts", {}).get("min_drop_pct", 5.0)
    alerts = ph.compute_alerts(history, all_flight_results, min_drop)
    ph.update_all(history, all_flight_results)
    ph.save(history, history_file)

    reporter = Reporter(templates_dir=Path("templates"))
    report_path = Path(reports_dir) / f"{run_tag}_report.md"
    reporter.render(route_results, alerts, report_path, run_date, run_time, settings)

    manual_review = [
        f"{r.source}/{r.origin}→{r.destination}/{r.leg}/{r.depart_date}"
        for rr in route_results
        for r in (rr.outbound_results + rr.return_results)
        if r.confidence == "manual_review"
    ]

    print(f"\nReport: {report_path}")
    if alerts:
        print(f"Price alerts: {len(alerts)}")
        for a in alerts:
            print(f"  {a['route']} {a['leg']} {a['date']} ({a['source']}): "
                  f"${a['current_price']:.0f} ↓ from ${a['prior_price']:.0f} "
                  f"({a['delta_pct']:.1f}%)")
    if manual_review:
        print(f"Manual review needed ({len(manual_review)}):")
        for item in manual_review:
            print(f"  {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlightChecker — flight price monitor")
    parser.add_argument("--config-dir", default="config", help="Config directory (default: config/)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    parser.add_argument("--once", action="store_true", help="Run once and exit (ignore schedule)")
    parser.add_argument("--date-override", help="Override run date (YYYY-MM-DD)")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    if not config_dir.exists():
        print(f"Config directory not found: {config_dir}", file=sys.stderr)
        sys.exit(1)

    # Validate config
    from flightchecker.config_loader import load_routes, load_settings
    try:
        settings = load_settings(config_dir / "settings.yaml")
        routes, top_n = load_routes(config_dir / "routes.yaml")
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Config OK — {len(routes)} routes, top_n={top_n}")
        for r in routes:
            trip = "one-way" if r.one_way else "return"
            print(f"  {r.origin}→{r.destination} ({trip})")
        sys.exit(0)

    if args.once:
        _run_once(config_dir, args.date_override)
        return

    # Scheduled mode: run at configured UTC times
    run_times = settings.get("schedule", {}).get("run_times_utc", ["14:00", "20:00", "02:00"])
    for t in run_times:
        schedule.every().day.at(t).do(_run_once, config_dir=config_dir)

    print(f"Scheduler started. Run times (UTC): {run_times}")
    print("Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        _time.sleep(30)


if __name__ == "__main__":
    main()
