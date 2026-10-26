from pathlib import Path
from typing import Any
import yaml

from flightchecker.models import RouteConfig


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_routes(path: Path) -> tuple[list[RouteConfig], int]:
    data = load_yaml(path)
    top_n = data.get("top_n_results", 3)
    routes = []
    for r in data.get("routes", []):
        one_way = r.get("one_way", True)
        return_window = None
        if not one_way:
            return_window = r.get("return_window")
            if return_window is None:
                raise ValueError(
                    f"Route {r['origin']}→{r['destination']} has one_way=false but no return_window"
                )
        routes.append(RouteConfig(
            origin=r["origin"],
            destination=r["destination"],
            one_way=one_way,
            outbound_window=r.get("outbound_window") or r.get("date_window"),
            return_window=return_window,
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
