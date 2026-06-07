import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flightchecker.models import FlightResult


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save(history: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def _key(origin: str, destination: str, leg: str, date: str, source: str) -> str:
    return f"{origin}-{destination}/{leg}/{date}/{source}"


def record(history: dict, result: FlightResult) -> None:
    if result.price_usd is None:
        return
    key = _key(result.origin, result.destination, result.leg, result.depart_date, result.source)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_usd": result.price_usd,
    }
    history.setdefault(key, []).append(entry)


def compute_delta(history: dict, result: FlightResult) -> Optional[float]:
    """Return % change vs most recent prior entry. Negative = price dropped."""
    if result.price_usd is None:
        return None
    key = _key(result.origin, result.destination, result.leg, result.depart_date, result.source)
    entries = history.get(key, [])
    if len(entries) < 2:
        return None
    prior_price = entries[-2]["price_usd"]
    if prior_price == 0:
        return None
    return round((result.price_usd - prior_price) / prior_price * 100, 2)


def compute_alerts(history: dict, results: list[FlightResult], min_drop_pct: float) -> list[dict]:
    """Return list of alert dicts for results that dropped >= min_drop_pct."""
    alerts = []
    for r in results:
        delta = compute_delta(history, r)
        if delta is not None and delta <= -min_drop_pct:
            key = _key(r.origin, r.destination, r.leg, r.depart_date, r.source)
            entries = history.get(key, [])
            prior = entries[-2] if len(entries) >= 2 else None
            alerts.append({
                "route": f"{r.origin}→{r.destination}",
                "leg": r.leg,
                "date": r.depart_date,
                "source": r.source,
                "current_price": r.price_usd,
                "prior_price": prior["price_usd"] if prior else None,
                "prior_timestamp": prior["timestamp"] if prior else None,
                "delta_pct": delta,
            })
    return alerts


def update_all(history: dict, results: list[FlightResult]) -> None:
    for r in results:
        record(history, r)
