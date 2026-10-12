"""Entry point: python -m flightchecker"""
import argparse
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import schedule
import time as _time

logger = logging.getLogger(__name__)


def _discord_enabled() -> bool:
    """Return False if FLIGHTCHECKER_NO_DISCORD env var is set to a truthy value."""
    val = os.getenv("FLIGHTCHECKER_NO_DISCORD", "").strip().lower()
    return val not in ("1", "true", "yes", "on")


def _post_to_discord(report_path: Path, route_results: list, run_time: str) -> None:
    """Post detailed flight options to Discord."""
    if not route_results:
        return

    def fmt_price(usd):
        return f"${usd:.0f}" if usd else "?"

    def clean_time(t: str) -> str:
        """Collapse embedded newlines/whitespace from scraped time text."""
        return " ".join(t.split()) if t else "?"

    def fmt_flight(r) -> str:
        time_str = clean_time(r.dep_time_text)
        lines = [
            f"• **{r.depart_date}** — {r.airline_text or '?'} — **{r.price_text or '?'}**",
            f"  {time_str} · {r.duration_text or '?'} · {r.stops_text or '?'}",
        ]
        if r.baggage_text:
            lines.append(f"  Bag: {r.baggage_text}")
        if r.search_url:
            lines.append(f"  <{r.search_url}>")
        return "\n".join(lines)

    def send_msg(msg: str) -> None:
        try:
            subprocess.run(
                ["python", "D:\\MyData\\Software\\openclaw-config\\bin\\discord-send.py",
                 "--target", "1482473282925101217", "--message", msg],
                check=False, timeout=10
            )
        except Exception as e:
            logger.warning("Failed to post to Discord: %s", e)

    send_msg(f"**FlightChecker Update** ({run_time} UTC)")

    for rr in route_results:
        origin, dest = rr.route.origin, rr.route.destination

        per_leg = not rr.route.date_pairs  # weekend routes: the combos block already shows both legs

        if per_leg and rr.outbound_results:
            top = rr.outbound_results[:3]
            block = f"**{origin} → {dest}** (Outbound — {len(top)} options)\n\n"
            block += "\n\n".join(fmt_flight(r) for r in top)
            send_msg(block)

        if per_leg and rr.return_results:
            top = rr.return_results[:3]
            block = f"**{dest} → {origin}** (Return — {len(top)} options)\n\n"
            block += "\n\n".join(fmt_flight(r) for r in top)
            send_msg(block)

        if rr.roundtrip_results:
            top = rr.roundtrip_results[:3]
            block = f"**{origin} ↔ {dest}** (Round-trip — {len(top)} options)\n\n"
            entries = []
            for r in top:
                dates = f"{r.depart_date} → {r.return_date}" if r.return_date else r.depart_date
                time_str = clean_time(r.dep_time_text)
                lines = [
                    f"• **{dates}** — {r.airline_text or '?'} — **{r.price_text or '?'}**",
                    f"  {time_str} · {r.duration_text or '?'} · {r.stops_text or '?'}",
                ]
                if r.baggage_text:
                    lines.append(f"  Bag: {r.baggage_text}")
                if r.search_url:
                    lines.append(f"  <{r.search_url}>")
                entries.append("\n".join(lines))
            block += "\n\n".join(entries)
            send_msg(block)

        if rr.best_pairings:
            top = rr.best_pairings[:3]
            block = f"**{origin} ↔ {dest}** (Best combos)\n\n"
            entries = []
            for p in top:
                out, ret = p.outbound, p.ret
                out_time = clean_time(out.dep_time_text)
                ret_time = clean_time(ret.dep_time_text)
                lines = [
                    f"• **{fmt_price(p.total_price_usd)}** total",
                    f"  Out {out.depart_date} — {out.airline_text or '?'} — {fmt_price(out.price_usd)}"
                    f" — {out_time} · {out.duration_text or '?'} · {out.stops_text or '?'}",
                    f"  Ret {ret.depart_date} — {ret.airline_text or '?'} — {fmt_price(ret.price_usd)}"
                    f" — {ret_time} · {ret.duration_text or '?'} · {ret.stops_text or '?'}",
                ]
                if out.baggage_text or ret.baggage_text:
                    bag = out.baggage_text or ret.baggage_text
                    lines.append(f"  Bag: {bag}")
                if out.search_url:
                    lines.append(f"  Outbound: <{out.search_url}>")
                if ret.search_url:
                    lines.append(f"  Return: <{ret.search_url}>")
                entries.append("\n".join(lines))
            block += "\n\n".join(entries)
            send_msg(block)


def _run_once(config_dir: Path, date_override: str | None = None, post_discord: bool = False) -> None:
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

    storage_cfg = settings.get("storage", {})
    use_sqlite = storage_cfg.get("backend", "json") == "sqlite"

    Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
    Path(reports_dir).mkdir(parents=True, exist_ok=True)

    runner = DailyRunner(routes, settings, top_n=top_n)
    route_results = asyncio.run(runner.run())

    all_flight_results = []
    for rr in route_results:
        all_flight_results.extend(rr.outbound_results)
        all_flight_results.extend(rr.return_results)
        all_flight_results.extend(rr.roundtrip_results)

    min_drop = settings.get("price_alerts", {}).get("min_drop_pct", 5.0)

    if use_sqlite:
        from flightchecker.database import FlightDatabase
        db_path = Path(storage_cfg.get("db_file", "outputs/flights.db"))
        db = FlightDatabase(db_path)
        alerts = db.compute_alerts(all_flight_results, min_drop, run_tag)
        db.record_flights(all_flight_results, run_tag)

        if storage_cfg.get("csv_export", False):
            csv_dir = Path(storage_cfg.get("csv_dir", "outputs/csv"))
            csv_path = csv_dir / f"{run_tag}.csv"
            n = db.export_csv(csv_path, run_tag=run_tag)
            logger.info("CSV export: %d rows -> %s", n, csv_path)

        db.close()
    else:
        history = ph.load(history_file)
        alerts = ph.compute_alerts(history, all_flight_results, min_drop)
        ph.update_all(history, all_flight_results)
        ph.save(history, history_file)

    reporter = Reporter(templates_dir=Path("templates"))
    report_path = Path(reports_dir) / f"{run_tag}_report.md"
    reporter.render(route_results, alerts, report_path, run_date, run_time, settings)

    manual_review = [
        f"{r.source}/{r.origin}->{r.destination}/{r.leg}/{r.depart_date}"
        for rr in route_results
        for r in (rr.outbound_results + rr.return_results)
        if r.confidence == "manual_review"
    ]

    print(f"\nReport: {report_path}")
    if alerts:
        print(f"Price alerts: {len(alerts)}")
        for a in alerts:
            print(f"  {a['route']} {a['leg']} {a['date']} ({a['source']}): "
                  f"${a['current_price']:.0f} v from ${a['prior_price']:.0f} "
                  f"({a['delta_pct']:.1f}%)")
    if manual_review:
        print(f"Manual review needed ({len(manual_review)}):")
        for item in manual_review:
            print(f"  {item}")

    if use_sqlite:
        print("\n--- Booking analysis ---")
        _cmd_analyze(config_dir, settings)

    if post_discord and _discord_enabled():
        _post_to_discord(report_path, route_results, run_time)
    elif post_discord and not _discord_enabled():
        logger.info("Discord notifications suppressed (FLIGHTCHECKER_NO_DISCORD is set)")


def _cmd_analyze(config_dir: Path, settings: dict) -> None:
    """Print best booking time summary from the SQLite DB."""
    from flightchecker.config_loader import load_routes
    from flightchecker.database import FlightDatabase

    storage_cfg = settings.get("storage", {})
    if storage_cfg.get("backend", "json") != "sqlite":
        print("--analyze requires storage.backend=sqlite in settings.yaml", file=sys.stderr)
        sys.exit(1)

    db_path = Path(storage_cfg.get("db_file", "outputs/flights.db"))
    if not db_path.exists():
        print(f"Database not found: {db_path}\nRun --once first to populate it.", file=sys.stderr)
        sys.exit(1)

    db = FlightDatabase(db_path)
    routes, _ = load_routes(config_dir / "routes.yaml")

    print(f"Database: {db_path}  ({db.snapshot_count()} snapshots)\n")

    for route in routes:
        origin, dest = route.origin, route.destination
        print(f"{'='*60}")
        print(f"  {origin} -> {dest}")
        print(f"{'='*60}")

        # Best round-trip combos (return routes only)
        if not route.one_way:
            combos = db.best_round_trip_combos(origin, dest, top_n=5)
            if combos:
                print(f"\n  Top 5 cheapest round-trip combos (outbound+return):")
                print(f"  {'Out Date':<12} {'Out $':>6}   {'Ret Date':<12} {'Ret $':>6}   {'Total':>7}")
                print(f"  {'-'*12} {'-'*6}   {'-'*12} {'-'*6}   {'-'*7}")
                for c in combos:
                    print(f"  {c['out_date']:<12} ${c['out_price']:>5.0f}   "
                          f"{c['ret_date']:<12} ${c['ret_price']:>5.0f}   "
                          f"${c['total_price']:>6.0f}")

        # Per-date price summary
        summary = db.best_booking_summary(origin, dest)
        if summary:
            print(f"\n  Price history per date (min/avg/max, all runs):")
            print(f"  {'Date':<12} {'Leg':<10} {'Source':<16} {'Min':>6} {'Avg':>6} {'Max':>6} {'Runs':>5}")
            print(f"  {'-'*12} {'-'*10} {'-'*16} {'-'*6} {'-'*6} {'-'*6} {'-'*5}")
            for s in summary:
                print(f"  {s['depart_date']:<12} {s['leg']:<10} {s['source']:<16} "
                      f"${s['min_price']:>5.0f} ${s['avg_price']:>5.0f} ${s['max_price']:>5.0f} "
                      f"{s['snapshots']:>5}")
        print()

    db.close()


def _cmd_export_csv(settings: dict, output_path: Path | None) -> None:
    """Export all DB data to CSV."""
    from flightchecker.database import FlightDatabase

    storage_cfg = settings.get("storage", {})
    if storage_cfg.get("backend", "json") != "sqlite":
        print("--export-csv requires storage.backend=sqlite in settings.yaml", file=sys.stderr)
        sys.exit(1)

    db_path = Path(storage_cfg.get("db_file", "outputs/flights.db"))
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if output_path is None:
        csv_dir = Path(storage_cfg.get("csv_dir", "outputs/csv"))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        output_path = csv_dir / f"{now}_all.csv"

    db = FlightDatabase(db_path)
    n = db.export_csv(output_path)
    db.close()
    print(f"Exported {n} rows -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlightChecker — flight price monitor")
    parser.add_argument("--config-dir", default="config", help="Config directory (default: config/)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    parser.add_argument("--once", action="store_true", help="Run once and exit (ignore schedule)")
    parser.add_argument("--continuous", action="store_true", help="Run continuously every N minutes (ignore schedule)")
    parser.add_argument("--date-override", help="Override run date (YYYY-MM-DD)")
    parser.add_argument("--analyze", action="store_true",
                        help="Print best booking time analysis from DB and exit")
    parser.add_argument("--export-csv", metavar="FILE", nargs="?", const="",
                        help="Export all DB data to CSV (optional output path)")
    parser.add_argument("--no-discord", action="store_true",
                        help="Suppress Discord notifications for this run (data still stored in DB)")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    if not config_dir.exists():
        print(f"Config directory not found: {config_dir}", file=sys.stderr)
        sys.exit(1)

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
            print(f"  {r.origin}->{r.destination} ({trip})")
        backend = settings.get("storage", {}).get("backend", "json")
        print(f"Storage backend: {backend}")
        sys.exit(0)

    if args.analyze:
        _cmd_analyze(config_dir, settings)
        return

    if args.export_csv is not None:
        path = Path(args.export_csv) if args.export_csv else None
        _cmd_export_csv(settings, path)
        return

    if args.once:
        _run_once(config_dir, args.date_override)
        return

    if args.continuous:
        # Continuous mode
        interval_minutes = settings.get("continuous", {}).get("interval_minutes", 15)
        want_discord = not args.no_discord
        print(f"Continuous mode started. Running every {interval_minutes} minute(s).")
        if not want_discord:
            print("Discord notifications disabled (--no-discord).")
        elif not _discord_enabled():
            print("Discord notifications disabled (FLIGHTCHECKER_NO_DISCORD is set).")
        print("Press Ctrl+C to stop.")
        while True:
            _run_once(config_dir, args.date_override, post_discord=want_discord)
            print(f"\nNext run in {interval_minutes} minute(s)...")
            _time.sleep(interval_minutes * 60)
        return

    # Scheduled mode
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
