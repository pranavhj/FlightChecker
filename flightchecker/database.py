"""SQLite-backed flight data storage.

Single flight_snapshots table handles all routes automatically — new routes
from config changes need no schema migrations. The routes table tracks
first/last seen timestamps per (origin, destination) pair.

Usage (via settings.yaml):
    storage:
      backend: sqlite          # "sqlite" | "json"  (default: json)
      db_file: outputs/flights.db
      csv_export: true         # write CSV after each run
      csv_dir: outputs/csv
"""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flightchecker.models import FlightResult

_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_route_date
    ON flight_snapshots(origin, destination, depart_date, leg, source);
CREATE INDEX IF NOT EXISTS idx_run_tag   ON flight_snapshots(run_tag);
CREATE INDEX IF NOT EXISTS idx_scraped   ON flight_snapshots(scraped_at);

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
"""


class FlightDatabase:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def compute_alerts(
        self,
        results: list[FlightResult],
        min_drop_pct: float,
        run_tag: str,
    ) -> list[dict]:
        """Compare results against the most recent DB snapshot per route/date.

        Must be called BEFORE record_flights so new prices aren't included.
        Returns alert dicts matching the same shape as price_history.compute_alerts.
        """
        now = datetime.now(timezone.utc).isoformat()
        alerts = []
        for r in results:
            if r.price_usd is None:
                continue
            row = self._conn.execute(
                """
                SELECT price_usd, scraped_at FROM flight_snapshots
                WHERE origin=? AND destination=? AND depart_date=? AND leg=? AND source=?
                ORDER BY scraped_at DESC LIMIT 1
                """,
                (r.origin, r.destination, r.depart_date, r.leg, r.source),
            ).fetchone()
            if row is None or row["price_usd"] is None or row["price_usd"] == 0:
                continue
            prior_price = row["price_usd"]
            delta = round((r.price_usd - prior_price) / prior_price * 100, 2)
            if delta <= -min_drop_pct:
                alerts.append(
                    {
                        "route": f"{r.origin}→{r.destination}",
                        "leg": r.leg,
                        "date": r.depart_date,
                        "source": r.source,
                        "current_price": r.price_usd,
                        "prior_price": prior_price,
                        "prior_timestamp": row["scraped_at"],
                        "delta_pct": delta,
                    }
                )
                self._conn.execute(
                    """
                    INSERT INTO price_alerts(
                        detected_at, run_tag, origin, destination, leg, depart_date,
                        source, current_price, prior_price, delta_pct)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        now, run_tag, r.origin, r.destination, r.leg, r.depart_date,
                        r.source, r.price_usd, prior_price, delta,
                    ),
                )
        return alerts

    def record_flights(self, results: list[FlightResult], run_tag: str) -> None:
        """Insert one snapshot row per FlightResult."""
        now = datetime.now(timezone.utc).isoformat()
        for r in results:
            self._conn.execute(
                """
                INSERT INTO routes(origin, destination, first_seen, last_seen)
                VALUES(?,?,?,?)
                ON CONFLICT(origin, destination) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (r.origin, r.destination, now, now),
            )
            self._conn.execute(
                """
                INSERT INTO flight_snapshots(
                    run_tag, scraped_at, source, origin, destination, depart_date, leg,
                    price_usd, airline, duration_text, total_hours, stops_text,
                    dep_time, arr_time, baggage_text, confidence, extraction_method,
                    score, search_url
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_tag, now, r.source, r.origin, r.destination,
                    r.depart_date, r.leg, r.price_usd, r.airline_text,
                    r.duration_text, r.total_hours, r.stops_text,
                    r.dep_time_text, r.arr_time_text, r.baggage_text,
                    r.confidence, r.extraction_method, r.score, r.search_url,
                ),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self, output_path: Path, run_tag: Optional[str] = None) -> int:
        """Write flight_snapshots to CSV.

        Args:
            output_path: Destination file.
            run_tag: If provided, export only that run; otherwise export everything.

        Returns:
            Number of rows written.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if run_tag:
            rows = self._conn.execute(
                """
                SELECT * FROM flight_snapshots
                WHERE run_tag=?
                ORDER BY scraped_at, origin, destination, depart_date, leg
                """,
                (run_tag,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM flight_snapshots
                ORDER BY scraped_at, origin, destination, depart_date, leg
                """
            ).fetchall()
        if not rows:
            return 0
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(dict(r) for r in rows)
        return len(rows)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def best_booking_summary(self, origin: str, dest: str) -> list[dict]:
        """Per depart_date/leg/source: min, max, avg price and snapshot count.

        Useful for identifying cheapest dates and price stability.
        """
        rows = self._conn.execute(
            """
            SELECT
                depart_date,
                leg,
                source,
                MIN(price_usd)  AS min_price,
                MAX(price_usd)  AS max_price,
                ROUND(AVG(price_usd), 2) AS avg_price,
                COUNT(*)        AS snapshots
            FROM flight_snapshots
            WHERE origin=? AND destination=? AND price_usd IS NOT NULL
            GROUP BY depart_date, leg, source
            ORDER BY depart_date, leg
            """,
            (origin, dest),
        ).fetchall()
        return [dict(r) for r in rows]

    def price_trend(
        self,
        origin: str,
        dest: str,
        depart_date: str,
        leg: str,
        source: str,
    ) -> list[dict]:
        """Return all price snapshots over time for a single route+date."""
        rows = self._conn.execute(
            """
            SELECT scraped_at, price_usd, airline, run_tag
            FROM flight_snapshots
            WHERE origin=? AND destination=? AND depart_date=? AND leg=? AND source=?
            ORDER BY scraped_at
            """,
            (origin, dest, depart_date, leg, source),
        ).fetchall()
        return [dict(r) for r in rows]

    def best_round_trip_combos(
        self,
        origin: str,
        dest: str,
        source: str = "google_flights",
        top_n: int = 10,
    ) -> list[dict]:
        """Find cheapest outbound+return date combinations using min prices seen.

        Only pairs where return_date > outbound_date are considered.
        """
        rows = self._conn.execute(
            """
            WITH out_leg AS (
                SELECT depart_date AS out_date, MIN(price_usd) AS out_price
                FROM flight_snapshots
                WHERE origin=? AND destination=? AND source=? AND leg='outbound'
                  AND price_usd IS NOT NULL
                GROUP BY depart_date
            ),
            ret_leg AS (
                SELECT depart_date AS ret_date, MIN(price_usd) AS ret_price
                FROM flight_snapshots
                WHERE origin=? AND destination=? AND source=? AND leg='return'
                  AND price_usd IS NOT NULL
                GROUP BY depart_date
            )
            SELECT
                out_date,
                out_price,
                ret_date,
                ret_price,
                ROUND(out_price + ret_price, 2) AS total_price
            FROM out_leg
            JOIN ret_leg ON ret_date > out_date
            ORDER BY total_price ASC
            LIMIT ?
            """,
            (origin, dest, source, dest, origin, source, top_n),
        ).fetchall()
        return [dict(r) for r in rows]

    def known_routes(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT origin, destination, first_seen, last_seen FROM routes ORDER BY first_seen"
        ).fetchall()
        return [dict(r) for r in rows]

    def snapshot_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM flight_snapshots").fetchone()[0]
