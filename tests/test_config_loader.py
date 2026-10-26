import tempfile
from pathlib import Path

import pytest
import yaml

from flightchecker.config_loader import load_routes, date_range, stay_date_pairs


def write_yaml(tmp_path: Path, filename: str, data: dict) -> Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data))
    return p


def test_load_routes_one_way(tmp_path):
    data = {
        "top_n_results": 5,
        "routes": [{
            "origin": "SJC",
            "destination": "LAS",
            "one_way": True,
            "outbound_window": {"start": "2026-05-01", "end": "2026-05-07"},
        }]
    }
    p = write_yaml(tmp_path, "routes.yaml", data)
    routes, top_n = load_routes(p)
    assert top_n == 5
    assert len(routes) == 1
    assert routes[0].origin == "SJC"
    assert routes[0].one_way is True
    assert routes[0].return_window is None


def test_load_routes_return(tmp_path):
    data = {
        "top_n_results": 3,
        "routes": [{
            "origin": "SJC",
            "destination": "ORD",
            "one_way": False,
            "outbound_window": {"start": "2026-05-01", "end": "2026-05-03"},
            "return_window": {"start": "2026-05-08", "end": "2026-05-10"},
        }]
    }
    p = write_yaml(tmp_path, "routes.yaml", data)
    routes, top_n = load_routes(p)
    assert routes[0].one_way is False
    assert routes[0].return_window == {"start": "2026-05-08", "end": "2026-05-10"}


def test_load_routes_missing_return_window_raises(tmp_path):
    data = {
        "routes": [{
            "origin": "SJC",
            "destination": "ORD",
            "one_way": False,
            "outbound_window": {"start": "2026-05-01", "end": "2026-05-03"},
        }]
    }
    p = write_yaml(tmp_path, "routes.yaml", data)
    with pytest.raises(ValueError, match="return_window"):
        load_routes(p)


def test_date_range_inclusive():
    window = {"start": "2026-05-01", "end": "2026-05-03"}
    dates = date_range(window)
    assert dates == ["2026-05-01", "2026-05-02", "2026-05-03"]


def test_date_range_single_day():
    window = {"start": "2026-05-01", "end": "2026-05-01"}
    assert date_range(window) == ["2026-05-01"]


def test_stay_pairs_cover_every_stay_length_from_each_departure_day():
    spec = {"start": "2099-03-01", "end": "2099-03-06", "min_days": 3, "max_days": 4}
    assert stay_date_pairs(spec) == [
        ("2099-03-01", "2099-03-04"), ("2099-03-01", "2099-03-05"),
        ("2099-03-02", "2099-03-05"), ("2099-03-02", "2099-03-06"),
        ("2099-03-03", "2099-03-06"),
    ]


def test_stay_pairs_empty_when_window_shorter_than_min_stay():
    spec = {"start": "2099-03-01", "end": "2099-03-02", "min_days": 3, "max_days": 7}
    assert stay_date_pairs(spec) == []


def test_trips_route_becomes_round_trip_with_date_pairs(tmp_path):
    data = {"routes": [{
        "origins": ["SJC"], "destinations": ["IAD"],
        "trips": {"start": "2099-03-01", "end": "2099-03-05", "min_days": 3, "max_days": 7},
    }]}
    routes, _ = load_routes(write_yaml(tmp_path, "routes.yaml", data))
    assert routes[0].date_pairs == [("2099-03-01", "2099-03-04"), ("2099-03-01", "2099-03-05"),
                                    ("2099-03-02", "2099-03-05")]
