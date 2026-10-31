from pathlib import Path
from typing import Any
import yaml

from flightchecker.models import RouteConfig


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def weekend_date_pairs(spec: dict) -> list[tuple[str, str]]:
    """Expand a weekend_trips spec into (outbound, return) ISO date pairs.

    spec: {start, end, patterns: [[out_weekday, ret_weekday], ...]}. The return date
    is the first matching weekday after the outbound; pairs whose return falls after
    `end` or before today are dropped.
    """
    from datetime import date, timedelta
    start = max(date.fromisoformat(str(spec["start"])), date.today())
    end = date.fromisoformat(str(spec["end"]))
    pairs: list[tuple[str, str]] = []
    for out_name, ret_name in spec.get("patterns", [["fri", "mon"]]):
        out_wd, ret_wd = _WEEKDAYS[out_name.lower()[:3]], _WEEKDAYS[ret_name.lower()[:3]]
        gap = (ret_wd - out_wd) % 7 or 7
        day = start + timedelta(days=(out_wd - start.weekday()) % 7)
        while day + timedelta(days=gap) <= end:
            pairs.append((day.isoformat(), (day + timedelta(days=gap)).isoformat()))
            day += timedelta(days=7)
    return sorted(pairs)


def stay_date_pairs(spec: dict) -> list[tuple[str, str]]:
    """Expand a trips spec into (outbound, return) ISO date pairs for any departure day.

    spec: {start, end, min_days, max_days, last_outbound?, exclude_dates?}. The return is
    min_days..max_days after the outbound; pairs before today or returning after `end` are
    dropped, as are outbound dates after `last_outbound` and trips that are away on an
    exclude_dates day (outbound <= day < return; flying home that day is fine).
    """
    from datetime import date, timedelta
    start = max(date.fromisoformat(str(spec["start"])), date.today())
    end = date.fromisoformat(str(spec["end"]))
    last_outbound = date.fromisoformat(str(spec["last_outbound"])) if spec.get("last_outbound") else end
    excluded = [date.fromisoformat(str(d)) for d in spec.get("exclude_dates", [])]
    pairs: list[tuple[str, str]] = []
    day = start
    while day <= last_outbound and day + timedelta(days=spec["min_days"]) <= end:
        for stay in range(spec["min_days"], spec["max_days"] + 1):
            ret = day + timedelta(days=stay)
            if ret <= end and not any(day <= d < ret for d in excluded):
                pairs.append((day.isoformat(), ret.isoformat()))
        day += timedelta(days=1)
    return pairs


def load_routes(path: Path) -> tuple[list[RouteConfig], int]:
    data = load_yaml(path)
    top_n = data.get("top_n_results", 3)
    routes = []
    for r in data.get("routes", []):
        origins = r.get("origins") or [r["origin"]]
        destinations = r.get("destinations") or [r["destination"]]
        if r.get("weekend_trips"):
            pairs = weekend_date_pairs(r["weekend_trips"])
        elif r.get("trips"):
            pairs = stay_date_pairs(r["trips"])
        else:
            pairs = []
        one_way = False if pairs else r.get("one_way", True)
        return_window = None
        outbound_window = r.get("outbound_window") or r.get("date_window")
        if pairs:
            outbound_window = {"start": pairs[0][0], "end": pairs[-1][0]}
            return_window = {"start": min(p[1] for p in pairs), "end": max(p[1] for p in pairs)}
        elif not one_way:
            return_window = r.get("return_window")
            if return_window is None:
                raise ValueError(
                    f"Route {origins}→{destinations} has one_way=false but no return_window"
                )
        for origin in origins:
            for destination in destinations:
                routes.append(RouteConfig(
                    origin=origin,
                    destination=destination,
                    one_way=one_way,
                    outbound_window=outbound_window,
                    return_window=return_window,
                    nonstop_only=r.get("nonstop_only", False),
                    same_day_return=r.get("same_day_return", False),
                    max_duration_hours=r.get("max_duration_hours"),
                    max_stops=r.get("max_stops"),
                    checked_bag_required=r.get("checked_bag_required", False),
                    same_airline_only=r.get("same_airline_only", False),
                    date_pairs=list(pairs),
                ))
    return routes, top_n


def load_settings(path: Path) -> dict:
    return load_yaml(path)


def date_range(window: dict) -> list[str]:
    """Return all dates (YYYY-MM-DD strings) from window start to end inclusive."""
    from datetime import date, timedelta
    start = date.fromisoformat(window["start"])
    end = date.fromisoformat(window["end"])
    days = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days
