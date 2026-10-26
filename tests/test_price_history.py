import json
import tempfile
from pathlib import Path

import pytest

from flightchecker import price_history as ph
from tests.conftest import make_result


def test_record_and_load(tmp_path):
    history_file = tmp_path / "price_history.json"
    history = ph.load(history_file)
    r = make_result(price_usd=189.0)
    ph.record(history, r)
    ph.save(history, history_file)

    reloaded = ph.load(history_file)
    key = "SJC-LAS/outbound/2026-05-01/google_flights"
    assert key in reloaded
    assert reloaded[key][0]["price_usd"] == 189.0


def test_compute_delta_no_prior():
    history = {}
    r = make_result(price_usd=189.0)
    ph.record(history, r)
    assert ph.compute_delta(history, r) is None


def test_compute_delta_price_drop():
    history = {}
    r = make_result(price_usd=200.0)
    ph.record(history, r)
    r2 = make_result(price_usd=150.0)
    ph.record(history, r2)
    delta = ph.compute_delta(history, r2)
    assert delta == pytest.approx(-25.0)


def test_compute_delta_price_increase():
    history = {}
    r = make_result(price_usd=100.0)
    ph.record(history, r)
    r2 = make_result(price_usd=120.0)
    ph.record(history, r2)
    delta = ph.compute_delta(history, r2)
    assert delta == pytest.approx(20.0)


def test_compute_alerts_filters_by_threshold():
    history = {}
    r = make_result(price_usd=200.0)
    ph.record(history, r)
    r2 = make_result(price_usd=185.0)  # 7.5% drop
    ph.record(history, r2)

    alerts = ph.compute_alerts(history, [r2], min_drop_pct=5.0)
    assert len(alerts) == 1
    assert alerts[0]["delta_pct"] == pytest.approx(-7.5)

    # 3% drop should not trigger with 5% threshold
    history2 = {}
    r3 = make_result(price_usd=200.0)
    ph.record(history2, r3)
    r4 = make_result(price_usd=194.0)  # 3% drop
    ph.record(history2, r4)
    alerts2 = ph.compute_alerts(history2, [r4], min_drop_pct=5.0)
    assert len(alerts2) == 0


def test_load_missing_file_returns_empty(tmp_path):
    history = ph.load(tmp_path / "nonexistent.json")
    assert history == {}
