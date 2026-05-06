"""Migrate outputs/price_history.json into the SQLite database.

The JSON has minimal data (timestamp + price_usd only).  Each unique timestamp
is treated as one historical "run"; all other fields (airline, duration, etc.)
are stored as NULL — the DB schema handles that fine.

Usage:
    python scripts/migrate_history.py [--db outputs/flights.db] [--json outputs/price_history.json]
    python scripts/migrate_history.py --dry-run   # print summary without writing
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DEFAULT_DB   = Path("outputs/flights.db")
DEFAULT_JSON = Path("outputs/price_history.json")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS routes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        origin      TEXT NOT NULL,
        destination TEXT NOT NULL,
        first_seen  TEXT NOT NULL,
        last_seen   TEXT NOT NULL,
        UNIQUE(origin, destination)
    );
    CREATE TABLE IF NOT EXISTS flight_snapshots (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        run_tag          TEXT NOT NULL,
        scraped_at       TEXT NOT NULL,
        source           TEXT NOT NULL,
        origin           TEXT NOT NULL,
        destination      TEXT NOT NULL,
        depart_date      TEXT NOT NULL,
        leg              TEXT NOT NULL,
        price_usd        REAL,
        airline          TEXT,
        duration_text    TEXT,
        total_hours      REAL,
        stops_text       TEXT,
        dep_time         TEXT,
        arr_time         TEXT,
        baggage_text     TEXT,
        confidence       TEXT,
        extraction_method TEXT,
        score            REAL,
        search_url       TEXT
    );
    CREATE TABLE IF NOT EXISTS price_alerts (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        detected_at   TEXT NOT NULL,
        run_tag       TEXT NOT NULL,
        origin        TEXT NOT NULL,
        destination   TEXT NOT NULL,
        leg           TEXT NOT NULL,
        depart_date   TEXT NOT NULL,
        source        TEXT NOT NULL,
        current_price REAL,
        prior_price   REAL,
        delta_pct     REAL
    );
    CREATE INDEX IF NOT EXISTS idx_route_date
        ON flight_snapshots(origin, destination, depart_date, leg, source);
    CREATE INDEX IF NOT EXISTS idx_run_tag   ON flight_snapshots(run_tag);
    CREATE INDEX IF NOT EXISTS idx_scraped   ON flight_snapshots(scraped_at);
    """)
    conn.commit()


def _parse_key(key: str) -> tuple[str, str, str, str, str]:
    """Parse 'SJC-LAS/outbound/2026-05-10/google_flights'
    → (origin, dest, leg, depart_date, source)
    """
    route, leg, depart_date, source = key.split("/", 3)
    # Route is always 'AAA-BBB' (IATA codes)
    origin, dest = route.split("-", 1)
    return origin, dest, leg, depart_date, source


def migrate(json_path: Path, db_path: Path, dry_run: bool = False) -> None:
    data: dict = json.loads(json_path.read_text(encoding="utf-8"))

    # Group all entries by timestamp so each timestamp becomes one run_tag.
    # Structure: runs[timestamp][(origin,dest,leg,date,source)] = [price, ...]
    runs: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for key, entries in data.items():
        try:
            origin, dest, leg, depart_date, source = _parse_key(key)
        except ValueError:
            print(f"  SKIP (bad key format): {key}")
            continue
        for entry in entries:
            ts    = entry["timestamp"]
            price = entry.get("price_usd")
            runs[ts][(origin, dest, leg, depart_date, source)].append(price)

    print(f"JSON keys  : {len(data)}")
    print(f"Unique runs: {len(runs)}")
    total_rows = sum(
        len(prices)
        for run_entries in runs.values()
        for prices in run_entries.values()
    )
    print(f"Total rows : {total_rows}")

    if dry_run:
        print("\n-- dry-run: no DB writes --")
        for ts in sorted(runs):
            n = sum(len(v) for v in runs[ts].values())
            print(f"  {ts}  {n:4d} rows")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn)

    # Check for already-migrated runs to make the script idempotent
    existing_tags = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT run_tag FROM flight_snapshots WHERE run_tag LIKE 'migrate/%'"
        )
    }

    inserted = 0
    skipped_runs = 0
    for ts in sorted(runs):
        run_tag = f"migrate/{ts}"
        if run_tag in existing_tags:
            skipped_runs += 1
            continue
        run_entries = runs[ts]
        for (origin, dest, leg, depart_date, source), prices in run_entries.items():
            # Upsert route
            conn.execute(
                """
                INSERT INTO routes(origin, destination, first_seen, last_seen)
                VALUES(?,?,?,?)
                ON CONFLICT(origin, destination)
                DO UPDATE SET
                    first_seen = MIN(first_seen, excluded.first_seen),
                    last_seen  = MAX(last_seen,  excluded.last_seen)
                """,
                (origin, dest, ts, ts),
            )
            for price in prices:
                conn.execute(
                    """
                    INSERT INTO flight_snapshots(
                        run_tag, scraped_at, source, origin, destination,
                        depart_date, leg, price_usd,
                        confidence, extraction_method
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        run_tag, ts, source, origin, dest,
                        depart_date, leg, price,
                        "historical_import", "json_history",
                    ),
                )
                inserted += 1
    conn.commit()
    conn.close()

    if skipped_runs:
        print(f"Skipped {skipped_runs} already-migrated run(s) (idempotent).")
    print(f"Inserted {inserted} rows into {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate price_history.json → SQLite")
    parser.add_argument("--db",       default=str(DEFAULT_DB),   help="Path to SQLite DB")
    parser.add_argument("--json",     default=str(DEFAULT_JSON), help="Path to price_history.json")
    parser.add_argument("--dry-run",  action="store_true",       help="Print summary, don't write")
    args = parser.parse_args()

    json_path = Path(args.json)
    db_path   = Path(args.db)

    if not json_path.exists():
        print(f"ERROR: {json_path} not found")
        raise SystemExit(1)

    migrate(json_path, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
